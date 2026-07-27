"""Reads FOCUS 1.2 CSV files and writes to raw_billing_lines table."""

import json
import logging
from typing import Dict

import pandas as pd

from cloudledger.database import get_db, RawBillingLine

logger = logging.getLogger(__name__)

# Map FOCUS 1.2 PascalCase column names → our snake_case schema
FOCUS_COLUMN_MAP = {
    "InvoiceId": "invoice_id",
    "BillingPeriodStart": "billing_period_start",
    "BillingPeriodEnd": "billing_period_end",
    "ChargePeriodStart": "charge_period_start",
    "ChargePeriodEnd": "charge_period_end",
    "ServiceName": "service_name",
    "ServiceCategory": "service_category",
    "ResourceId": "resource_id",
    "ResourceName": "resource_name",
    "Region": "region",
    "AvailabilityZone": "availability_zone",
    "ChargeType": "charge_type",
    "Description": "description",
    "ChargeDescription": "description",
    "Quantity": "quantity",
    "Unit": "unit",
    "UnitPrice": "unit_price",
    "BilledCost": "billed_cost",
    "ListCost": "list_cost",
    "EffectiveCost": "effective_cost",
    "Tags": "tags",
    "Provider": "provider",
}

# Azure Cost Export uses different column names
AZURE_COLUMN_MAP = {
    "InvoiceId": "invoice_id",
    "BillingPeriodStartDate": "billing_period_start",
    "BillingPeriodEndDate": "billing_period_end",
    "Date": "charge_period_start",
    "MeterCategory": "service_name",
    "MeterSubCategory": "service_category",
    "ResourceId": "resource_id",
    "ResourceName": "resource_name",
    "ResourceLocation": "region",
    "ChargeType": "charge_type",
    "ProductName": "description",
    "Quantity": "quantity",
    "UnitOfMeasure": "unit",
    "UnitPrice": "unit_price",
    "CostInBillingCurrency": "billed_cost",
    "ListPrice": "list_cost",
    "EffectivePrice": "effective_cost",
    "Tags": "tags",
}

ALL_COLUMNS = list(dict.fromkeys(FOCUS_COLUMN_MAP.values()))  # unique, preserves order

CHUNK_SIZE = 10_000


