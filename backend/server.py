"""CloudLedger — FastAPI backend. Upload, pipeline, and data endpoints."""

import os
import tempfile
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, distinct

from cloudledger.config import ALLOWED_ORIGINS, MAX_UPLOAD_SIZE_MB, ANTHROPIC_API_KEY
import cloudledger.database as _db
from cloudledger.database import (
    create_all_tables,
    RawBillingLine, Invoice, Resource, ChangeEvent, VarianceReport, Allocation,
)


def get_db():
    """Wrapper that delegates to cloudledger.database.get_db for testability."""
    return _db.get_db()
from cloudledger.ingest import ingest_focus_csv
from cloudledger.normalize import normalize_invoices, normalize_resources
from cloudledger.terraform import parse_terraform_state
from cloudledger.variance import compute_variance

import re as _re
import logging

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    create_all_tables()
    yield


def _parse_period(period: str) -> date:
    """Validate and parse a 'YYYY-MM' period string to a date."""
    if not _re.match(r"^\d{4}-(0[1-9]|1[0-2])$", period):
        raise HTTPException(400, f"Invalid period format: '{period}'. Expected YYYY-MM (e.g. 2024-03).")
    return date.fromisoformat(f"{period}-01")


app = FastAPI(title="CloudLedger API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _f(v) -> float:
    """Convert any Decimal/None to float for JSON serialization."""
    if v is None:
        return 0.0
    return float(v)


# Reason codes that mean "unmanaged / drift" (not in any IaC)
DRIFT_CODES = {"drift", "orphan_sdk_created", "orphan_unknown", "legacy_untracked", "non_terraform_iac"}
# Reason codes that mean "organic change" (managed but no PR)
USAGE_CODES = {"usage_growth", "new_resource", "removed_resource", "price_change", "steady_state"}
# Reason codes that are edge-case exclusions
EDGE_CODES = {"savings_plan_allocation", "ri_coverage_shift", "cross_service_transfer",
              "marketplace_subscription", "spot_price_volatility", "credit_applied", "tag_propagation_delay"}


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Periods ──────────────────────────────────────────────────────────────────

@app.get("/api/periods")
def get_periods():
    with get_db() as session:
        rows = (
            session.query(distinct(RawBillingLine.billing_period_start))
            .order_by(RawBillingLine.billing_period_start.desc())
            .all()
        )
        periods = [r[0].strftime("%Y-%m") for r in rows if r[0]]
    return {"periods": periods}


# ── Upload billing CSVs ─────────────────────────────────────────────────────

@app.post("/api/upload")
async def upload_csv(files: list[UploadFile] = File(...)):
    if len(files) > 20:
        raise HTTPException(400, "Maximum 20 CSV files allowed")

    # Clear all existing data so we start fresh
    with get_db() as session:
        session.query(Allocation).delete()
        session.query(VarianceReport).delete()
        session.query(Resource).delete()
        session.query(Invoice).delete()
        session.query(RawBillingLine).delete()

    total_inserted = 0
    total_skipped = 0

    for file in files:
        if not file.filename or not file.filename.endswith(".csv"):
            raise HTTPException(400, f"Only CSV files accepted, got: {file.filename}")
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"File {file.filename} exceeds {MAX_UPLOAD_SIZE_MB}MB limit")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            stats = ingest_focus_csv(tmp_path)
            total_inserted += stats.get("rows_inserted", 0)
            total_skipped += stats.get("rows_skipped", 0)
        except Exception as e:
            logger.error("Failed to ingest %s: %s", file.filename, e)
            raise HTTPException(400, f"Failed to process {file.filename}: {str(e)}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return {"rows_inserted": total_inserted, "rows_skipped": total_skipped, "files_count": len(files)}


# ── Upload Terraform state ──────────────────────────────────────────────────

@app.post("/api/upload/terraform")
async def upload_terraform(files: list[UploadFile] = File(...)):
    if len(files) > 20:
        raise HTTPException(400, "Maximum 20 files allowed")

    total_resources = 0
    tf_dir = os.path.join(UPLOAD_DIR, "terraform")
    os.makedirs(tf_dir, exist_ok=True)

    for i, file in enumerate(files):
        if not file.filename or not file.filename.endswith((".tfstate", ".json")):
            raise HTTPException(400, f"Only .tfstate or .json accepted, got: {file.filename}")
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"File {file.filename} exceeds {MAX_UPLOAD_SIZE_MB}MB limit")
        save_path = os.path.join(tf_dir, f"terraform_{i}.tfstate")
        with open(save_path, "wb") as f:
            f.write(content)
        try:
            resource_map = parse_terraform_state(save_path)
            total_resources += len(resource_map)
        except Exception as e:
            logger.error("Failed to parse terraform state %s: %s", file.filename, e)
            raise HTTPException(400, f"Invalid terraform state file: {file.filename}")

    return {"resources_parsed": total_resources, "files_count": len(files)}


