"""Database tools that Claude can call via tool-use to answer data questions."""

import logging
from typing import Dict, List, Optional

from sqlalchemy import func, distinct

from cloudledger.database import get_db, RawBillingLine, Invoice, Resource, VarianceReport

logger = logging.getLogger(__name__)


def _f(v) -> float:
    if v is None:
        return 0.0
    return float(v)


# ── Tool definitions (Anthropic tool-use format) ──────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "query_spend_by_service",
        "description": "Get total cloud spend broken down by service for a billing period. Use this when the user asks about spend, costs, or which services cost the most.",
        "input_schema": {
            "type": "object",
            "properties": {
                "billing_period": {
                    "type": "string",
                    "description": "Billing period in YYYY-MM format (e.g. 2025-02)",
                },
            },
            "required": ["billing_period"],
        },
    },
    {
        "name": "query_top_variance",
        "description": "Get the resources with the largest cost changes between two periods. Use this when the user asks about increases, decreases, what changed, or biggest movers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "billing_period": {
                    "type": "string",
                    "description": "Current billing period in YYYY-MM format",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (default 10)",
                    "default": 10,
                },
                "direction": {
                    "type": "string",
                    "enum": ["increases", "decreases", "both"],
                    "description": "Filter to only increases, only decreases, or both (default both)",
                    "default": "both",
                },
            },
            "required": ["billing_period"],
        },
    },
    {
        "name": "query_resources_by_filter",
        "description": "Search for resources matching specific criteria: service name, team, reason code, cost threshold, or IaC status. Use this when the user asks to filter or find specific resources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "billing_period": {
                    "type": "string",
                    "description": "Billing period in YYYY-MM format",
                },
                "service": {
                    "type": "string",
                    "description": "Filter by service name (partial match, case-insensitive)",
                },
                "team": {
                    "type": "string",
                    "description": "Filter by team tag",
                },
                "reason_code": {
                    "type": "string",
                    "description": "Filter by variance reason code (e.g. orphan_unknown, usage_growth)",
                },
                "min_cost": {
                    "type": "number",
                    "description": "Minimum current cost threshold",
                },
                "in_terraform": {
                    "type": "boolean",
                    "description": "Filter by IaC management status",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
            },
            "required": ["billing_period"],
        },
    },
    {
        "name": "query_drift_summary",
        "description": "Get a summary of infrastructure drift: unmanaged resources, their cost, and recommended actions. Use this when the user asks about drift, unmanaged resources, or IaC coverage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "billing_period": {
                    "type": "string",
                    "description": "Billing period in YYYY-MM format",
                },
            },
            "required": ["billing_period"],
        },
    },
    {
        "name": "query_cost_trend",
        "description": "Get cost trends across all available billing periods, optionally filtered by service. Use this when the user asks about trends, growth, trajectory, or historical spend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Optional: filter to a specific service name",
                },
            },
            "required": [],
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

def _execute_tool(name: str, inputs: Dict) -> str:
    """Execute a tool by name and return the result as a formatted string."""
    try:
        if name == "query_spend_by_service":
            return _tool_spend_by_service(inputs["billing_period"])
        elif name == "query_top_variance":
            return _tool_top_variance(
                inputs["billing_period"],
                inputs.get("limit", 10),
                inputs.get("direction", "both"),
            )
        elif name == "query_resources_by_filter":
            return _tool_resources_by_filter(inputs)
        elif name == "query_drift_summary":
            return _tool_drift_summary(inputs["billing_period"])
        elif name == "query_cost_trend":
            return _tool_cost_trend(inputs.get("service"))
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        logger.error("Tool execution failed for %s: %s", name, e)
        return f"Error executing {name}: {str(e)}"


def _tool_spend_by_service(period: str) -> str:
    from datetime import date
    period_date = date.fromisoformat(f"{period}-01")

    with get_db() as session:
        rows = (
            session.query(
                Resource.service_name,
                func.sum(Resource.total_cost),
                func.count(Resource.id),
            )
            .filter(Resource.billing_period_start == period_date)
            .group_by(Resource.service_name)
            .order_by(func.sum(Resource.total_cost).desc())
            .all()
        )

        if not rows:
            return f"No data found for period {period}."

        total = sum(_f(r[1]) for r in rows)
        lines = [f"Total spend for {period}: ${total:,.2f}\n"]
        for svc, cost, count in rows:
            pct = (_f(cost) / total * 100) if total > 0 else 0
            lines.append(f"- {svc or 'Unknown'}: ${_f(cost):,.2f} ({pct:.1f}%, {count} resources)")

        return "\n".join(lines)


def _tool_top_variance(period: str, limit: int, direction: str) -> str:
    from datetime import date
    period_date = date.fromisoformat(f"{period}-01")

    with get_db() as session:
        query = session.query(VarianceReport).filter(
            VarianceReport.current_period_start == period_date
        )
        if direction == "increases":
            query = query.filter(VarianceReport.delta_dollars > 0)
        elif direction == "decreases":
            query = query.filter(VarianceReport.delta_dollars < 0)

        rows = query.order_by(func.abs(VarianceReport.delta_dollars).desc()).limit(limit).all()

        if not rows:
            return f"No variance data found for period {period}."

        lines = [f"Top {len(rows)} cost changes for {period}:\n"]
        for v in rows:
            delta = _f(v.delta_dollars)
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"- {v.resource_name or v.resource_id}: {sign}${delta:,.2f} "
                f"({v.service_name or 'Unknown'}, reason: {v.reason_code}, "
                f"team: {v.team or 'untagged'}, IaC: {'yes' if v.in_terraform_state else 'no'})"
            )

        return "\n".join(lines)


