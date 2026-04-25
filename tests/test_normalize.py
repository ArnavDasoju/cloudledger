"""Tests for the normalization module."""

from datetime import date, datetime
from decimal import Decimal

from cloudledger.database import RawBillingLine, Invoice
from cloudledger.normalize import normalize_invoices


def test_normalize_invoices_aggregates(db_session):
    """normalize_invoices should aggregate billing lines into invoice records."""
    with db_session() as session:
        for i in range(3):
            session.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                charge_period_start=datetime(2025, 1, 1),
                service_name="Amazon EC2",
                resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-{i:04d}",
                billed_cost=Decimal("100.00"),
                charge_type="Usage",
            ))

    count = normalize_invoices()
    assert count == 1

    with db_session() as session:
        inv = session.query(Invoice).filter_by(invoice_id="INV-001").first()
        assert inv is not None
        assert inv.total_line_items == 3
        assert abs(float(inv.total_billed_cost) - 300.00) < 0.01


def test_invoice_total_matches_lines(db_session):
    """Invoice total_billed_cost should match sum of billing lines within $0.01."""
    with db_session() as session:
        costs = [Decimal("1234.56"), Decimal("789.01"), Decimal("0.43")]
        for i, cost in enumerate(costs):
            session.add(RawBillingLine(
                invoice_id="INV-002",
                billing_period_start=date(2025, 2, 1),
                billing_period_end=date(2025, 2, 28),
                charge_period_start=datetime(2025, 2, 1),
                resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-{i:04d}",
                billed_cost=cost,
                charge_type="Usage",
            ))

    normalize_invoices()

    with db_session() as session:
        inv = session.query(Invoice).filter_by(invoice_id="INV-002").first()
        expected = sum([1234.56, 789.01, 0.43])
        assert abs(float(inv.total_billed_cost) - expected) < 0.01
