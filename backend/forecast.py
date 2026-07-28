"""Cost forecasting — linear regression on historical spend data."""

import logging
from datetime import date
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import func

from cloudledger.database import get_db, Invoice, Resource

logger = logging.getLogger(__name__)


def forecast_total(months_ahead: int = 1) -> Dict:
    """Forecast total spend using linear regression on invoice totals.

    Returns {forecast: float, confidence: str, periods_used: int, trend_pct: float, history: [...]}.
    """
    with get_db() as session:
        rows = (
            session.query(Invoice.billing_period_start, Invoice.total_billed_cost)
            .order_by(Invoice.billing_period_start)
            .all()
        )

    if len(rows) < 2:
        return {"forecast": None, "confidence": "insufficient_data", "periods_used": len(rows)}

    costs = [float(r[1] or 0) for r in rows]
    x = np.arange(len(costs))

    # Linear regression
    coeffs = np.polyfit(x, costs, 1)
    slope, intercept = coeffs[0], coeffs[1]

    forecast_x = len(costs) - 1 + months_ahead
    forecast_val = slope * forecast_x + intercept

    # Confidence based on R² and data points
    predicted = np.polyval(coeffs, x)
    ss_res = np.sum((np.array(costs) - predicted) ** 2)
    ss_tot = np.sum((np.array(costs) - np.mean(costs)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    if len(rows) >= 6 and r_squared > 0.7:
        confidence = "high"
    elif len(rows) >= 3 and r_squared > 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    # Monthly trend percentage
    avg_cost = np.mean(costs)
    trend_pct = (slope / avg_cost * 100) if avg_cost > 0 else 0

    history = [
        {"period": r[0].strftime("%Y-%m"), "actual": float(r[1] or 0)}
        for r in rows
    ]

    return {
        "forecast": round(forecast_val, 2),
        "confidence": confidence,
        "r_squared": round(r_squared, 3),
        "trend_pct": round(trend_pct, 1),
        "periods_used": len(rows),
        "history": history,
    }


def forecast_by_service(months_ahead: int = 1) -> List[Dict]:
    """Forecast per-service spend using linear regression.

    Returns list of {service, forecast, trend_pct, current, periods_used}.
    """
    with get_db() as session:
        svc_rows = (
            session.query(
                Resource.service_name,
                Resource.billing_period_start,
                func.sum(Resource.total_cost),
            )
            .group_by(Resource.service_name, Resource.billing_period_start)
            .order_by(Resource.service_name, Resource.billing_period_start)
            .all()
        )

    # Group by service
    by_service: Dict[str, List] = {}
    for svc, period, cost in svc_rows:
        svc_name = svc or "Unknown"
        if svc_name not in by_service:
            by_service[svc_name] = []
        by_service[svc_name].append({"period": period, "cost": float(cost or 0)})

    results = []
    for svc, data in by_service.items():
        if len(data) < 2:
            continue

        costs = [d["cost"] for d in data]
        x = np.arange(len(costs))

        coeffs = np.polyfit(x, costs, 1)
        slope = coeffs[0]
        forecast_x = len(costs) - 1 + months_ahead
        forecast_val = slope * forecast_x + coeffs[1]

        avg_cost = np.mean(costs)
        trend_pct = (slope / avg_cost * 100) if avg_cost > 0 else 0

        results.append({
            "service": svc,
            "forecast": round(max(forecast_val, 0), 2),  # don't predict negative spend
            "current": costs[-1],
            "trend_pct": round(trend_pct, 1),
            "periods_used": len(costs),
        })

    results.sort(key=lambda x: x["forecast"], reverse=True)
    return results