def _tool_resources_by_filter(inputs: Dict) -> str:
    from datetime import date
    period = inputs["billing_period"]
    period_date = date.fromisoformat(f"{period}-01")

    with get_db() as session:
        # Query from variance_report for richer data
        query = session.query(VarianceReport).filter(
            VarianceReport.current_period_start == period_date
        )

        if inputs.get("service"):
            query = query.filter(VarianceReport.service_name.ilike(f"%{inputs['service']}%"))
        if inputs.get("team"):
            query = query.filter(VarianceReport.team == inputs["team"])
        if inputs.get("reason_code"):
            query = query.filter(VarianceReport.reason_code == inputs["reason_code"])
        if inputs.get("min_cost") is not None:
            query = query.filter(VarianceReport.current_cost >= inputs["min_cost"])
        if inputs.get("in_terraform") is not None:
            query = query.filter(VarianceReport.in_terraform_state == inputs["in_terraform"])

        limit = inputs.get("limit", 20)
        rows = query.order_by(func.abs(VarianceReport.delta_dollars).desc()).limit(limit).all()

        if not rows:
            return f"No resources found matching the filters for {period}."

        lines = [f"Found {len(rows)} resources matching filters:\n"]
        for v in rows:
            delta = _f(v.delta_dollars)
            lines.append(
                f"- {v.resource_name or v.resource_id}: "
                f"${_f(v.current_cost):,.2f}/mo (delta: {'+' if delta >= 0 else ''}${delta:,.2f}, "
                f"reason: {v.reason_code}, service: {v.service_name or 'Unknown'}, "
                f"team: {v.team or 'untagged'})"
            )

        return "\n".join(lines)


def _tool_drift_summary(period: str) -> str:
    from datetime import date
    period_date = date.fromisoformat(f"{period}-01")

    drift_codes = {"drift", "orphan_sdk_created", "orphan_unknown", "legacy_untracked", "non_terraform_iac"}

    with get_db() as session:
        total = session.query(func.count(VarianceReport.id)).filter(
            VarianceReport.current_period_start == period_date
        ).scalar() or 0

        drift_rows = (
            session.query(VarianceReport)
            .filter(
                VarianceReport.current_period_start == period_date,
                VarianceReport.reason_code.in_(list(drift_codes)),
            )
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        managed = total - len(drift_rows)
        drift_cost = sum(_f(v.current_cost) for v in drift_rows)
        managed_cost_val = sum(
            _f(r[0]) for r in session.query(func.sum(VarianceReport.current_cost)).filter(
                VarianceReport.current_period_start == period_date,
                VarianceReport.in_terraform_state == True,
            ).all()
        )

        lines = [
            f"Infrastructure drift summary for {period}:\n",
            f"- Total resources: {total}",
            f"- IaC-managed: {managed} (${managed_cost_val:,.2f})",
            f"- Drift/unmanaged: {len(drift_rows)} (${drift_cost:,.2f})",
            f"- Coverage: {(managed / total * 100):.0f}%" if total > 0 else "- Coverage: N/A",
            "",
            "Drift resources by reason:",
        ]

        by_reason: Dict[str, list] = {}
        for v in drift_rows:
            rc = v.reason_code or "unknown"
            if rc not in by_reason:
                by_reason[rc] = []
            by_reason[rc].append(v)

        for rc, resources in sorted(by_reason.items(), key=lambda x: -len(x[1])):
            lines.append(f"\n  {rc} ({len(resources)}):")
            for v in resources[:5]:
                lines.append(f"    - {v.resource_name or v.resource_id}: ${_f(v.current_cost):,.2f}/mo")

        return "\n".join(lines)


def _tool_cost_trend(service: Optional[str] = None) -> str:
    with get_db() as session:
        if service:
            rows = (
                session.query(
                    Resource.billing_period_start,
                    func.sum(Resource.total_cost),
                    func.count(Resource.id),
                )
                .filter(Resource.service_name.ilike(f"%{service}%"))
                .group_by(Resource.billing_period_start)
                .order_by(Resource.billing_period_start)
                .all()
            )
            label = f"Cost trend for {service}"
        else:
            rows = (
                session.query(
                    Invoice.billing_period_start,
                    Invoice.total_billed_cost,
                )
                .order_by(Invoice.billing_period_start)
                .all()
            )
            label = "Total cost trend"

        if not rows:
            return "No historical data available."

        lines = [f"{label}:\n"]
        prev_cost = None
        for row in rows:
            period = row[0].strftime("%Y-%m")
            cost = _f(row[1])
            if prev_cost is not None and prev_cost > 0:
                change = ((cost - prev_cost) / prev_cost) * 100
                lines.append(f"- {period}: ${cost:,.2f} ({'+' if change >= 0 else ''}{change:.1f}% MoM)")
            else:
                lines.append(f"- {period}: ${cost:,.2f}")
            prev_cost = cost

        return "\n".join(lines)
