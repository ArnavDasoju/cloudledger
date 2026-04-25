"""Tests for data quality checks."""

from datetime import date
from decimal import Decimal

from cloudledger.database import RawBillingLine, Invoice
from cloudledger.quality import run_quality_checks


def _seed_billing_data(db_session):
    """Insert sample billing data for quality checks."""
    with db_session() as session:
        # Insert raw billing lines
        for i in range(3):
            session.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id=f"arn:aws:ec2:us-east-1:123456:instance/i-{i:04d}",
                service_name="Amazon EC2",
                billed_cost=Decimal("100.00"),
                charge_type="Usage",
            ))

        # Insert matching invoice
        session.add(Invoice(
            invoice_id="INV-001",
            billing_period_start=date(2025, 1, 1),
            billing_period_end=date(2025, 1, 31),
            total_billed_cost=Decimal("300.00"),
            total_line_items=3,
            attributed_cost=Decimal("270.00"),
            unattributed_cost=Decimal("30.00"),
            attribution_coverage_pct=Decimal("90.00"),
        ))


def test_all_checks_pass_on_sample_data(db_session):
    """All 5 quality checks should pass on well-formed sample data."""
    _seed_billing_data(db_session)
    results = run_quality_checks("2025-01")

    # Should have at least 5 check results
    assert len(results) >= 5

    # No failures
    failed = [r for r in results if r["status"] == "fail"]
    assert failed == [], f"Unexpected failures: {failed}"


def test_reconciliation_check(db_session):
    """Invoice total should match sum of billing lines within $0.01."""
    _seed_billing_data(db_session)
    results = run_quality_checks("2025-01")

    recon = [r for r in results if "reconciliation" in r["check"].lower()]
    assert len(recon) > 0
    assert all(r["status"] == "pass" for r in recon)


def test_no_duplicates_check(db_session):
    """Duplicate check should pass when no duplicates exist."""
    _seed_billing_data(db_session)
    results = run_quality_checks("2025-01")

    dupe_check = [r for r in results if "duplicate" in r["check"].lower()]
    assert len(dupe_check) == 1
    assert dupe_check[0]["status"] == "pass"


def test_attribution_coverage_check(db_session):
    """Attribution coverage check passes when coverage >= 80%."""
    _seed_billing_data(db_session)
    results = run_quality_checks("2025-01")

    coverage = [r for r in results if "attribution" in r["check"].lower()]
    assert len(coverage) > 0
    assert all(r["status"] == "pass" for r in coverage)


def test_no_negative_costs_check(db_session):
    """Negative cost check passes when no non-credit negatives exist."""
    _seed_billing_data(db_session)
    results = run_quality_checks("2025-01")

    neg_check = [r for r in results if "negative" in r["check"].lower()]
    assert len(neg_check) == 1
    assert neg_check[0]["status"] == "pass"
