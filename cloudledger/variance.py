"""Variance engine — computes month-over-month cost variance and assigns reason codes.

Supports extended reason codes for edge cases:
- planned, orphan_sdk_created, orphan_unknown, usage_growth, new_resource, removed_resource, price_change
- savings_plan_allocation, ri_coverage_shift, cross_service_transfer
- marketplace_subscription, spot_price_volatility, credit_applied
- tag_propagation_delay
"""

import calendar
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, func

from cloudledger.database import get_db, Resource, ChangeEvent, VarianceReport, RawBillingLine

logger = logging.getLogger(__name__)


def _days_in_month(d: date) -> int:
    """Return the number of days in the month of the given date."""
    return calendar.monthrange(d.year, d.month)[1]

# Charge types that map to specific reason codes
EDGE_CASE_CHARGE_TYPES = {
    "SavingsPlanCoveredUsage": "savings_plan_allocation",
    "SavingsPlanNegation": "savings_plan_allocation",
    "SavingsPlanRecurringFee": "savings_plan_allocation",
    "SavingsPlanUpfrontFee": "savings_plan_allocation",
    "RIFee": "ri_coverage_shift",
    "DiscountedUsage": "ri_coverage_shift",
    "Credit": "credit_applied",
    "Refund": "credit_applied",
    "BundledDiscount": "credit_applied",
}

MARKETPLACE_INDICATORS = ["marketplace", "mp-", "aws marketplace"]
SPOT_INDICATORS = ["spot", "spotusage"]
DATA_TRANSFER_INDICATORS = ["datatransfer", "data transfer", "cloudfront", "nat gateway"]


def _detect_charge_type_reason(charge_types: List[str], description: str) -> Optional[str]:
    """Detect edge-case reason code from charge types and description."""
    desc_lower = (description or "").lower()

    for ct in charge_types:
        if ct in EDGE_CASE_CHARGE_TYPES:
            return EDGE_CASE_CHARGE_TYPES[ct]

    # Marketplace detection
    if any(ind in desc_lower for ind in MARKETPLACE_INDICATORS):
        return "marketplace_subscription"

    # Spot instance detection
    if any(ind in desc_lower for ind in SPOT_INDICATORS):
        return "spot_price_volatility"
    for ct in charge_types:
        if "spot" in (ct or "").lower():
            return "spot_price_volatility"

    # Data transfer detection
    if any(ind in desc_lower for ind in DATA_TRANSFER_INDICATORS):
        return "cross_service_transfer"

    return None


def _build_evidence_chain(
    reason_code: str,
    rid: str,
    prior_cost: Decimal,
    current_cost: Decimal,
    delta_pct: Decimal,
    in_tf: bool,
    iac_source: str,
    tf_module: Optional[str],
    change_event: Optional[object],
    charge_types: List[str],
    is_excluded: bool,
) -> dict:
    """Build a structured evidence_chain JSONB for audit trail."""
    chain = {
        "reason_code": reason_code,
        "classification_steps": [],
        "inputs": {
            "resource_id": rid,
            "prior_cost": float(prior_cost),
            "current_cost": float(current_cost),
            "delta_pct": float(delta_pct) if delta_pct is not None else None,
            "in_iac": in_tf,
            "iac_source": iac_source,
            "iac_module": tf_module,
            "charge_types": charge_types,
        },
    }

    steps = chain["classification_steps"]

    # Step 1: Edge case check
    if is_excluded:
        steps.append({
            "step": "edge_case_detection",
            "result": reason_code,
            "detail": f"Charge types {charge_types} matched edge case pattern",
        })
        return chain

    # Step 2: New/removed check
    if reason_code == "new_resource":
        steps.append({
            "step": "period_presence",
            "result": "new_resource",
            "detail": "Resource not found in prior period",
        })
        return chain

    if reason_code == "removed_resource":
        steps.append({
            "step": "period_presence",
            "result": "removed_resource",
            "detail": "Resource not found in current period",
        })
        return chain

    # Step 3: IaC check
    steps.append({
        "step": "iac_lookup",
        "result": "managed" if in_tf else "unmanaged",
        "detail": f"Source: {iac_source}, module: {tf_module}" if in_tf else "Not found in any IaC state",
    })

    # Step 4: Change event check
    if change_event:
        ce = change_event
        steps.append({
            "step": "change_event_match",
            "result": "matched",
            "detail": f"PR #{getattr(ce, 'pr_number', 'N/A')}: {getattr(ce, 'pr_title', 'N/A')}",
        })
    else:
        steps.append({
            "step": "change_event_match",
            "result": "no_match",
            "detail": "No change events found within window",
        })

    # Step 5: Final classification
    steps.append({
        "step": "classification",
        "result": reason_code,
        "detail": f"Delta {float(delta_pct):.1f}%, IaC={in_tf}, change_event={'yes' if change_event else 'no'}" if delta_pct is not None else f"Delta N/A (new baseline), IaC={in_tf}, change_event={'yes' if change_event else 'no'}",
    })

    return chain


