"""Tests for the variance engine."""

from datetime import date
from decimal import Decimal

from cloudledger.database import Resource, VarianceReport
from cloudledger.variance import compute_variance


def test_drift_reason_code(db_session):
    """Resource not in terraform state should get reason_code='drift'."""
    with db_session() as session:
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-drift",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 1, 1),
            total_cost=Decimal("500.00"),
            in_terraform_state=False,
        ))
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-drift",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 2, 1),
            total_cost=Decimal("600.00"),
            in_terraform_state=False,
        ))

    summary = compute_variance("2025-01", "2025-02")
    assert summary["by_reason"].get("drift", {}).get("count", 0) >= 1

    with db_session() as session:
        vr = session.query(VarianceReport).filter_by(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-drift"
        ).first()
        assert vr is not None
        assert vr.reason_code == "drift"


def test_delta_dollars_computed(db_session):
    """delta_dollars should equal current_cost - prior_cost."""
    with db_session() as session:
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-delta",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 1, 1),
            total_cost=Decimal("1000.00"),
            in_terraform_state=True,
        ))
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-delta",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 2, 1),
            total_cost=Decimal("1250.00"),
            in_terraform_state=True,
        ))

    compute_variance("2025-01", "2025-02")

    with db_session() as session:
        vr = session.query(VarianceReport).filter_by(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-delta"
        ).first()
        assert vr is not None
        assert float(vr.delta_dollars) == 250.00
        assert float(vr.current_cost) == 1250.00
        assert float(vr.prior_cost) == 1000.00


def test_confidence_score_in_range(db_session):
    """confidence_score should be between 0 and 1."""
    with db_session() as session:
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-conf",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 1, 1),
            total_cost=Decimal("200.00"),
            in_terraform_state=True,
        ))
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-conf",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 2, 1),
            total_cost=Decimal("250.00"),
            in_terraform_state=True,
        ))

    compute_variance("2025-01", "2025-02")

    with db_session() as session:
        vr = session.query(VarianceReport).filter_by(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-conf"
        ).first()
        assert vr is not None
        assert 0 <= float(vr.confidence_score) <= 1
