"""
Ingest an AWS FOCUS 1.2 billing export CSV into the raw_focus_export table.

Usage:
    python -m ingestion.ingest_focus_csv data/focus_export_2024_03.csv

The script:
  1. Reads the CSV with pandas
  2. Maps FOCUS 1.2 column names → raw_focus_export columns
  3. Parses the tags column from JSON string → JSONB
  4. Bulk-inserts into PostgreSQL using pandas to_sql
"""

import sys
import json
import pandas as pd
from ingestion.db import get_engine

# FOCUS 1.2 column names → our schema column names
COLUMN_MAP = {
    "BillingPeriodStartDate": "billing_period",
    "ServiceName":            "service_name",
    "ServiceCategory":        "service_category",
    "ResourceId":             "resource_id",
    "ResourceName":           "resource_name",
    "BillingAccountId":       "account_id",
    "BillingAccountName":     "account_name",
    "Region":                 "region",
    "AvailabilityZone":       "availability_zone",
    "ChargeType":             "charge_type",
    "ChargeDescription":      "charge_description",
    "PricingUnit":            "pricing_unit",
    "UsageQuantity":          "usage_quantity",
    "BilledCost":             "billed_cost",
    "EffectiveCost":          "effective_cost",
    "ListCost":               "list_cost",
    "PricingCategory":        "pricing_category",
    "CommitmentDiscountId":   "commitment_discount",
    "Tags":                   "tags",
}


def parse_tags(val):
    """Convert a JSON string or dict to a Python dict, or return None."""
    if pd.isna(val):
        return None
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None


def ingest(csv_path: str) -> int:
    """Load a FOCUS 1.2 CSV into raw_focus_export. Returns row count."""
    engine = get_engine()

    df = pd.read_csv(csv_path, dtype=str)

    # Keep only columns we recognize and rename them
    focus_cols = [c for c in df.columns if c in COLUMN_MAP]
    df = df[focus_cols].rename(columns=COLUMN_MAP)

    # Type conversions
    if "billing_period" in df.columns:
        df["billing_period"] = pd.to_datetime(df["billing_period"]).dt.date

    numeric_cols = [
        "usage_quantity", "billed_cost", "effective_cost", "list_cost",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "tags" in df.columns:
        df["tags"] = df["tags"].apply(parse_tags).apply(
            lambda v: json.dumps(v) if v is not None else None
        )

    # Track provenance
    df["source_file"] = csv_path

    row_count = len(df)
    df.to_sql(
        "raw_focus_export",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=5000,
    )
    print(f"Ingested {row_count:,} rows from {csv_path}")
    return row_count


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m ingestion.ingest_focus_csv <path_to_csv>")
        sys.exit(1)
    ingest(sys.argv[1])
