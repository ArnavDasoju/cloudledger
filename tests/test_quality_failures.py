"""Tests for quality check failure paths.

The existing test_quality.py only tests the all-pass scenario.
These tests verify that each check correctly reports failures and warnings.
"""

from datetime import date
from decimal import Decimal

from cloudledger.database import RawBillingLine, Invoice
from cloudledger.quality import run_quality_checks


def _find_check(results, keyword):
    """Find a check result by keyword in its name."""
    matches = [r for r in results if keyword.lower() in r["check"].lower()]
    assert matches, f"No check found matching '{keyword}' in {[r['check'] for r in results]}"
    return matches[0]


class TestReconciliationFailure:
    def test_mismatch_fails(self, db_session):
        """Invoice total != sum of lines → reconciliation check fails."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("100.00"),
                charge_type="Usage",
            ))
            s.add(Invoice(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                total_billed_cost=Decimal("999.00"),  # mismatch
                total_line_items=1,
                attributed_cost=Decimal("999"),
                unattributed_cost=Decimal("0"),
                attribution_coverage_pct=Decimal("100"),
            ))

        results = run_quality_checks("2025-01")
        recon = _find_check(results, "reconciliation")
        assert recon["status"] == "fail"

    def test_no_invoice_warns(self, db_session):
        """No invoice for the period → reconciliation check warns."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("100.00"),
                charge_type="Usage",
            ))

        results = run_quality_checks("2025-01")
        recon = _find_check(results, "reconciliation")
        assert recon["status"] == "warn"


class TestDuplicateDetection:
    def test_duplicate_lines_warn(self, db_session):
        """Duplicate billing lines should trigger a warning."""
        with db_session() as s:
            for _ in range(2):
                s.add(RawBillingLine(
                    invoice_id="INV-DUP",
                    billing_period_start=date(2025, 1, 1),
                    billing_period_end=date(2025, 1, 31),
                    resource_id="r-dup",
                    charge_period_start=date(2025, 1, 1),
                    billed_cost=Decimal("100.00"),
                    charge_type="Usage",
                ))

        results = run_quality_checks("2025-01")
        dupe = _find_check(results, "duplicate")
        assert dupe["status"] == "warn"
        assert "1 duplicate" in dupe["detail"]


class TestMissingResourceIds:
    def test_missing_resource_id_warns(self, db_session):
        """Lines with null resource_id should trigger a warning."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id=None,
                billed_cost=Decimal("50.00"),
                charge_type="Usage",
            ))
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("50.00"),
                charge_type="Usage",
            ))

        results = run_quality_checks("2025-01")
        rid_check = _find_check(results, "resource id")
        assert rid_check["status"] == "warn"
        assert "1 of 2" in rid_check["detail"]


class TestNegativeCosts:
    def test_non_credit_negative_warns(self, db_session):
        """Non-credit negative costs should trigger a warning."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("-50.00"),
                charge_type="Usage",  # not Credit or Refund
            ))

        results = run_quality_checks("2025-01")
        neg = _find_check(results, "negative")
        assert neg["status"] == "warn"

    def test_credit_negative_is_ok(self, db_session):
        """Credit/Refund negative costs should NOT trigger a warning."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("-50.00"),
                charge_type="Credit",
            ))
            # Need an invoice for the attribution check not to warn
            s.add(Invoice(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                total_billed_cost=Decimal("-50.00"),
                total_line_items=1,
                attributed_cost=Decimal("-50"),
                unattributed_cost=Decimal("0"),
                attribution_coverage_pct=Decimal("100"),
            ))

        results = run_quality_checks("2025-01")
        neg = _find_check(results, "negative")
        assert neg["status"] == "pass"


class TestAttributionCoverage:
    def test_low_coverage_fails(self, db_session):
        """Attribution coverage < 80% should fail."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                resource_id="r1",
                billed_cost=Decimal("100.00"),
                charge_type="Usage",
            ))
            s.add(Invoice(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                total_billed_cost=Decimal("100.00"),
                total_line_items=1,
                attributed_cost=Decimal("50"),
                unattributed_cost=Decimal("50"),
                attribution_coverage_pct=Decimal("50.00"),  # < 80%
            ))

        results = run_quality_checks("2025-01")
        attr = _find_check(results, "attribution")
        assert attr["status"] == "fail"


class TestEmptyPeriod:
    def test_no_data_returns_results(self, db_session):
        """A period with no data should return check results without crashing."""
        results = run_quality_checks("2030-01")
        assert len(results) >= 4
        # No failures — just warnings about missing data
        failed = [r for r in results if r["status"] == "fail"]
        assert failed == []