# ── Run pipeline ─────────────────────────────────────────────────────────────

@app.post("/api/pipeline/run")
def run_pipeline(prior_period: str, current_period: str):
    _parse_period(prior_period)
    _parse_period(current_period)

    tf_dir = os.path.join(UPLOAD_DIR, "terraform")
    tf_paths = []
    if os.path.isdir(tf_dir):
        tf_paths = [os.path.join(tf_dir, f) for f in os.listdir(tf_dir) if f.endswith(".tfstate")]

    normalize_invoices()
    normalize_resources(terraform_state_paths=tf_paths if tf_paths else None)
    result = compute_variance(prior_period, current_period)

    def _sanitize(obj):
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, Decimal):
            return float(obj)
        return obj

    return _sanitize(result)


# ── Screen 1: Bill overview ─────────────────────────────────────────────────

@app.get("/api/bill-overview")
def bill_overview(prior_period: str, current_period: str):
    prior_date = _parse_period(prior_period)
    current_date = _parse_period(current_period)

    with get_db() as session:
        prior_total = _f(
            session.query(func.sum(Invoice.total_billed_cost))
            .filter(Invoice.billing_period_start == prior_date).scalar()
        )
        current_total = _f(
            session.query(func.sum(Invoice.total_billed_cost))
            .filter(Invoice.billing_period_start == current_date).scalar()
        )

    return {
        "prior_total": prior_total,
        "current_total": current_total,
        "delta": current_total - prior_total,
        "prior_period": prior_period,
        "current_period": current_period,
    }


# ── Screen 2: Ingestion stats ───────────────────────────────────────────────

