"""Query layer for Snowflake — powers CloudLedger dashboards from the warehouse."""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_conn = None


def get_snowflake_conn():
    """Get or create a Snowflake connection."""
    global _conn
    if _conn is not None:
        try:
            _conn.cursor().execute("SELECT 1")
            return _conn
        except Exception:
            _conn = None

    import snowflake.connector
    _conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="CLOUDLEDGER",
    )
    return _conn


def is_configured() -> bool:
    """Check if Snowflake credentials are set."""
    return bool(os.environ.get("SNOWFLAKE_ACCOUNT"))


def query(sql: str, params: Optional[dict] = None) -> list[dict]:
    """Execute a SQL query and return results as list of dicts."""
    conn = get_snowflake_conn()
    cur = conn.cursor()
    cur.execute("USE WAREHOUSE COMPUTE_WH")
    cur.execute(sql, params or {})
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    cur.close()
    return [dict(zip(columns, row)) for row in rows]


def get_overview(prior_period: str, current_period: str) -> dict:
    """Bill overview from Snowflake warehouse."""
    rows = query("""
        SELECT
            SUM(CASE WHEN BILLING_PERIOD_START = TO_DATE(%s || '-01') THEN BILLED_COST ELSE 0 END) AS PRIOR_TOTAL,
            SUM(CASE WHEN BILLING_PERIOD_START = TO_DATE(%s || '-01') THEN BILLED_COST ELSE 0 END) AS CURRENT_TOTAL
        FROM ANALYTICS.STG_BILLING_LINES
    """, (prior_period, current_period))
    r = rows[0] if rows else {"PRIOR_TOTAL": 0, "CURRENT_TOTAL": 0}
    prior = float(r["PRIOR_TOTAL"] or 0)
    current = float(r["CURRENT_TOTAL"] or 0)
    return {
        "prior_total": prior,
        "current_total": current,
        "delta": current - prior,
        "prior_period": prior_period,
        "current_period": current_period,
    }


def get_variance(current_period: str) -> dict:
    """Variance detail from Snowflake fact table."""
    resources = query("""
        SELECT
            RESOURCE_ID, RESOURCE_NAME, SERVICE_NAME,
            PRIOR_COST, CURRENT_COST, DELTA_DOLLARS, DELTA_PCT,
            REASON_CODE, REASON_DESCRIPTION, IN_TERRAFORM_STATE,
            EVIDENCE, TEAM, DELTA_BUCKET, HIGH_PRIORITY_DRIFT,
            PCT_OF_TOTAL_VARIANCE
        FROM ANALYTICS.FCT_VARIANCE_REPORT
        WHERE CURRENT_PERIOD_START = TO_DATE(%s || '-01')
        ORDER BY ABS(DELTA_DOLLARS) DESC
    """, (current_period,))

    result = []
    for r in resources:
        result.append({
            "resource_id": r["RESOURCE_ID"],
            "resource_name": r["RESOURCE_NAME"],
            "service": r["SERVICE_NAME"] or "Unknown",
            "prior_cost": float(r["PRIOR_COST"] or 0),
            "current_cost": float(r["CURRENT_COST"] or 0),
            "delta": float(r["DELTA_DOLLARS"] or 0),
            "delta_pct": float(r["DELTA_PCT"] or 0),
            "reason_code": r["REASON_CODE"] or "unknown",
            "reason_description": r["REASON_DESCRIPTION"],
            "in_terraform": r["IN_TERRAFORM_STATE"] or False,
            "evidence": r["EVIDENCE"],
            "team": r["TEAM"],
            "delta_bucket": r["DELTA_BUCKET"],
            "high_priority": r["HIGH_PRIORITY_DRIFT"] or False,
            "pct_of_total": float(r["PCT_OF_TOTAL_VARIANCE"] or 0),
        })

    totals = query("""
        SELECT
            SUM(DELTA_DOLLARS) AS NET_CHANGE,
            SUM(ABS(DELTA_DOLLARS)) AS TOTAL_VARIANCE,
            SUM(CASE WHEN DELTA_DOLLARS > 0 THEN DELTA_DOLLARS ELSE 0 END) AS INCREASES,
            SUM(CASE WHEN DELTA_DOLLARS < 0 THEN DELTA_DOLLARS ELSE 0 END) AS DECREASES
        FROM ANALYTICS.FCT_VARIANCE_REPORT
        WHERE CURRENT_PERIOD_START = TO_DATE(%s || '-01')
    """, (current_period,))
    t = totals[0] if totals else {}

    return {
        "resources": result,
        "net_change": float(t.get("NET_CHANGE") or 0),
        "total_variance": float(t.get("TOTAL_VARIANCE") or 0),
        "total_increases": float(t.get("INCREASES") or 0),
        "total_decreases": float(t.get("DECREASES") or 0),
    }