def _clean(v):
    """Convert NaN/NaT to None for database insertion."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _parse_tags(val):
    """Parse tags JSON string → dict."""
    val = _clean(val)
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return None
    return val


# Azure resource type → friendly service name
_AZURE_SERVICE_MAP = {
    "microsoft.compute/virtualmachines": "Virtual Machines",
    "microsoft.compute/disks": "Managed Disks",
    "microsoft.sql/servers": "SQL Database",
    "microsoft.sql/servers/databases": "SQL Database",
    "microsoft.storage/storageaccounts": "Storage",
    "microsoft.network/virtualnetworks": "Virtual Network",
    "microsoft.network/publicipaddresses": "Public IP",
    "microsoft.network/loadbalancers": "Load Balancer",
    "microsoft.network/applicationgateways": "Application Gateway",
    "microsoft.network/networkinterfaces": "Network Interface",
    "microsoft.web/sites": "App Service",
    "microsoft.web/serverfarms": "App Service Plan",
    "microsoft.containerservice/managedclusters": "AKS",
    "microsoft.dbforpostgresql/servers": "PostgreSQL",
    "microsoft.dbformysql/servers": "MySQL",
    "microsoft.cache/redis": "Redis Cache",
    "microsoft.cdn/profiles": "CDN",
    "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.containerregistry/registries": "Container Registry",
    "microsoft.eventhub/namespaces": "Event Hubs",
    "microsoft.servicebus/namespaces": "Service Bus",
    "microsoft.cognitiveservices/accounts": "Cognitive Services",
    "microsoft.insights/components": "Application Insights",
}


def _derive_service_from_resource_id(resource_id: str) -> str | None:
    """Extract Azure service name from ARM resource ID path."""
    if not resource_id or "/providers/" not in resource_id.lower():
        return None
    # ARM format: /subscriptions/.../providers/Microsoft.Compute/virtualMachines/name
    lower = resource_id.lower()
    idx = lower.rfind("/providers/")
    if idx < 0:
        return None
    after = resource_id[idx + len("/providers/"):]
    parts = after.split("/")
    if len(parts) >= 2:
        # Try 2-level match first (e.g. Microsoft.Sql/servers/databases)
        if len(parts) >= 4:
            key3 = f"{parts[0]}/{parts[1]}/{parts[3]}".lower()
            if key3 in _AZURE_SERVICE_MAP:
                return _AZURE_SERVICE_MAP[key3]
        # 1-level match (e.g. Microsoft.Compute/virtualMachines)
        key2 = f"{parts[0]}/{parts[1]}".lower()
        if key2 in _AZURE_SERVICE_MAP:
            return _AZURE_SERVICE_MAP[key2]
        # Fallback: humanize the resource type
        return parts[1].replace("virtualMachines", "Virtual Machines").replace("storageAccounts", "Storage")
    return None


def _process_chunk(chunk: pd.DataFrame, column_map: dict, existing: set,
                   provider: str) -> tuple[list, int, int, int]:
    """Process a single chunk of CSV data. Returns (records, inserted, skipped, errors)."""
    rename_map = {k: v for k, v in column_map.items() if k in chunk.columns}
    # Avoid duplicate target columns by only keeping first match
    seen_targets = set()
    deduped_rename = {}
    for k, v in rename_map.items():
        if v not in seen_targets:
            deduped_rename[k] = v
            seen_targets.add(v)
    chunk = chunk.rename(columns=deduped_rename)

    # Drop duplicate columns if any remain
    chunk = chunk.loc[:, ~chunk.columns.duplicated()]

    for col in ALL_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = None

    chunk = chunk[ALL_COLUMNS]

    date_cols = ["billing_period_start", "billing_period_end"]
    for col in date_cols:
        if col in chunk.columns:
            chunk[col] = pd.to_datetime(chunk[col], errors="coerce").dt.date

    ts_cols = ["charge_period_start", "charge_period_end"]
    for col in ts_cols:
        if col in chunk.columns:
            chunk[col] = pd.to_datetime(chunk[col], errors="coerce")

    records = []
    inserted = 0
    skipped = 0
    errors = 0

    for _, row in chunk.iterrows():
        try:
            dedup_key = (
                f"{row.get('invoice_id', '')}|"
                f"{row.get('resource_id', '')}|"
                f"{row.get('charge_period_start', '')}"
            )
            if dedup_key in existing:
                skipped += 1
                continue

            # Use provider from CSV if present, otherwise use function parameter
            row_provider = _clean(row.get("provider"))
            # Handle description — ensure it's a scalar, not a Series
            desc = row.get("description")
            if hasattr(desc, 'iloc'):
                desc = desc.iloc[0] if len(desc) > 0 else None

            # Derive friendly service_name from Azure resource ID
            svc = _clean(row.get("service_name"))
            rid = _clean(row.get("resource_id"))
            if rid:
                derived = _derive_service_from_resource_id(str(rid))
                # Use derived name if: no service name, or service name looks like a raw Azure resource type
                if not svc or (svc and "microsoft." in svc.lower()):
                    svc = derived or svc

            record = RawBillingLine(
                invoice_id=_clean(row.get("invoice_id")),
                billing_period_start=_clean(row.get("billing_period_start")),
                billing_period_end=_clean(row.get("billing_period_end")),
                charge_period_start=_clean(row.get("charge_period_start")),
                charge_period_end=_clean(row.get("charge_period_end")),
                service_name=svc,
                service_category=_clean(row.get("service_category")),
                resource_id=rid,
                resource_name=_clean(row.get("resource_name")),
                region=_clean(row.get("region")),
                availability_zone=_clean(row.get("availability_zone")),
                charge_type=_clean(row.get("charge_type")),
                description=_clean(desc),
                quantity=_clean(row.get("quantity")),
                unit=_clean(row.get("unit")),
                unit_price=_clean(row.get("unit_price")),
                billed_cost=_clean(row.get("billed_cost")),
                list_cost=_clean(row.get("list_cost")),
                effective_cost=_clean(row.get("effective_cost")),
                tags=_parse_tags(row.get("tags")),
                provider=row_provider if row_provider else provider,
            )
            records.append(record)
            existing.add(dedup_key)
            inserted += 1
        except Exception as e:
            logger.error("Error processing row: %s", e)
            errors += 1

    return records, inserted, skipped, errors


def _detect_format(columns: list) -> tuple[dict, str]:
    """Auto-detect CSV format from column names. Returns (column_map, provider)."""
    col_set = set(columns)
    # Azure-specific columns
    azure_markers = {"BillingPeriodStartDate", "CostInBillingCurrency", "MeterCategory", "ResourceLocation"}
    if azure_markers & col_set:
        return AZURE_COLUMN_MAP, "Azure"
    return FOCUS_COLUMN_MAP, "AWS"


def ingest_focus_csv(filepath: str, provider: str = "auto") -> Dict:
    """Ingest a billing CSV file into raw_billing_lines.

    Auto-detects AWS FOCUS vs Azure Cost Export format from column headers.
    Uses chunked reads (chunksize=10,000) for memory-efficient processing.

    Returns dict with stats: rows_read, rows_inserted, rows_skipped, errors.
    """
    # Peek at headers to detect format
    header_df = pd.read_csv(filepath, nrows=0)
    column_map, detected_provider = _detect_format(list(header_df.columns))
    if provider == "auto":
        provider = detected_provider
    logger.info("Starting ingestion of %s (detected=%s, provider=%s)", filepath, detected_provider, provider)

    total_read = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    with get_db() as session:
        # Load existing keys for dedup
        existing_rows = session.query(
            RawBillingLine.invoice_id,
            RawBillingLine.resource_id,
            RawBillingLine.charge_period_start,
        ).all()
        existing = {
            f"{r.invoice_id}|{r.resource_id}|{r.charge_period_start or ''}"
            for r in existing_rows
        }

        for chunk in pd.read_csv(filepath, chunksize=CHUNK_SIZE):
            total_read += len(chunk)
            records, inserted, skipped, errors = _process_chunk(
                chunk, column_map, existing, provider
            )
            if records:
                session.bulk_save_objects(records)
            total_inserted += inserted
            total_skipped += skipped
            total_errors += errors

            logger.debug(
                "Chunk processed: %d inserted, %d skipped, %d errors",
                inserted, skipped, errors,
            )

    stats = {
        "rows_read": total_read,
        "rows_inserted": total_inserted,
        "rows_skipped": total_skipped,
        "errors": total_errors,
    }
    logger.info("Ingest complete: %d inserted, %d skipped, %d errors (of %d read)",
                total_inserted, total_skipped, total_errors, total_read)
    return stats


def ingest_azure_cost_export(filepath: str) -> Dict:
    """Ingest an Azure Cost Management CSV export.

    Handles Azure's billing format differences (different column names,
    date formats, and resource ID structure) and normalizes into the
    same raw_billing_lines schema.

    Returns dict with stats: rows_read, rows_inserted, rows_skipped, errors.
    """
    logger.info("Starting Azure cost export ingestion: %s", filepath)

    total_read = 0
    total_inserted = 0
    total_skipped = 0
    total_errors = 0

    with get_db() as session:
        existing_rows = session.query(
            RawBillingLine.invoice_id,
            RawBillingLine.resource_id,
            RawBillingLine.charge_period_start,
        ).all()
        existing = {
            f"{r.invoice_id}|{r.resource_id}|{r.charge_period_start or ''}"
            for r in existing_rows
        }

        for chunk in pd.read_csv(filepath, chunksize=CHUNK_SIZE):
            total_read += len(chunk)
            records, inserted, skipped, errors = _process_chunk(
                chunk, AZURE_COLUMN_MAP, existing, "Azure"
            )
            if records:
                session.bulk_save_objects(records)
            total_inserted += inserted
            total_skipped += skipped
            total_errors += errors

    stats = {
        "rows_read": total_read,
        "rows_inserted": total_inserted,
        "rows_skipped": total_skipped,
        "errors": total_errors,
    }
    logger.info("Azure ingest complete: %d inserted, %d skipped, %d errors (of %d read)",
                total_inserted, total_skipped, total_errors, total_read)
    return stats


if __name__ == "__main__":
    import sys
    from cloudledger.database import create_all_tables

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    create_all_tables()
    path = sys.argv[1] if len(sys.argv) > 1 else "data/samples/month1.csv"
    ingest_focus_csv(path)