@app.get("/api/ingestion-stats")
def ingestion_stats(current_period: str):
    current_date = _parse_period(current_period)

    with get_db() as session:
        # --- Per-period billing line counts ---
        periods = (
            session.query(
                RawBillingLine.billing_period_start,
                func.count(RawBillingLine.id),
                func.sum(RawBillingLine.billed_cost),
                func.count(distinct(RawBillingLine.resource_id)),
            )
            .group_by(RawBillingLine.billing_period_start)
            .order_by(RawBillingLine.billing_period_start)
            .all()
        )
        period_breakdown = []
        total_billing_rows = 0
        for p_date, cnt, cost, res_cnt in periods:
            total_billing_rows += cnt
            period_breakdown.append({
                "period": p_date.strftime("%Y-%m") if p_date else "unknown",
                "rows": cnt,
                "cost": _f(cost),
                "unique_resources": res_cnt,
            })

        # --- Resource & terraform matching ---
        resources_current = (
            session.query(Resource)
            .filter(Resource.billing_period_start == current_date)
            .all()
        )
        resource_count = len(resources_current)
        tf_matched = [r for r in resources_current if r.in_terraform_state]
        tf_unmatched = [r for r in resources_current if not r.in_terraform_state]
        tf_count = len(tf_matched)

        tf_matched_cost = sum(_f(r.total_cost) for r in tf_matched)
        tf_unmatched_cost = sum(_f(r.total_cost) for r in tf_unmatched)

        # --- Data quality checks ---
        missing_resource_id = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == current_date,
            (RawBillingLine.resource_id == None) | (RawBillingLine.resource_id == ""),  # noqa: E711
        ).scalar() or 0

        missing_service = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == current_date,
            (RawBillingLine.service_name == None) | (RawBillingLine.service_name == ""),  # noqa: E711
        ).scalar() or 0

        zero_cost_lines = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == current_date,
            (RawBillingLine.billed_cost == 0) | (RawBillingLine.billed_cost == None),  # noqa: E711
        ).scalar() or 0

        negative_cost_lines = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == current_date,
            RawBillingLine.billed_cost < 0,
        ).scalar() or 0

        current_period_rows = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == current_date,
        ).scalar() or 0

        # --- Tag coverage ---
        tagged_resources = session.query(func.count(Resource.id)).filter(
            Resource.billing_period_start == current_date,
            Resource.team != None,  # noqa: E711
            Resource.team != "",
        ).scalar() or 0

        tagged_cost = sum(_f(r.total_cost) for r in resources_current if r.team)

        # --- Service breakdown for current period ---
        service_rows = (
            session.query(
                RawBillingLine.service_name,
                func.count(RawBillingLine.id),
                func.sum(RawBillingLine.billed_cost),
                func.count(distinct(RawBillingLine.resource_id)),
            )
            .filter(RawBillingLine.billing_period_start == current_date)
            .group_by(RawBillingLine.service_name)
            .order_by(func.sum(RawBillingLine.billed_cost).desc())
            .all()
        )
        services = []
        for svc, cnt, cost, res_cnt in service_rows:
            svc_tf = session.query(func.count(Resource.id)).filter(
                Resource.billing_period_start == current_date,
                Resource.service_name == svc,
                Resource.in_terraform_state == True,  # noqa: E712
            ).scalar() or 0
            services.append({
                "service": svc or "Unknown",
                "rows": cnt,
                "cost": _f(cost),
                "resources": res_cnt,
                "terraform_matched": svc_tf,
            })

        # --- Top unmatched resources (by cost) ---
        unmatched_resources = sorted(tf_unmatched, key=lambda r: _f(r.total_cost), reverse=True)[:5]
        top_unmatched = [{
            "resource_id": r.resource_id,
            "resource_name": r.resource_name,
            "service": r.service_name,
            "cost": _f(r.total_cost),
        } for r in unmatched_resources]

        # --- Invoice totals ---
        inv = session.query(Invoice).filter(Invoice.billing_period_start == current_date).first()
        total_cost = _f(inv.total_billed_cost) if inv else 0.0
        coverage_pct = _f(inv.attribution_coverage_pct) if inv else 0.0
        unattributed = _f(inv.unattributed_cost) if inv else 0.0

        # --- Provider detection ---
        providers = session.query(distinct(RawBillingLine.provider)).all()
        detected_providers = [p[0] for p in providers if p[0]]

    return {
        "billing_rows": total_billing_rows,
        "current_period_rows": current_period_rows,
        "resource_count": resource_count,
        "terraform_resources": tf_count,
        "terraform_matched_cost": tf_matched_cost,
        "terraform_unmatched_cost": tf_unmatched_cost,
        "total_cost": total_cost,
        "coverage_pct": coverage_pct,
        "unattributed": unattributed,
        "period_breakdown": period_breakdown,
        "data_quality": {
            "missing_resource_id": missing_resource_id,
            "missing_service": missing_service,
            "zero_cost_lines": zero_cost_lines,
            "negative_cost_lines": negative_cost_lines,
        },
        "tag_coverage": {
            "tagged_resources": tagged_resources,
            "tagged_cost": tagged_cost,
            "total_resources": resource_count,
            "total_cost": total_cost,
        },
        "services": services,
        "top_unmatched": top_unmatched,
        "detected_providers": detected_providers,
    }


# ── Screen 3: Variance by service ───────────────────────────────────────────