def compute_variance(prior_period: str, current_period: str, baseline_mode: str = "prior_month") -> Dict:
    """Compute variance between two billing periods (format: 'YYYY-MM').

    baseline_mode: 'prior_month' (default), 'rolling_3m', or 'same_month_last_year'.
    Returns summary dict with counts by reason_code.
    """
    prior_start = date.fromisoformat(f"{prior_period}-01")
    current_start = date.fromisoformat(f"{current_period}-01")

    with get_db() as session:
        # Load current resources
        current_resources = {
            r.resource_id: r
            for r in session.query(Resource)
            .filter(Resource.billing_period_start == current_start)
            .all()
        }

        # Load baseline resources based on mode
        if baseline_mode == "same_month_last_year":
            baseline_start = date(current_start.year - 1, current_start.month, 1)
            prior_resources = {
                r.resource_id: r
                for r in session.query(Resource)
                .filter(Resource.billing_period_start == baseline_start)
                .all()
            }
            prior_start = baseline_start
        elif baseline_mode == "rolling_3m":
            # Average costs from 3 months before current
            month_costs: Dict[str, list] = {}
            for offset in [1, 2, 3]:
                m = current_start.month - offset
                y = current_start.year
                while m <= 0:
                    m += 12
                    y -= 1
                m_start = date(y, m, 1)
                for r in session.query(Resource).filter(Resource.billing_period_start == m_start).all():
                    if r.resource_id not in month_costs:
                        month_costs[r.resource_id] = {"costs": [], "ref": r}
                    month_costs[r.resource_id]["costs"].append(Decimal(str(r.total_cost or 0)))

            # Create synthetic prior_resources with averaged costs
            class _AvgResource:
                def __init__(self, ref, avg_cost):
                    self.resource_id = ref.resource_id
                    self.resource_name = ref.resource_name
                    self.service_name = ref.service_name
                    self.team = ref.team
                    self.cost_center = ref.cost_center
                    self.in_terraform_state = ref.in_terraform_state
                    self.terraform_module = ref.terraform_module
                    self.iac_source = ref.iac_source
                    self.total_cost = avg_cost
                    self.service_category = ref.service_category
                    self.region = ref.region

            prior_resources = {}
            for rid, data in month_costs.items():
                avg = sum(data["costs"]) / len(data["costs"])
                prior_resources[rid] = _AvgResource(data["ref"], avg)
        else:
            # Default: prior month
            prior_resources = {
                r.resource_id: r
                for r in session.query(Resource)
                .filter(Resource.billing_period_start == prior_start)
                .all()
            }

        all_resource_ids = set(prior_resources.keys()) | set(current_resources.keys())

        # Load charge types per resource for edge case detection
        charge_type_map: Dict[str, List[str]] = {}
        description_map: Dict[str, str] = {}
        ct_rows = (
            session.query(
                RawBillingLine.resource_id,
                RawBillingLine.charge_type,
                RawBillingLine.description,
            )
            .filter(RawBillingLine.billing_period_start == current_start)
            .all()
        )
        for row in ct_rows:
            if row.resource_id:
                if row.resource_id not in charge_type_map:
                    charge_type_map[row.resource_id] = []
                if row.charge_type and row.charge_type not in charge_type_map[row.resource_id]:
                    charge_type_map[row.resource_id].append(row.charge_type)
                if row.description and row.resource_id not in description_map:
                    description_map[row.resource_id] = row.description

        # Load change events near the current billing period
        window_start = current_start - timedelta(days=7)
        window_end = current_start + timedelta(days=7)
        change_events = (
            session.query(ChangeEvent)
            .filter(
                and_(
                    ChangeEvent.event_date >= window_start,
                    ChangeEvent.event_date <= window_end,
                )
            )
            .all()
        )
        change_event_resources = set()
        change_event_map = {}
        for ce in change_events:
            change_event_resources.add(ce.resource_id)
            change_event_map[ce.resource_id] = ce
            if "/" in ce.resource_id:
                short_id = ce.resource_id.rsplit("/", 1)[-1]
                change_event_resources.add(short_id)
                change_event_map[short_id] = ce
            elif ":" in ce.resource_id:
                short_id = ce.resource_id.rsplit(":", 1)[-1]
                change_event_resources.add(short_id)
                change_event_map[short_id] = ce

        # Clear existing variance rows for this period pair
        session.query(VarianceReport).filter(
            and_(
                VarianceReport.prior_period_start == prior_start,
                VarianceReport.current_period_start == current_start,
            )
        ).delete()

        # Day-length normalization: adjust prior cost to same-length month
        prior_days = _days_in_month(prior_start)
        current_days = _days_in_month(current_start)
        day_ratio = Decimal(str(current_days)) / Decimal(str(prior_days))

        counts = {}
        for rid in all_resource_ids:
            prior_r = prior_resources.get(rid)
            current_r = current_resources.get(rid)

            prior_cost_raw = Decimal(str(prior_r.total_cost)) if prior_r and prior_r.total_cost else Decimal("0")
            current_cost = Decimal(str(current_r.total_cost)) if current_r and current_r.total_cost else Decimal("0")

            # Normalize prior cost to current month's day count for fair comparison
            prior_cost_normalized = prior_cost_raw * day_ratio if prior_cost_raw > 0 else Decimal("0")

            # Raw delta (what the bill actually shows)
            delta_dollars = current_cost - prior_cost_raw
            # Normalized delta (actual change after adjusting for month length)
            delta_normalized = current_cost - prior_cost_normalized

            delta_pct = (
                (delta_dollars / prior_cost_raw * 100) if prior_cost_raw != 0
                else None
            )
            # Normalized percentage — the real change beyond month-length effects
            delta_pct_normalized = (
                (delta_normalized / prior_cost_normalized * 100) if prior_cost_normalized > 0
                else delta_pct
            )

            # Store raw prior for the report (what user sees on invoice)
            prior_cost = prior_cost_raw

            ref = current_r or prior_r
            in_tf = ref.in_terraform_state if ref else False
            iac_source = getattr(ref, "iac_source", None) or ("terraform" if in_tf else "none")
            tf_module = ref.terraform_module if ref else None
            has_change_event = rid in change_event_resources
            charge_types = charge_type_map.get(rid, [])
            description = description_map.get(rid, "")

            # --- Edge case detection (Category 3) ---
            is_excluded = False
            edge_reason = _detect_charge_type_reason(charge_types, description)

            # Use normalized delta for classification (ignore month-length noise)
            # but store raw delta for reporting
            abs_norm_pct = abs(float(delta_pct_normalized)) if delta_pct_normalized is not None else 0

            if edge_reason:
                reason_code = edge_reason
                is_excluded = True
            elif rid not in prior_resources:
                reason_code = "new_resource"
            elif rid not in current_resources:
                reason_code = "removed_resource"
            elif in_tf and has_change_event:
                reason_code = "planned"
            elif not in_tf:
                has_tags = bool(ref and ref.team)
                tags = {}
                if ref and hasattr(ref, 'tags') and ref.tags:
                    tags = ref.tags if isinstance(ref.tags, dict) else {}

                is_non_tf_iac = False
                if tags:
                    for tag_key in ('managed_by', 'managed-by', 'iac_tool', 'CreatedBy'):
                        val = tags.get(tag_key, '').lower()
                        if val in ('cloudformation', 'cdk', 'pulumi', 'serverless'):
                            is_non_tf_iac = True
                            break
                    if 'aws:cloudformation:stack-name' in tags:
                        is_non_tf_iac = True

                if is_non_tf_iac:
                    reason_code = "non_terraform_iac"
                elif has_tags:
                    reason_code = "orphan_sdk_created"
                elif prior_cost > 0 and current_cost < 200:
                    reason_code = "legacy_untracked"
                else:
                    reason_code = "orphan_unknown"
            elif in_tf and not has_change_event and abs_norm_pct > 5:
                # Genuine usage growth beyond month-length noise
                reason_code = "usage_growth"
            elif in_tf and not has_change_event and abs_norm_pct <= 5:
                # Within normal month-length variation — steady state
                reason_code = "steady_state"
            else:
                reason_code = "price_change"

            # Confidence score
            if is_excluded:
                confidence = Decimal("0.90")
            elif reason_code == "non_terraform_iac":
                confidence = Decimal("0.85")
            elif reason_code == "orphan_sdk_created":
                confidence = Decimal("0.70")
            elif reason_code == "legacy_untracked":
                confidence = Decimal("0.60")
            elif reason_code == "orphan_unknown":
                confidence = Decimal("0.50")
            elif in_tf:
                confidence = Decimal("0.95")
            elif ref and ref.team:
                confidence = Decimal("0.70")
            else:
                confidence = Decimal("0.50")

            # Build human-readable evidence string
            evidence_parts = []
            if is_excluded:
                evidence_parts.append(f"Edge case: {reason_code} (charge_types: {', '.join(charge_types)})")
            if reason_code == "planned":
                ce = change_event_map.get(rid)
                if ce:
                    evidence_parts.append(f"PR #{ce.pr_number}: {ce.pr_title}" if ce.pr_number else ce.description or "terraform apply")
            if reason_code == "steady_state":
                evidence_parts.append(f"Day-adjusted delta is {float(delta_pct_normalized or 0):.1f}% (within normal range for {prior_days}→{current_days} day month)")
            if reason_code == "usage_growth":
                evidence_parts.append(f"Day-adjusted growth of {float(delta_pct_normalized or 0):.1f}% exceeds normal variation")
            if reason_code == "new_resource":
                svc = ref.service_name if ref else "Unknown"
                team = ref.team if ref else None
                evidence_parts.append(f"New {svc} resource" + (f" (team: {team})" if team else "") + f" costing {float(current_cost):,.0f}/mo")
            if in_tf:
                evidence_parts.append(f"Managed by {iac_source} ({tf_module})")
            if not in_tf and current_r and not is_excluded:
                evidence_parts.append("Not in any IaC state — possible drift")
            evidence = "; ".join(evidence_parts) if evidence_parts else None

            # Build structured evidence chain (Category 1, Item 1)
            ce_obj = change_event_map.get(rid)
            evidence_chain = _build_evidence_chain(
                reason_code=reason_code,
                rid=rid,
                prior_cost=prior_cost,
                current_cost=current_cost,
                delta_pct=delta_pct,
                in_tf=in_tf,
                iac_source=iac_source,
                tf_module=tf_module,
                change_event=ce_obj,
                charge_types=charge_types,
                is_excluded=is_excluded,
            )

            # PR info
            pr_number = ce_obj.pr_number if ce_obj else None
            pr_author = ce_obj.pr_author if ce_obj else None

            vr = VarianceReport(
                resource_id=rid,
                resource_name=ref.resource_name if ref else None,
                service_name=ref.service_name if ref else None,
                team=ref.team if ref else None,
                cost_center=ref.cost_center if ref else None,
                prior_period_start=prior_start,
                current_period_start=current_start,
                prior_cost=prior_cost,
                current_cost=current_cost,
                delta_dollars=delta_dollars,
                delta_pct=round(delta_pct, 2) if delta_pct is not None else Decimal("0"),
                reason_code=reason_code,
                confidence_score=confidence,
                evidence=evidence,
                evidence_chain=evidence_chain,
                pr_number=pr_number,
                pr_author=pr_author,
                iac_source=iac_source,
                in_terraform_state=in_tf,
                reviewed=False,
                excluded=is_excluded,
            )
            session.add(vr)

            counts[reason_code] = counts.get(reason_code, 0) + 1

    by_reason = {}
    total_delta = Decimal("0")
    attributed_count = 0
    total_count = sum(counts.values())

    with get_db() as session:
        for vr in session.query(VarianceReport).filter(
            and_(VarianceReport.prior_period_start == prior_start, VarianceReport.current_period_start == current_start)
        ).all():
            rc = vr.reason_code
            if rc not in by_reason:
                by_reason[rc] = {"count": 0, "dollars": Decimal("0")}
            by_reason[rc]["count"] += 1
            by_reason[rc]["dollars"] += Decimal(str(vr.delta_dollars or 0))
            total_delta += Decimal(str(vr.delta_dollars or 0))
            if vr.confidence_score and float(vr.confidence_score) >= 0.70:
                attributed_count += 1

    attribution_coverage_pct = round(attributed_count / total_count * 100, 2) if total_count else 0

    summary = {
        "total_delta": float(total_delta),
        "by_reason": {k: {"count": v["count"], "dollars": float(v["dollars"])} for k, v in by_reason.items()},
        "attribution_coverage_pct": float(attribution_coverage_pct),
    }

    logger.info("Variance computed: %d rows, attribution_coverage=%.1f%%", total_count, attribution_coverage_pct)
    for code, n in sorted(counts.items()):
        logger.info("  %s: %d", code, n)
    return summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m cloudledger.variance <prior-period> <current-period>")
        sys.exit(1)
    prior = sys.argv[1]
    current = sys.argv[2]
    compute_variance(prior, current)
