"""Anomaly detection for billing variance data."""

import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func

from cloudledger.database import get_db, VarianceReport

logger = logging.getLogger(__name__)


def detect_anomalies(
    billing_period: str,
    min_delta_pct: float = 50,
    min_delta_dollars: float = 500,
) -> List[Dict]:
    """Detect cost anomalies for a billing period.

    An anomaly is a resource with an unusually large cost change:
    - delta_pct > min_delta_pct (default 50%)
    - abs(delta_dollars) > min_delta_dollars (default $500)

    Returns list of anomaly dicts sorted by severity (highest first).
    """
    period_start = date.fromisoformat(f"{billing_period}-01")

    with get_db() as session:
        from sqlalchemy import or_
        rows = (
            session.query(VarianceReport)
            .filter(
                VarianceReport.current_period_start == period_start,
                func.abs(VarianceReport.delta_dollars) > min_delta_dollars,
                or_(
                    func.abs(VarianceReport.delta_pct) > min_delta_pct,
                    VarianceReport.reason_code.in_(["new_resource", "removed_resource"]),
                ),
            )
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .all()
        )

        anomalies = []
        for v in rows:
            delta = float(v.delta_dollars or 0)
            delta_pct = float(v.delta_pct or 0)
            # Severity = normalized score combining magnitude and percentage
            severity = abs(delta) * (1 + abs(delta_pct) / 100)

            anomalies.append({
                "resource_id": v.resource_id,
                "resource_name": v.resource_name or v.resource_id,
                "service": v.service_name or "Unknown",
                "prior_cost": float(v.prior_cost or 0),
                "current_cost": float(v.current_cost or 0),
                "delta": delta,
                "delta_pct": delta_pct,
                "reason_code": v.reason_code or "unknown",
                "team": v.team,
                "evidence": v.evidence,
                "severity": severity,
            })

    # Sort by severity descending
    anomalies.sort(key=lambda a: a["severity"], reverse=True)
    return anomalies


def anomaly_summary(anomalies: List[Dict]) -> Dict:
    """Summarize a list of anomalies into a high-level report.

    Returns dict with: count, total_impact, top_service, top_team.
    """
    if not anomalies:
        return {
            "count": 0,
            "total_impact": 0.0,
            "top_service": None,
            "top_team": None,
        }

    total_impact = sum(abs(a["delta"]) for a in anomalies)

    # Find top service by total impact
    service_impact: Dict[str, float] = {}
    team_impact: Dict[str, float] = {}
    for a in anomalies:
        svc = a["service"]
        service_impact[svc] = service_impact.get(svc, 0) + abs(a["delta"])
        team = a.get("team") or "Untagged"
        team_impact[team] = team_impact.get(team, 0) + abs(a["delta"])

    top_service = max(service_impact, key=service_impact.get) if service_impact else None
    top_team = max(team_impact, key=team_impact.get) if team_impact else None

    return {
        "count": len(anomalies),
        "total_impact": total_impact,
        "top_service": top_service,
        "top_team": top_team,
    }
