"""Syncs CloudLedger billing data from PostgreSQL to Snowflake.

Creates a star schema in Snowflake with fact and dimension tables,
then loads data from the local Postgres database.
"""

import csv
import io
import logging
import os
import tempfile
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


def get_snowflake_connection():
    """Create a Snowflake connection from environment variables."""
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "SYSADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="CLOUDLEDGER",
    )


def create_snowflake_schema(conn):
    """Create the star schema in Snowflake — fact and dimension tables."""
    cur = conn.cursor()

    cur.execute("CREATE DATABASE IF NOT EXISTS CLOUDLEDGER")
    cur.execute("USE DATABASE CLOUDLEDGER")
    cur.execute("CREATE SCHEMA IF NOT EXISTS RAW")
    cur.execute("CREATE SCHEMA IF NOT EXISTS ANALYTICS")

    # Raw layer — mirrors Postgres tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS RAW.BILLING_LINES (
            id INTEGER,
            invoice_id VARCHAR,
            billing_period_start DATE,
            billing_period_end DATE,
            service_name VARCHAR,
            service_category VARCHAR,
            resource_id VARCHAR,
            resource_name VARCHAR,
            region VARCHAR,
            charge_type VARCHAR,
            description VARCHAR,
            quantity DECIMAL(18,6),
            unit VARCHAR,
            unit_price DECIMAL(18,10),
            billed_cost DECIMAL(18,6),
            list_cost DECIMAL(18,6),
            effective_cost DECIMAL(18,6),
            tags VARIANT,
            provider VARCHAR,
            loaded_at TIMESTAMP_NTZ
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS RAW.RESOURCES (
            id INTEGER,
            resource_id VARCHAR,
            resource_name VARCHAR,
            service_name VARCHAR,
            service_category VARCHAR,
            region VARCHAR,
            team VARCHAR,
            cost_center VARCHAR,
            in_terraform_state BOOLEAN,
            terraform_module VARCHAR,
            iac_source VARCHAR,
            environment VARCHAR,
            billing_period_start DATE,
            total_cost DECIMAL(18,2)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS RAW.VARIANCE_REPORT (
            id INTEGER,
            resource_id VARCHAR,
            resource_name VARCHAR,
            service_name VARCHAR,
            team VARCHAR,
            cost_center VARCHAR,
            prior_period_start DATE,
            current_period_start DATE,
            prior_cost DECIMAL(18,2),
            current_cost DECIMAL(18,2),
            delta_dollars DECIMAL(18,2),
            delta_pct DECIMAL(8,2),
            reason_code VARCHAR,
            confidence_score DECIMAL(3,2),
            evidence VARCHAR,
            pr_number VARCHAR,
            pr_author VARCHAR,
            iac_source VARCHAR,
            in_terraform_state BOOLEAN,
            reviewed BOOLEAN,
            excluded BOOLEAN
        )
    """)

    # Dimension tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ANALYTICS.DIM_SERVICES (
            service_key INTEGER AUTOINCREMENT,
            service_name VARCHAR,
            service_category VARCHAR,
            PRIMARY KEY (service_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ANALYTICS.DIM_TEAMS (
            team_key INTEGER AUTOINCREMENT,
            team VARCHAR,
            cost_center VARCHAR,
            PRIMARY KEY (team_key)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ANALYTICS.DIM_PERIODS (
            period_key INTEGER AUTOINCREMENT,
            period_start DATE,
            period_year INTEGER,
            period_month INTEGER,
            period_label VARCHAR,
            days_in_month INTEGER,
            PRIMARY KEY (period_key)
        )
    """)

    # Fact table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ANALYTICS.FACT_VARIANCE (
            variance_id INTEGER,
            resource_id VARCHAR,
            resource_name VARCHAR,
            service_key INTEGER REFERENCES ANALYTICS.DIM_SERVICES(service_key),
            team_key INTEGER REFERENCES ANALYTICS.DIM_TEAMS(team_key),
            prior_period_key INTEGER REFERENCES ANALYTICS.DIM_PERIODS(period_key),
            current_period_key INTEGER REFERENCES ANALYTICS.DIM_PERIODS(period_key),
            prior_cost DECIMAL(18,2),
            current_cost DECIMAL(18,2),
            delta_dollars DECIMAL(18,2),
            delta_pct DECIMAL(8,2),
            reason_code VARCHAR,
            confidence_score DECIMAL(3,2),
            in_terraform_state BOOLEAN,
            iac_source VARCHAR,
            evidence VARCHAR
        )
    """)

    cur.close()
    logger.info("Snowflake schema created")


def sync_to_snowflake(period: Optional[str] = None) -> dict:
    """Export data from Postgres and load into Snowflake.

    Args:
        period: Optional YYYY-MM filter. If None, syncs all data.

    Returns:
        Dict with row counts per table.
    """
    from cloudledger.database import get_db, RawBillingLine, Resource, VarianceReport

    conn = get_snowflake_connection()
    create_snowflake_schema(conn)
    cur = conn.cursor()
    cur.execute("USE DATABASE CLOUDLEDGER")

    stats = {}

    # Export each table from Postgres to CSV, then PUT + COPY INTO Snowflake
    tables = [
        ("RAW.BILLING_LINES", RawBillingLine, [
            "id", "invoice_id", "billing_period_start", "billing_period_end",
            "service_name", "service_category", "resource_id", "resource_name",
            "region", "charge_type", "description", "quantity", "unit",
            "unit_price", "billed_cost", "list_cost", "effective_cost",
            "tags", "provider", "loaded_at",
        ]),
        ("RAW.RESOURCES", Resource, [
            "id", "resource_id", "resource_name", "service_name",
            "service_category", "region", "team", "cost_center",
            "in_terraform_state", "terraform_module", "iac_source",
            "environment", "billing_period_start", "total_cost",
        ]),
        ("RAW.VARIANCE_REPORT", VarianceReport, [
            "id", "resource_id", "resource_name", "service_name",
            "team", "cost_center", "prior_period_start", "current_period_start",
            "prior_cost", "current_cost", "delta_dollars", "delta_pct",
            "reason_code", "confidence_score", "evidence", "pr_number",
            "pr_author", "iac_source", "in_terraform_state", "reviewed", "excluded",
        ]),
    ]

    for sf_table, model, columns in tables:
        with get_db() as session:
            query = session.query(model)
            if period:
                period_date = date.fromisoformat(f"{period}-01")
                if hasattr(model, "billing_period_start"):
                    query = query.filter(model.billing_period_start == period_date)
                elif hasattr(model, "current_period_start"):
                    query = query.filter(model.current_period_start == period_date)
            rows = query.all()

            if not rows:
                stats[sf_table] = 0
                continue

            # Write to temp CSV
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
            writer = csv.writer(tmp)
            writer.writerow(columns)
            for row in rows:
                writer.writerow([str(getattr(row, col, "") or "") for col in columns])
            tmp.close()

            # Upload to Snowflake internal stage and COPY INTO
            cur.execute(f"CREATE OR REPLACE TEMPORARY STAGE cloudledger_stage")
            cur.execute(f"PUT file://{tmp.name} @cloudledger_stage AUTO_COMPRESS=TRUE")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {sf_table}")
            cur.execute(f"""
                COPY INTO {sf_table}
                FROM @cloudledger_stage/{os.path.basename(tmp.name)}.gz
                FILE_FORMAT = (TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
                ON_ERROR = 'CONTINUE'
            """)

            # Get actual row count after COPY
            cur.execute(f"SELECT COUNT(*) FROM {sf_table}")
            loaded = cur.fetchone()[0]
            stats[sf_table] = loaded
            os.unlink(tmp.name)
            logger.info("Loaded %s rows into %s", loaded, sf_table)

    # Populate dimension tables
    cur.execute("""
        MERGE INTO ANALYTICS.DIM_SERVICES t
        USING (SELECT DISTINCT service_name, service_category FROM RAW.RESOURCES) s
        ON t.service_name = s.service_name
        WHEN NOT MATCHED THEN INSERT (service_name, service_category) VALUES (s.service_name, s.service_category)
    """)

    cur.execute("""
        MERGE INTO ANALYTICS.DIM_TEAMS t
        USING (SELECT DISTINCT team, cost_center FROM RAW.RESOURCES WHERE team IS NOT NULL) s
        ON t.team = s.team
        WHEN NOT MATCHED THEN INSERT (team, cost_center) VALUES (s.team, s.cost_center)
    """)

    cur.execute("""
        MERGE INTO ANALYTICS.DIM_PERIODS t
        USING (
            SELECT DISTINCT
                billing_period_start,
                YEAR(billing_period_start) as y,
                MONTH(billing_period_start) as m,
                TO_CHAR(billing_period_start, 'YYYY-MM') as label,
                DAYOFMONTH(LAST_DAY(billing_period_start)) as days
            FROM RAW.BILLING_LINES
        ) s
        ON t.period_start = s.billing_period_start
        WHEN NOT MATCHED THEN INSERT (period_start, period_year, period_month, period_label, days_in_month)
            VALUES (s.billing_period_start, s.y, s.m, s.label, s.days)
    """)

    # Populate fact table
    cur.execute("TRUNCATE TABLE IF EXISTS ANALYTICS.FACT_VARIANCE")
    cur.execute("""
        INSERT INTO ANALYTICS.FACT_VARIANCE
        SELECT
            vr.id,
            vr.resource_id,
            vr.resource_name,
            ds.service_key,
            dt.team_key,
            pp.period_key,
            cp.period_key,
            vr.prior_cost,
            vr.current_cost,
            vr.delta_dollars,
            vr.delta_pct,
            vr.reason_code,
            vr.confidence_score,
            vr.in_terraform_state,
            vr.iac_source,
            vr.evidence
        FROM RAW.VARIANCE_REPORT vr
        LEFT JOIN ANALYTICS.DIM_SERVICES ds ON vr.service_name = ds.service_name
        LEFT JOIN ANALYTICS.DIM_TEAMS dt ON vr.team = dt.team
        LEFT JOIN ANALYTICS.DIM_PERIODS pp ON vr.prior_period_start = pp.period_start
        LEFT JOIN ANALYTICS.DIM_PERIODS cp ON vr.current_period_start = cp.period_start
    """)

    fact_count = cur.execute("SELECT COUNT(*) FROM ANALYTICS.FACT_VARIANCE").fetchone()[0]
    stats["ANALYTICS.FACT_VARIANCE"] = fact_count

    cur.close()
    conn.close()

    logger.info("Snowflake sync complete: %s", stats)
    return stats


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    period = sys.argv[1] if len(sys.argv) > 1 else None
    result = sync_to_snowflake(period)
    for table, count in result.items():
        print(f"  {table}: {count} rows")
