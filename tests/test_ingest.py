"""Tests for the FOCUS CSV ingestion module."""

import csv
import os
import tempfile

from cloudledger.ingest import ingest_focus_csv
from cloudledger.database import RawBillingLine


def _write_csv(rows, header=None):
    """Helper to write a temporary CSV file."""
    if header is None:
        header = [
            "InvoiceId", "BillingPeriodStart", "BillingPeriodEnd",
            "ChargePeriodStart", "ChargePeriodEnd",
            "ServiceName", "ServiceCategory", "ResourceId", "ResourceName",
            "Region", "AvailabilityZone", "ChargeType", "ChargeDescription",
            "Quantity", "Unit", "UnitPrice", "BilledCost", "ListCost", "EffectiveCost",
            "Tags",
        ]
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)
    return path


SAMPLE_ROW = [
    "INV-001", "2025-01-01", "2025-01-31",
    "2025-01-01T00:00:00", "2025-01-31T00:00:00",
    "Amazon EC2", "Compute",
    "arn:aws:ec2:us-east-1:123456789:instance/i-abc123",
    "i-abc123", "us-east-1", "us-east-1a",
    "Usage", "EC2 running hours",
    "744", "Hrs", "0.10", "74.40", "78.12", "74.40",
    '{"team": "backend"}',
]


def test_ingest_loads_csv(db_session):
    """Ingesting a valid CSV should insert all rows."""
    path = _write_csv([SAMPLE_ROW])
    try:
        stats = ingest_focus_csv(path)
        assert stats["rows_read"] == 1
        assert stats["rows_inserted"] == 1
        assert stats["errors"] == 0

        with db_session() as session:
            count = session.query(RawBillingLine).count()
            assert count == 1
            row = session.query(RawBillingLine).first()
            assert row.service_name == "Amazon EC2"
            assert float(row.billed_cost) == 74.40
    finally:
        os.unlink(path)


def test_duplicate_rows_skipped(db_session):
    """Ingesting the same CSV twice should skip duplicates."""
    path = _write_csv([SAMPLE_ROW, SAMPLE_ROW])
    try:
        stats = ingest_focus_csv(path)
        # First row inserted, second is a dupe within the same file
        assert stats["rows_inserted"] == 1
        assert stats["rows_skipped"] == 1

        # Ingest again — all should be skipped
        stats2 = ingest_focus_csv(path)
        assert stats2["rows_inserted"] == 0
        assert stats2["rows_skipped"] == 2  # both rows in CSV are dupes
    finally:
        os.unlink(path)


def test_missing_columns_handled(db_session):
    """CSV with missing optional columns should still ingest with None defaults."""
    header = ["InvoiceId", "BillingPeriodStart", "BillingPeriodEnd", "BilledCost", "ResourceId", "ChargePeriodStart"]
    row = ["INV-002", "2025-01-01", "2025-01-31", "100.00", "arn:aws:s3:::my-bucket", "2025-01-01T00:00:00"]
    path = _write_csv([row], header=header)
    try:
        stats = ingest_focus_csv(path)
        assert stats["rows_read"] == 1
        assert stats["rows_inserted"] == 1
        assert stats["errors"] == 0

        with db_session() as session:
            record = session.query(RawBillingLine).first()
            assert record.service_name is None
            assert float(record.billed_cost) == 100.00
    finally:
        os.unlink(path)
