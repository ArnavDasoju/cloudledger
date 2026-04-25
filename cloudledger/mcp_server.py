"""CloudLedger MCP Server — exposes billing analysis tools to any MCP client."""

from datetime import date
from decimal import Decimal

from mcp.server.fastmcp import FastMCP

from cloudledger.database import (
    get_db, RawBillingLine, Invoice, Resource, VarianceReport, ChangeEvent,
)
from sqlalchemy import func, distinct

mcp = FastMCP("CloudLedger")


def _f(v) -> float:
    if v is None:
        return 0.0
    return float(v)


@mcp.tool()
def get_billing_overview(prior_period: str, current_period: str) -> dict:
    """Get high-level billing overview comparing two months.

    Args:
        prior_period: Prior month in YYYY-MM format (e.g. 2024-02)
        current_period: Current month in YYYY-MM format (e.g. 2024-03)
    """
    prior_date = date.fromisoformat(f"{prior_period}-01")
    current_date = date.fromisoformat(f"{current_period}-01")

    with get_db() as session:
        prior_total = _f(session.query(func.sum(Invoice.total_billed_cost)).filter(
            Invoice.billing_period_start == prior_date).scalar())
        current_total = _f(session.query(func.sum(Invoice.total_billed_cost)).filter(
            Invoice.billing_period_start == current_date).scalar())

    delta = current_total - prior_total
    pct = (delta / prior_total * 100) if prior_total > 0 else 0
    return {
        "prior_period": prior_period,
        "current_period": current_period,
        "prior_total": prior_total,
        "current_total": current_total,
        "delta": delta,
        "change_pct": round(pct, 1),
    }