def get_trends() -> dict:
    """Historical trends from Snowflake."""
    totals = query("""
        SELECT PERIOD_LABEL AS PERIOD, SUM(BILLED_COST) AS COST
        FROM ANALYTICS.STG_BILLING_LINES b
        JOIN ANALYTICS.DIM_PERIODS p ON b.BILLING_PERIOD_START = p.PERIOD_START
        GROUP BY PERIOD_LABEL
        ORDER BY MIN(b.BILLING_PERIOD_START)
    """)

    by_service = {}
    svc_rows = query("""
        SELECT SERVICE_NAME, BILLING_PERIOD_START, SUM(TOTAL_COST) AS COST, COUNT(*) AS RESOURCES
        FROM ANALYTICS.INT_MONTHLY_RESOURCE_SPEND
        GROUP BY SERVICE_NAME, BILLING_PERIOD_START
        ORDER BY BILLING_PERIOD_START
    """)
    for r in svc_rows:
        svc = r["SERVICE_NAME"] or "Unknown"
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append({
            "period": str(r["BILLING_PERIOD_START"])[:7],
            "cost": float(r["COST"] or 0),
            "resources": r["RESOURCES"],
        })

    anomalies = query("""
        SELECT RESOURCE_NAME, SERVICE_NAME, CURRENT_PERIOD_START,
               DELTA_DOLLARS, DELTA_PCT, REASON_CODE, EVIDENCE
        FROM ANALYTICS.FCT_VARIANCE_REPORT
        WHERE ABS(DELTA_PCT) > 50 AND ABS(DELTA_DOLLARS) > 500
        ORDER BY ABS(DELTA_DOLLARS) DESC
        LIMIT 20
    """)

    return {
        "totals": [{"period": r["PERIOD"], "cost": float(r["COST"] or 0)} for r in totals],
        "by_service": by_service,
        "anomalies": [{
            "period": str(a["CURRENT_PERIOD_START"])[:7],
            "resource_name": a["RESOURCE_NAME"],
            "service": a["SERVICE_NAME"] or "Unknown",
            "delta": float(a["DELTA_DOLLARS"] or 0),
            "delta_pct": float(a["DELTA_PCT"] or 0),
            "reason": a["REASON_CODE"],
        } for a in anomalies],
        "source": "snowflake",
    }


def get_engineering(current_period: str) -> dict:
    """IaC coverage from Snowflake."""
    rows = query("""
        SELECT
            COUNT(*) AS TOTAL,
            SUM(CASE WHEN IN_TERRAFORM_STATE = 'True' THEN 1 ELSE 0 END) AS MANAGED,
            SUM(TOTAL_COST) AS TOTAL_COST,
            SUM(CASE WHEN IN_TERRAFORM_STATE = 'True' THEN TOTAL_COST ELSE 0 END) AS MANAGED_COST
        FROM ANALYTICS.DIM_RESOURCES
        WHERE BILLING_PERIOD_START = TO_DATE(%s || '-01')
    """, (current_period,))
    r = rows[0] if rows else {}

    teams = query("""
        SELECT TEAM, COUNT(*) AS CNT, SUM(TOTAL_COST) AS COST,
               SUM(CASE WHEN IN_TERRAFORM_STATE = 'True' THEN 1 ELSE 0 END) AS MANAGED
        FROM ANALYTICS.DIM_RESOURCES
        WHERE BILLING_PERIOD_START = TO_DATE(%s || '-01') AND TEAM IS NOT NULL
        GROUP BY TEAM ORDER BY SUM(TOTAL_COST) DESC
    """, (current_period,))

    return {
        "total_resources": r.get("TOTAL", 0),
        "managed_count": r.get("MANAGED", 0),
        "total_cost": float(r.get("TOTAL_COST") or 0),
        "managed_cost": float(r.get("MANAGED_COST") or 0),
        "teams": [{"team": t["TEAM"], "count": t["CNT"], "cost": float(t["COST"] or 0), "managed": t["MANAGED"]} for t in teams],
        "source": "snowflake",
    }