@app.get("/api/variance-by-service")
def variance_by_service(current_period: str):
    current_date = _parse_period(current_period)

    with get_db() as session:
        svc_rows = (
            session.query(
                VarianceReport.service_name,
                func.sum(VarianceReport.delta_dollars),
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
                func.sum(VarianceReport.prior_cost),
                func.sum(VarianceReport.current_cost),
            )
            .filter(VarianceReport.current_period_start == current_date)
            .group_by(VarianceReport.service_name)
            .order_by(func.sum(func.abs(VarianceReport.delta_dollars)).desc())
            .all()
        )
        services = []
        for svc, delta, abs_delta, cnt, prior_sum, current_sum in svc_rows:
            services.append({
                "service": svc or "Unknown",
                "delta": _f(delta),
                "abs_delta": _f(abs_delta),
                "count": cnt,
                "prior_cost": _f(prior_sum),
                "current_cost": _f(current_sum),
            })

        all_rows = (
            session.query(VarianceReport)
            .filter(VarianceReport.current_period_start == current_date)
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        resources = []
        for v in all_rows:
            resources.append({
                "resource_id": v.resource_id,
                "resource_name": v.resource_name,
                "service": v.service_name or "Unknown",
                "prior_cost": _f(v.prior_cost),
                "current_cost": _f(v.current_cost),
                "delta": _f(v.delta_dollars),
                "delta_pct": _f(v.delta_pct),
                "reason_code": v.reason_code or "unknown",
                "in_terraform": v.in_terraform_state or False,
                "evidence": v.evidence,
                "team": v.team,
            })

        reason_rows = (
            session.query(
                VarianceReport.reason_code,
                func.sum(VarianceReport.delta_dollars),
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
            )
            .filter(VarianceReport.current_period_start == current_date)
            .group_by(VarianceReport.reason_code)
            .order_by(func.sum(func.abs(VarianceReport.delta_dollars)).desc())
            .all()
        )
        reasons = [{
            "code": r[0] or "unknown",
            "delta": _f(r[1]),
            "abs_delta": _f(r[2]),
            "count": r[3],
        } for r in reason_rows]

        total_increases = sum(_f(v.delta_dollars) for v in all_rows if _f(v.delta_dollars) > 0)
        total_decreases = sum(_f(v.delta_dollars) for v in all_rows if _f(v.delta_dollars) < 0)

    total = sum(s["abs_delta"] for s in services)
    return {
        "services": services,
        "resources": resources,
        "reasons": reasons,
        "total_variance": total,
        "total_increases": total_increases,
        "total_decreases": total_decreases,
        "net_change": total_increases + total_decreases,
    }


# ── Screen 4: Root causes ───────────────────────────────────────────────────

@app.get("/api/root-causes")
def root_causes(current_period: str):
    current_date = _parse_period(current_period)

    with get_db() as session:
        all_rows = (
            session.query(VarianceReport)
            .filter(VarianceReport.current_period_start == current_date)
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        buckets = {"planned": [], "drift": [], "usage": [], "edge_cases": []}
        for v in all_rows:
            rc = v.reason_code or "other"
            entry = {
                "resource_id": v.resource_id,
                "resource_name": v.resource_name,
                "service": v.service_name or "Unknown",
                "delta": _f(v.delta_dollars),
                "prior_cost": _f(v.prior_cost),
                "current_cost": _f(v.current_cost),
                "reason_code": rc,
                "evidence": v.evidence,
                "in_terraform": v.in_terraform_state or False,
                "team": v.team,
            }
            if rc == "planned":
                buckets["planned"].append(entry)
            elif rc in DRIFT_CODES:
                buckets["drift"].append(entry)
            elif rc in USAGE_CODES:
                buckets["usage"].append(entry)
            elif rc in EDGE_CODES:
                buckets["edge_cases"].append(entry)
            else:
                buckets["drift"].append(entry)

        reason_rows = (
            session.query(
                VarianceReport.reason_code,
                func.sum(VarianceReport.delta_dollars),
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
            )
            .filter(VarianceReport.current_period_start == current_date)
            .group_by(VarianceReport.reason_code)
            .order_by(func.sum(func.abs(VarianceReport.delta_dollars)).desc())
            .all()
        )
        all_reasons = [{
            "code": r[0] or "other",
            "delta": _f(r[1]),
            "abs_delta": _f(r[2]),
            "count": r[3],
        } for r in reason_rows]

    summary = {}
    for bucket_name, items in buckets.items():
        summary[bucket_name] = {
            "amount": sum(abs(r["delta"]) for r in items),
            "delta": sum(r["delta"] for r in items),
            "count": len(items),
            "top_resources": sorted(items, key=lambda x: abs(x["delta"]), reverse=True)[:5],
        }

    return {
        "planned": summary["planned"],
        "drift": summary["drift"],
        "usage": summary["usage"],
        "edge_cases": summary["edge_cases"],
        "all_reasons": all_reasons,
    }


# ── Screen 5: Close packet ──────────────────────────────────────────────────

@app.get("/api/close-packet")
def close_packet(current_period: str, prior_period: str | None = None):
    current_date = _parse_period(current_period)

    with get_db() as session:
        inv_current = session.query(Invoice).filter(Invoice.billing_period_start == current_date).first()
        total_cost = _f(inv_current.total_billed_cost) if inv_current else 0.0

        prior_cost = 0.0
        if prior_period:
            prior_date = _parse_period(prior_period)
            inv_prior = session.query(Invoice).filter(Invoice.billing_period_start == prior_date).first()
            prior_cost = _f(inv_prior.total_billed_cost) if inv_prior else 0.0

        all_rows = (
            session.query(VarianceReport)
            .filter(VarianceReport.current_period_start == current_date)
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        reason_map: dict = {}
        for v in all_rows:
            rc = v.reason_code or "other"
            if rc not in reason_map:
                reason_map[rc] = {"code": rc, "delta": 0.0, "abs_delta": 0.0, "count": 0, "top_resources": []}
            reason_map[rc]["delta"] += _f(v.delta_dollars)
            reason_map[rc]["abs_delta"] += abs(_f(v.delta_dollars))
            reason_map[rc]["count"] += 1
            if len(reason_map[rc]["top_resources"]) < 3:
                reason_map[rc]["top_resources"].append({
                    "name": v.resource_name or v.resource_id,
                    "delta": _f(v.delta_dollars),
                    "service": v.service_name or "Unknown",
                })

        reasons = sorted(reason_map.values(), key=lambda r: r["abs_delta"], reverse=True)

        drift_items = [v for v in all_rows if v.reason_code in DRIFT_CODES]
        action_items = []
        for v in sorted(drift_items, key=lambda x: abs(_f(x.delta_dollars)), reverse=True)[:5]:
            action_items.append({
                "resource_name": v.resource_name or v.resource_id,
                "service": v.service_name or "Unknown",
                "delta": _f(v.delta_dollars),
                "reason": v.reason_code or "unknown",
                "action": "Import to Terraform" if v.reason_code in ("orphan_unknown", "orphan_sdk_created") else "Investigate drift",
            })

        managed_count = sum(1 for v in all_rows if v.in_terraform_state)
        total_count = len(all_rows)
        managed_cost = sum(abs(_f(v.delta_dollars)) for v in all_rows if v.in_terraform_state)

    total_variance = sum(r["abs_delta"] for r in reasons)
    net_variance = sum(r["delta"] for r in reasons)

    return {
        "prior_cost": prior_cost,
        "total_cost": total_cost,
        "net_variance": net_variance,
        "total_variance": total_variance,
        "reasons": reasons,
        "resource_count": total_count,
        "managed_count": managed_count,
        "managed_cost": managed_cost,
        "action_items": action_items,
    }


# ── GL Export ────────────────────────────────────────────────────────────────

@app.get("/api/gl-export")
def gl_export(current_period: str):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    current_date = _parse_period(current_period)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Account", "Description", "Debit", "Credit", "Reason", "Service"])

    with get_db() as session:
        vrows = session.query(VarianceReport).filter(
            VarianceReport.current_period_start == current_date
        ).all()
        for v in vrows:
            delta = _f(v.delta_dollars)
            debit = abs(delta) if delta > 0 else 0
            credit = abs(delta) if delta < 0 else 0
            writer.writerow([
                current_date.strftime("%Y-%m-%d"),
                f"6{(v.service_name or 'CLD')[:3].upper()}00",
                f"{v.resource_name or v.resource_id} — {(v.reason_code or '').replace('_', ' ')}",
                f"{debit:.2f}",
                f"{credit:.2f}",
                v.reason_code or "",
                v.service_name or "",
            ])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=cloudledger_gl_{current_period}.csv"},
    )


# ── PDF Export ────────────────────────────────────────────────────────────────

@app.get("/api/close-packet/pdf")
def close_packet_pdf(current_period: str, prior_period: str):
    import tempfile as _tempfile
    from starlette.background import BackgroundTask
    from fastapi.responses import FileResponse
    from cloudledger.pdf_export import generate_close_packet_pdf

    _parse_period(current_period)
    _parse_period(prior_period)

    with _tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        out_path = tmp.name

    generate_close_packet_pdf(current_period, prior_period, out_path)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename=f"CloudLedger_Close_Packet_{current_period}.pdf",
        background=BackgroundTask(os.unlink, out_path),
    )


# ── Screen 6: Engineering view ───────────────────────────────────────────────

@app.get("/api/engineering-view")
def engineering_view(current_period: str):
    current_date = _parse_period(current_period)

    with get_db() as session:
        all_rows = (
            session.query(VarianceReport)
            .filter(VarianceReport.current_period_start == current_date)
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        managed = [v for v in all_rows if v.in_terraform_state]
        unmanaged = [v for v in all_rows if not v.in_terraform_state]
        planned = [v for v in all_rows if v.reason_code == "planned"]
        drift = [v for v in all_rows if v.reason_code in DRIFT_CODES]

        managed_cost = sum(_f(v.current_cost) for v in managed)
        unmanaged_cost = sum(_f(v.current_cost) for v in unmanaged)
        total_cost = managed_cost + unmanaged_cost

        drift_resources = []
        for v in sorted(drift, key=lambda x: abs(_f(x.delta_dollars)), reverse=True):
            drift_resources.append({
                "resource_name": v.resource_name or v.resource_id,
                "service": v.service_name or "Unknown",
                "current_cost": _f(v.current_cost),
                "delta": _f(v.delta_dollars),
                "reason_code": v.reason_code or "unknown",
                "team": v.team,
                "iac_source": v.iac_source or "none",
            })

        source_map: dict = {}
        for v in all_rows:
            src = v.iac_source or "none"
            if src not in source_map:
                source_map[src] = {"count": 0, "cost": 0.0}
            source_map[src]["count"] += 1
            source_map[src]["cost"] += _f(v.current_cost)
        iac_sources = [{"source": k, "count": v["count"], "cost": v["cost"]} for k, v in sorted(source_map.items(), key=lambda x: -x[1]["cost"])]

        team_map: dict = {}
        for v in all_rows:
            t = v.team or "Untagged"
            if t not in team_map:
                team_map[t] = {"count": 0, "cost": 0.0, "managed": 0, "delta": 0.0}
            team_map[t]["count"] += 1
            team_map[t]["cost"] += _f(v.current_cost)
            team_map[t]["delta"] += _f(v.delta_dollars)
            if v.in_terraform_state:
                team_map[t]["managed"] += 1
        teams = [{"team": k, **v} for k, v in sorted(team_map.items(), key=lambda x: -x[1]["cost"])]

        planned_total = sum(abs(_f(v.delta_dollars)) for v in planned)
        drift_total_val = sum(abs(_f(v.delta_dollars)) for v in drift)

    return {
        "managed_count": len(managed),
        "unmanaged_count": len(unmanaged),
        "managed_cost": managed_cost,
        "unmanaged_cost": unmanaged_cost,
        "total_cost": total_cost,
        "planned_count": len(planned),
        "planned_total": planned_total,
        "drift_count": len(drift),
        "drift_total": drift_total_val,
        "drift_resources": drift_resources,
        "iac_sources": iac_sources,
        "teams": teams,
        "total_resources": len(all_rows),
    }


# ── Cloud Account Connect ────────────────────────────────────────────────────

class AWSConnectRequest(BaseModel):
    access_key: str = Field(min_length=16, max_length=128)
    secret_key: str = Field(min_length=1)
    region: str = "us-east-1"
    months: int = Field(default=2, ge=2, le=12)

class AzureConnectRequest(BaseModel):
    subscription_id: str = Field(min_length=36, max_length=36)
    tenant_id: str = Field(min_length=36, max_length=36)
    client_id: str = Field(min_length=36, max_length=36)
    client_secret: str = Field(min_length=1)
    months: int = Field(default=2, ge=2, le=12)

@app.post("/api/connect/aws")
def connect_aws(req: AWSConnectRequest):
    from cloudledger.cloud_connect import fetch_aws_costs
    try:
        csv_paths = fetch_aws_costs(req.access_key, req.secret_key, req.region, req.months)
    except Exception as e:
        logger.error("AWS connect failed: %s", type(e).__name__)
        raise HTTPException(400, f"Failed to fetch AWS costs: {_safe_error(e)}")

    with get_db() as session:
        session.query(Allocation).delete()
        session.query(VarianceReport).delete()
        session.query(Resource).delete()
        session.query(Invoice).delete()
        session.query(RawBillingLine).delete()

    total_inserted = 0
    for path in csv_paths:
        try:
            stats = ingest_focus_csv(path)
            total_inserted += stats.get("rows_inserted", 0)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    return {"rows_inserted": total_inserted, "files": len(csv_paths), "provider": "AWS"}

@app.post("/api/connect/azure")
def connect_azure(req: AzureConnectRequest):
    from cloudledger.cloud_connect import fetch_azure_costs
    try:
        csv_paths = fetch_azure_costs(req.subscription_id, req.tenant_id, req.client_id, req.client_secret, req.months)
        if not csv_paths:
            raise HTTPException(400, "Azure returned no billing data for the requested period.")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Azure connect failed: %s", type(e).__name__)
        raise HTTPException(400, f"Failed to fetch Azure costs: {_safe_error(e)}")

    with get_db() as session:
        session.query(Allocation).delete()
        session.query(VarianceReport).delete()
        session.query(Resource).delete()
        session.query(Invoice).delete()
        session.query(RawBillingLine).delete()

    total_inserted = 0
    for path in csv_paths:
        try:
            stats = ingest_focus_csv(path)
            total_inserted += stats.get("rows_inserted", 0)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    return {"rows_inserted": total_inserted, "files": len(csv_paths), "provider": "Azure"}


def _safe_error(e: Exception) -> str:
    """Return error message with credentials stripped."""
    msg = str(e)
    # Strip anything that looks like an access key or secret
    msg = _re.sub(r'AKIA[A-Z0-9]{12,}', '[REDACTED]', msg)
    msg = _re.sub(r'[A-Za-z0-9/+=]{40,}', '[REDACTED]', msg)
    return msg


# ── GitHub CI/CD Integration ──────────────────────────────────────────────────

@app.get("/api/github/status")
def github_status():
    from cloudledger.config import GITHUB_TOKEN, GITHUB_REPO
    configured = bool(GITHUB_TOKEN and GITHUB_REPO)
    event_count = 0
    if configured:
        with get_db() as session:
            event_count = session.query(func.count(ChangeEvent.id)).filter(
                ChangeEvent.event_type == "github_pr"
            ).scalar() or 0
    return {
        "configured": configured,
        "repo": GITHUB_REPO if configured else None,
        "events_synced": event_count,
    }

@app.post("/api/github/sync")
def github_sync(billing_period: str | None = None):
    from cloudledger.config import GITHUB_TOKEN, GITHUB_REPO
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(400, "GITHUB_TOKEN and GITHUB_REPO must be configured in .env")

    if not billing_period:
        with get_db() as session:
            latest = session.query(func.max(RawBillingLine.billing_period_start)).scalar()
            if not latest:
                raise HTTPException(400, "No billing data uploaded yet")
            billing_period = latest.strftime("%Y-%m")

    from cloudledger.github_sync import sync_github_events
    result = sync_github_events(billing_period)

    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


# ── Historical Trends ────────────────────────────────────────────────────────

@app.get("/api/trends")
def get_trends():
    with get_db() as session:
        inv_rows = (
            session.query(Invoice.billing_period_start, Invoice.total_billed_cost)
            .order_by(Invoice.billing_period_start)
            .all()
        )
        totals = [{"period": r[0].strftime("%Y-%m"), "cost": _f(r[1])} for r in inv_rows]

        svc_rows = (
            session.query(
                Resource.service_name,
                Resource.billing_period_start,
                func.sum(Resource.total_cost),
                func.count(Resource.id),
            )
            .group_by(Resource.service_name, Resource.billing_period_start)
            .order_by(Resource.billing_period_start)
            .all()
        )
        by_service: dict = {}
        for svc, period, cost, count in svc_rows:
            svc_name = svc or "Unknown"
            if svc_name not in by_service:
                by_service[svc_name] = []
            by_service[svc_name].append({
                "period": period.strftime("%Y-%m"),
                "cost": _f(cost),
                "resources": count,
            })

        variance_rows = (
            session.query(
                VarianceReport.prior_period_start,
                VarianceReport.current_period_start,
                VarianceReport.reason_code,
                func.sum(VarianceReport.delta_dollars),
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
            )
            .group_by(
                VarianceReport.prior_period_start,
                VarianceReport.current_period_start,
                VarianceReport.reason_code,
            )
            .order_by(VarianceReport.current_period_start)
            .all()
        )

        period_variances: dict = {}
        for prior, current, reason, delta, abs_delta, count in variance_rows:
            key = f"{prior.strftime('%Y-%m')}_{current.strftime('%Y-%m')}"
            if key not in period_variances:
                period_variances[key] = {
                    "prior_period": prior.strftime("%Y-%m"),
                    "current_period": current.strftime("%Y-%m"),
                    "by_reason": {},
                    "net_change": 0.0,
                    "total_variance": 0.0,
                }
            rc = reason or "other"
            period_variances[key]["by_reason"][rc] = {
                "delta": _f(delta), "abs_delta": _f(abs_delta), "count": count,
            }
            period_variances[key]["net_change"] += _f(delta)
            period_variances[key]["total_variance"] += _f(abs_delta)

        anomaly_rows = (
            session.query(VarianceReport)
            .filter(
                func.abs(VarianceReport.delta_pct) > 50,
                func.abs(VarianceReport.delta_dollars) > 500,
            )
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .limit(20)
            .all()
        )
        anomalies = [{
            "period": v.current_period_start.strftime("%Y-%m"),
            "resource_name": v.resource_name or v.resource_id,
            "service": v.service_name or "Unknown",
            "delta": _f(v.delta_dollars),
            "delta_pct": _f(v.delta_pct),
            "reason": v.reason_code or "unknown",
        } for v in anomaly_rows]

    return {
        "totals": totals,
        "by_service": by_service,
        "variances": list(period_variances.values()),
        "anomalies": anomalies,
    }


@app.post("/api/pipeline/run-all")
def run_pipeline_all():
    """Run variance for all consecutive period pairs."""
    tf_dir = os.path.join(UPLOAD_DIR, "terraform")
    tf_paths = []
    if os.path.isdir(tf_dir):
        tf_paths = [os.path.join(tf_dir, f) for f in os.listdir(tf_dir) if f.endswith(".tfstate")]

    normalize_invoices()
    normalize_resources(terraform_state_paths=tf_paths if tf_paths else None)

    with get_db() as session:
        periods = (
            session.query(distinct(RawBillingLine.billing_period_start))
            .order_by(RawBillingLine.billing_period_start)
            .all()
        )
        period_list = sorted([r[0] for r in periods if r[0]])

    if len(period_list) < 2:
        raise HTTPException(400, "Need at least 2 billing periods")

    results = []
    for i in range(len(period_list) - 1):
        prior = period_list[i].strftime("%Y-%m")
        current = period_list[i + 1].strftime("%Y-%m")
        result = compute_variance(prior, current)
        results.append({"prior": prior, "current": current, **result})

    return {
        "periods": [p.strftime("%Y-%m") for p in period_list],
        "variance_runs": len(results),
        "results": results,
    }


# ── Snowflake-Powered Endpoints ──────────────────────────────────────────────

@app.get("/api/snowflake/status")
def snowflake_status():
    from cloudledger.snowflake_query import is_configured
    configured = is_configured()
    table_count = 0
    if configured:
        try:
            from cloudledger.snowflake_query import query as sf_query
            rows = sf_query("SELECT COUNT(*) AS CNT FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA IN ('RAW','ANALYTICS')")
            table_count = rows[0]["CNT"] if rows else 0
        except Exception:
            pass
    return {"configured": configured, "tables": table_count}

@app.get("/api/snowflake/overview")
def snowflake_overview(prior_period: str, current_period: str):
    _parse_period(prior_period)
    _parse_period(current_period)
    from cloudledger.snowflake_query import get_overview
    return get_overview(prior_period, current_period)

@app.get("/api/snowflake/variance")
def snowflake_variance(current_period: str):
    _parse_period(current_period)
    from cloudledger.snowflake_query import get_variance
    return get_variance(current_period)

@app.get("/api/snowflake/trends")
def snowflake_trends():
    from cloudledger.snowflake_query import get_trends
    return get_trends()

@app.get("/api/snowflake/engineering")
def snowflake_engineering(current_period: str):
    _parse_period(current_period)
    from cloudledger.snowflake_query import get_engineering
    return get_engineering(current_period)


# ── Snowflake Sync ───────────────────────────────────────────────────────────

@app.post("/api/snowflake/sync")
def snowflake_sync(period: str | None = None):
    sf_account = os.environ.get("SNOWFLAKE_ACCOUNT")
    if not sf_account:
        raise HTTPException(400, "SNOWFLAKE_ACCOUNT not configured in environment variables.")
    from cloudledger.snowflake_sync import sync_to_snowflake
    try:
        result = sync_to_snowflake(period)
        return result
    except Exception as e:
        logger.error("Snowflake sync failed: %s", e)
        raise HTTPException(400, f"Snowflake sync failed: {str(e)}")


# ── Cloudly Chat ─────────────────────────────────────────────────────────────

import json as _json

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    screen: str
    screen_data: dict | None = None
    history: list[dict] = []

@app.post("/api/chat")
def cloudly_chat(req: ChatRequest):
    import anthropic

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        raise HTTPException(400, "ANTHROPIC_API_KEY not configured. Add it to .env and restart.")

    # Truncate screen_data for context window
    screen_context = ""
    if req.screen_data:
        raw = _json.dumps(req.screen_data, default=str)
        if len(raw) > 40000:
            truncated = {}
            for k, v in req.screen_data.items():
                if isinstance(v, list) and len(v) > 20:
                    truncated[k] = v[:20]
                    truncated[f"_{k}_note"] = f"Showing 20 of {len(v)} items"
                else:
                    truncated[k] = v
            screen_context = _json.dumps(truncated, default=str)[:40000]
        else:
            screen_context = raw

    try:
        from backend.agent import ask
        result = ask(
            question=req.message,
            screen=req.screen,
            screen_data=screen_context,
            history=req.history,
        )
        return {
            "reply": result["answer"],
            "sources": result.get("sources", []),
        }
    except anthropic.AuthenticationError:
        raise HTTPException(401, "Invalid ANTHROPIC_API_KEY. Check your .env file.")
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(500, "Failed to generate a response. Please try again.")


# ── Serve frontend static files ──────────────────────────────────────────────

import pathlib
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

_FRONTEND_OUT = pathlib.Path(__file__).parent.parent / "frontend" / "out"

if _FRONTEND_OUT.exists():
    app.mount("/_next", StaticFiles(directory=str(_FRONTEND_OUT / "_next")), name="next_static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = _FRONTEND_OUT / full_path
        if file_path.is_file():
            return HTMLResponse(file_path.read_text())
        index = _FRONTEND_OUT / "index.html"
        if index.exists():
            return HTMLResponse(index.read_text())
        raise HTTPException(404, "Not found")