@mcp.tool()
def get_variance_by_resource(current_period: str, limit: int = 20) -> dict:
    """Get resource-level variance details for a billing period, sorted by largest impact.

    Args:
        current_period: Month in YYYY-MM format
        limit: Max resources to return (default 20)
    """
    current_date = date.fromisoformat(f"{current_period}-01")

    with get_db() as session:
        rows = (
            session.query(VarianceReport)
            .filter(VarianceReport.current_period_start == current_date)
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .limit(limit)
            .all()
        )
        resources = []
        for v in rows:
            resources.append({
                "resource_name": v.resource_name or v.resource_id,
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

        total_variance = _f(session.query(func.sum(func.abs(VarianceReport.delta_dollars))).filter(
            VarianceReport.current_period_start == current_date).scalar())
        net_change = _f(session.query(func.sum(VarianceReport.delta_dollars)).filter(
            VarianceReport.current_period_start == current_date).scalar())

    return {
        "period": current_period,
        "net_change": net_change,
        "total_variance": total_variance,
        "resource_count": len(resources),
        "resources": resources,
    }


@mcp.tool()
def get_root_cause_summary(current_period: str) -> dict:
    """Get variance broken down by root cause category (planned, drift, usage, edge cases).

    Args:
        current_period: Month in YYYY-MM format
    """
    current_date = date.fromisoformat(f"{current_period}-01")

    drift_codes = {"drift", "orphan_sdk_created", "orphan_unknown", "legacy_untracked", "non_terraform_iac"}
    usage_codes = {"usage_growth", "new_resource", "removed_resource", "price_change", "steady_state"}

    with get_db() as session:
        rows = (
            session.query(
                VarianceReport.reason_code,
                func.sum(VarianceReport.delta_dollars),
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
            )
            .filter(VarianceReport.current_period_start == current_date)
            .group_by(VarianceReport.reason_code)
            .all()
        )

    planned = {"delta": 0.0, "count": 0}
    drift = {"delta": 0.0, "count": 0}
    usage = {"delta": 0.0, "count": 0}
    reasons = {}

    for code, delta, abs_delta, count in rows:
        rc = code or "other"
        reasons[rc] = {"delta": _f(delta), "abs_delta": _f(abs_delta), "count": count}
        if rc == "planned":
            planned["delta"] += _f(delta)
            planned["count"] += count
        elif rc in drift_codes:
            drift["delta"] += _f(delta)
            drift["count"] += count
        elif rc in usage_codes:
            usage["delta"] += _f(delta)
            usage["count"] += count

    return {
        "period": current_period,
        "planned": planned,
        "drift": drift,
        "usage": usage,
        "all_reason_codes": reasons,
    }


@mcp.tool()
def get_iac_coverage(current_period: str) -> dict:
    """Get Infrastructure-as-Code coverage metrics — how much spend is managed by Terraform.

    Args:
        current_period: Month in YYYY-MM format
    """
    current_date = date.fromisoformat(f"{current_period}-01")

    with get_db() as session:
        total = session.query(func.count(Resource.id)).filter(
            Resource.billing_period_start == current_date).scalar() or 0
        managed = session.query(func.count(Resource.id)).filter(
            Resource.billing_period_start == current_date,
            Resource.in_terraform_state == True).scalar() or 0
        managed_cost = _f(session.query(func.sum(Resource.total_cost)).filter(
            Resource.billing_period_start == current_date,
            Resource.in_terraform_state == True).scalar())
        total_cost = _f(session.query(func.sum(Resource.total_cost)).filter(
            Resource.billing_period_start == current_date).scalar())

        # Top unmanaged by cost
        unmanaged = (
            session.query(Resource)
            .filter(Resource.billing_period_start == current_date, Resource.in_terraform_state == False)
            .order_by(Resource.total_cost.desc())
            .limit(10)
            .all()
        )
        unmanaged_list = [{"name": r.resource_name or r.resource_id, "service": r.service_name, "cost": _f(r.total_cost)} for r in unmanaged]

    return {
        "period": current_period,
        "total_resources": total,
        "managed_resources": managed,
        "coverage_pct": round(managed / total * 100, 1) if total > 0 else 0,
        "managed_cost": managed_cost,
        "total_cost": total_cost,
        "cost_coverage_pct": round(managed_cost / total_cost * 100, 1) if total_cost > 0 else 0,
        "top_unmanaged": unmanaged_list,
    }


@mcp.tool()
def get_available_periods() -> dict:
    """List all billing periods that have been uploaded and analyzed."""
    with get_db() as session:
        periods = (
            session.query(distinct(RawBillingLine.billing_period_start))
            .order_by(RawBillingLine.billing_period_start)
            .all()
        )
        period_list = [r[0].strftime("%Y-%m") for r in periods if r[0]]

        # Get total cost per period
        totals = []
        for p in period_list:
            d = date.fromisoformat(f"{p}-01")
            inv = session.query(Invoice).filter(Invoice.billing_period_start == d).first()
            totals.append({"period": p, "total_cost": _f(inv.total_billed_cost) if inv else 0.0})

    return {"periods": totals}


@mcp.tool()
def get_anomalies(min_delta_pct: float = 50, min_delta_dollars: float = 500) -> dict:
    """Find cost anomalies — resources with unusually large changes.

    Args:
        min_delta_pct: Minimum percentage change to flag (default 50%)
        min_delta_dollars: Minimum dollar impact to flag (default $500)
    """
    with get_db() as session:
        rows = (
            session.query(VarianceReport)
            .filter(
                func.abs(VarianceReport.delta_pct) > min_delta_pct,
                func.abs(VarianceReport.delta_dollars) > min_delta_dollars,
            )
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .limit(20)
            .all()
        )
        anomalies = [{
            "resource_name": v.resource_name or v.resource_id,
            "service": v.service_name or "Unknown",
            "period": v.current_period_start.strftime("%Y-%m"),
            "prior_cost": _f(v.prior_cost),
            "current_cost": _f(v.current_cost),
            "delta": _f(v.delta_dollars),
            "delta_pct": _f(v.delta_pct),
            "reason": v.reason_code,
            "evidence": v.evidence,
        } for v in rows]

    return {"anomalies": anomalies, "count": len(anomalies)}


if __name__ == "__main__":
    mcp.run()
