"""Tests for ingest edge cases, Azure format detection, and idempotency."""

import csv
import os
import tempfile
from decimal import Decimal

from cloudledger.database import RawBillingLine
from cloudledger.ingest import (
    ingest_focus_csv,
    _detect_format,
    _derive_service_from_resource_id,
    _parse_tags,
    _clean,
    FOCUS_COLUMN_MAP,
    AZURE_COLUMN_MAP,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_csv(rows, header):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


FOCUS_HEADER = [
    "InvoiceId", "BillingPeriodStart", "BillingPeriodEnd",
    "ChargePeriodStart", "ChargePeriodEnd",
    "ServiceName", "ServiceCategory", "ResourceId", "ResourceName",
    "Region", "AvailabilityZone", "ChargeType", "ChargeDescription",
    "Quantity", "Unit", "UnitPrice", "BilledCost", "ListCost", "EffectiveCost",
    "Tags",
]

AZURE_HEADER = [
    "InvoiceId", "BillingPeriodStartDate", "BillingPeriodEndDate",
    "Date", "MeterCategory", "MeterSubCategory",
    "ResourceId", "ResourceName", "ResourceLocation",
    "ChargeType", "ProductName", "Quantity", "UnitOfMeasure",
    "UnitPrice", "CostInBillingCurrency", "ListPrice", "EffectivePrice",
    "Tags",
]


# ── Format detection ────────────────────────────────────────────────────────

class TestFormatDetection:
    def test_focus_format_detected(self):
        col_map, provider = _detect_format(list(FOCUS_COLUMN_MAP.keys()))
        assert provider == "AWS"
        assert col_map is FOCUS_COLUMN_MAP

    def test_azure_format_detected(self):
        col_map, provider = _detect_format(list(AZURE_COLUMN_MAP.keys()))
        assert provider == "Azure"
        assert col_map is AZURE_COLUMN_MAP

    def test_unknown_columns_default_to_focus(self):
        col_map, provider = _detect_format(["Foo", "Bar", "Baz"])
        assert provider == "AWS"


# ── Azure service name derivation ────────────────────────────────────────────

class TestAzureServiceDerivation:
    def test_virtual_machines(self):
        rid = "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1"
        assert _derive_service_from_resource_id(rid) == "Virtual Machines"

    def test_storage_accounts(self):
        rid = "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa1"
        assert _derive_service_from_resource_id(rid) == "Storage"

    def test_sql_database_nested(self):
        rid = "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Sql/servers/srv1/databases/db1"
        assert _derive_service_from_resource_id(rid) == "SQL Database"

    def test_no_providers_returns_none(self):
        assert _derive_service_from_resource_id("arn:aws:ec2:us-east-1:123:instance/i-abc") is None

    def test_empty_returns_none(self):
        assert _derive_service_from_resource_id("") is None
        assert _derive_service_from_resource_id(None) is None

    def test_unknown_type_returns_humanized_name(self):
        rid = "/subscriptions/abc/providers/Microsoft.NewService/someResources/r1"
        result = _derive_service_from_resource_id(rid)
        assert result == "someResources"  # fallback: returns the raw type name


# ── Tag parsing ──────────────────────────────────────────────────────────────

class TestTagParsing:
    def test_valid_json_string(self):
        assert _parse_tags('{"team": "backend"}') == {"team": "backend"}

    def test_invalid_json_string(self):
        assert _parse_tags("not json") is None

    def test_none_input(self):
        assert _parse_tags(None) is None

    def test_nan_treated_as_none(self):
        import math
        assert _parse_tags(float("nan")) is None


# ── _clean helper ────────────────────────────────────────────────────────────

class TestClean:
    def test_nan_becomes_none(self):
        import math
        assert _clean(float("nan")) is None


# ── Empty and malformed CSV ───────────────────────────────────────────────────

class TestEmptyCSV:
    def test_headers_only_no_rows(self, db_session):
        """A CSV with headers but no data rows should ingest cleanly with 0 rows."""
        path = _write_csv([], FOCUS_HEADER)
        try:
            stats = ingest_focus_csv(path)
            assert stats["rows_read"] == 0
            assert stats["rows_inserted"] == 0
            assert stats["errors"] == 0
        finally:
            os.unlink(path)



# NOTE: Malformed BilledCost (non-numeric string) is NOT tested because the
# ingest error handler catches per-row construction errors but bulk_save_objects
# blows up on DB-level type coercion. This is a real gap in ingest.py error
# handling — a single bad row in a chunk crashes the entire chunk insert.
# Fixing this requires wrapping bulk_save_objects in a try/except, which is a
# source change beyond the scope of this test suite.


# ── Azure CSV ingestion ─────────────────────────────────────────────────────

class TestAzureIngestion:
    def test_azure_csv_auto_detected(self, db_session):
        """An Azure-format CSV should be auto-detected and ingested correctly."""
        row = [
            "AZ-INV-001", "2025-01-01", "2025-01-31",
            "2025-01-15T00:00:00", "Virtual Machines", "Compute",
            "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1",
            "vm-1", "eastus",
            "Usage", "Standard D2s v3",
            "744", "Hours", "0.10", "74.40", "0.12", "0.10",
            '{"team": "platform"}',
        ]
        path = _write_csv([row], AZURE_HEADER)
        try:
            stats = ingest_focus_csv(path, provider="auto")
            assert stats["rows_inserted"] == 1
            assert stats["errors"] == 0

            with db_session() as s:
                line = s.query(RawBillingLine).first()
                assert line.provider == "Azure"
                assert float(line.billed_cost) == 74.40
        finally:
            os.unlink(path)


# ── Idempotency ──────────────────────────────────────────────────────────────

class TestIdempotency:
    """Verify that re-ingesting the same file is a clean no-op, not a silent
    duplicate or an error. This locks in the current dedup behavior."""

    def test_reingest_same_file_is_noop(self, db_session):
        """Ingesting the exact same CSV twice should skip all rows on second pass."""
        row = [
            "INV-IDEM", "2025-01-01", "2025-01-31",
            "2025-01-01T00:00:00", "2025-01-31T00:00:00",
            "Amazon S3", "Storage",
            "arn:aws:s3:::idempotent-bucket", "idempotent-bucket",
            "us-east-1", "us-east-1a",
            "Usage", "S3 storage",
            "100", "GB", "0.023", "2.30", "2.50", "2.30",
            '{}',
        ]
        path = _write_csv([row], FOCUS_HEADER)
        try:
            stats1 = ingest_focus_csv(path)
            assert stats1["rows_inserted"] == 1

            stats2 = ingest_focus_csv(path)
            assert stats2["rows_inserted"] == 0
            assert stats2["rows_skipped"] == 1

            # Only one row in the database
            with db_session() as s:
                assert s.query(RawBillingLine).count() == 1
        finally:
            os.unlink(path)

    def test_different_resources_not_deduped(self, db_session):
        """Two rows with different resource_ids should both be inserted."""
        rows = [
            [
                "INV-001", "2025-01-01", "2025-01-31",
                "2025-01-01T00:00:00", "2025-01-31T00:00:00",
                "Amazon EC2", "Compute",
                "arn:aws:ec2:us-east-1:123:instance/i-aaa", "i-aaa",
                "us-east-1", "", "Usage", "EC2",
                "744", "Hrs", "0.10", "74.40", "78.00", "74.40", "{}",
            ],
            [
                "INV-001", "2025-01-01", "2025-01-31",
                "2025-01-01T00:00:00", "2025-01-31T00:00:00",
                "Amazon EC2", "Compute",
                "arn:aws:ec2:us-east-1:123:instance/i-bbb", "i-bbb",
                "us-east-1", "", "Usage", "EC2",
                "744", "Hrs", "0.10", "74.40", "78.00", "74.40", "{}",
            ],
        ]
        path = _write_csv(rows, FOCUS_HEADER)
        try:
            stats = ingest_focus_csv(path)
            assert stats["rows_inserted"] == 2
        finally:
            os.unlink(path)

    def test_reingest_after_new_data_only_adds_new(self, db_session):
        """Adding a new row to a file and re-ingesting should only insert the new one."""
        row1 = [
            "INV-001", "2025-01-01", "2025-01-31",
            "2025-01-01T00:00:00", "", "Amazon S3", "",
            "arn:aws:s3:::bucket-1", "bucket-1",
            "", "", "Usage", "",
            "", "", "", "50.00", "", "", "{}",
        ]
        row2 = [
            "INV-001", "2025-01-01", "2025-01-31",
            "2025-01-02T00:00:00", "", "Amazon S3", "",
            "arn:aws:s3:::bucket-2", "bucket-2",
            "", "", "Usage", "",
            "", "", "", "75.00", "", "", "{}",
        ]

        path1 = _write_csv([row1], FOCUS_HEADER)
        path2 = _write_csv([row1, row2], FOCUS_HEADER)
        try:
            stats1 = ingest_focus_csv(path1)
            assert stats1["rows_inserted"] == 1

            stats2 = ingest_focus_csv(path2)
            assert stats2["rows_inserted"] == 1  # only the new row
            assert stats2["rows_skipped"] == 1   # existing row skipped

            with db_session() as s:
                assert s.query(RawBillingLine).count() == 2
        finally:
            os.unlink(path1)
            os.unlink(path2)
