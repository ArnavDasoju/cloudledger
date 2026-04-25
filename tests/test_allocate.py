"""Tests for the cost allocation engine."""

from datetime import date, datetime
from decimal import Decimal

from cloudledger.database import RawBillingLine, Invoice, Resource, Allocation
from cloudledger.normalize import normalize_invoices
from cloudledger.allocate import run_allocations


def _seed_data(db_session, in_terraform=True, tags=None):
    """Insert a billing line + resource + invoice for testing."""
    with db_session() as session:
        session.add(RawBillingLine(
            invoice_id="INV-T01",
            billing_period_start=date(2025, 1, 1),
            billing_period_end=date(2025, 1, 31),
            charge_period_start=datetime(2025, 1, 1),
            service_name="Amazon EC2",
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-alloc",
            billed_cost=Decimal("500.00"),
            charge_type="Usage",
            tags=tags,
        ))
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-alloc",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 1, 1),
            total_cost=Decimal("500.00"),
            in_terraform_state=in_terraform,
            team="backend" if tags else None,
            cost_center="CC-1001" if tags else None,
        ))
    normalize_invoices()


def test_allocation_creates_rows(db_session):
    """run_allocations should create one allocation per billing line."""
    _seed_data(db_session, in_terraform=True, tags={"team": "backend", "cost_center": "CC-1001"})
    count = run_allocations()
    assert count == 1

    with db_session() as session:
        alloc = session.query(Allocation).first()
        assert alloc is not None
        assert float(alloc.allocated_cost) == 500.00


def test_terraform_gets_high_confidence(db_session):
    """Terraform-managed resources should get confidence 0.95."""
    _seed_data(db_session, in_terraform=True, tags={"team": "backend"})
    run_allocations()

    with db_session() as session:
        alloc = session.query(Allocation).first()
        assert alloc.attribution_method == "terraform_state"
        assert float(alloc.confidence_score) == 0.95


def test_tag_only_gets_medium_confidence(db_session):
    """Tag-attributed resources should get confidence 0.80."""
    _seed_data(db_session, in_terraform=False, tags={"team": "backend"})
    run_allocations()

    with db_session() as session:
        alloc = session.query(Allocation).first()
        assert alloc.attribution_method == "tag"
        assert float(alloc.confidence_score) == 0.80


def test_attribution_coverage_updated(db_session):
    """After allocation, invoice attribution_coverage_pct should be > 0."""
    _seed_data(db_session, in_terraform=True, tags={"team": "backend"})
    run_allocations()

    with db_session() as session:
        inv = session.query(Invoice).filter_by(invoice_id="INV-T01").first()
        assert inv is not None
        assert float(inv.attribution_coverage_pct) == 100.00
