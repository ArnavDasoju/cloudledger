"""Tests for the anomaly detection module."""

from datetime import date
from decimal import Decimal

from cloudledger.database import Resource, VarianceReport
from cloudledger.variance import compute_variance
from cloudledger.anomaly import detect_anomalies, anomaly_summary


def _seed_variance(db_session):
    """Create a mix of normal and anomalous resources."""
    with db_session() as session:
        # 8 normal resources with modest changes
        for i in range(8):
            for period_start, cost_base in [(date(2025, 1, 1), 1000), (date(2025, 2, 1), 1050)]:
                session.add(Resource(
                    resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-normal-{i}",
                    service_name="Amazon EC2",
                    billing_period_start=period_start,
                    total_cost=Decimal(str(cost_base + i * 10)),
                    in_terraform_state=True,
                    team="backend",
                ))

        # 1 anomalous resource — huge spike
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-spike",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 1, 1),
            total_cost=Decimal("200"),
            in_terraform_state=True,
            team="ml-ops",
        ))
        session.add(Resource(
            resource_id="arn:aws:ec2:us-east-1:123:instance/i-spike",
            service_name="Amazon EC2",
            billing_period_start=date(2025, 2, 1),
            total_cost=Decimal("5000"),
            in_terraform_state=True,
            team="ml-ops",
        ))

        # 1 anomalous resource — big new resource
        session.add(Resource(
            resource_id="arn:aws:rds:us-east-1:123:db:mega-db",
            service_name="Amazon RDS",
            billing_period_start=date(2025, 2, 1),
            total_cost=Decimal("8000"),
            in_terraform_state=False,
            team="data-eng",
        ))

    compute_variance("2025-01", "2025-02")


def test_anomalies_detected(db_session):
    """Anomaly detector should flag the spike and the big new resource."""
    _seed_variance(db_session)
    anomalies = detect_anomalies("2025-02")
    assert len(anomalies) >= 2

    resource_ids = {a["resource_id"] for a in anomalies}
    assert "arn:aws:ec2:us-east-1:123:instance/i-spike" in resource_ids
    assert "arn:aws:rds:us-east-1:123:db:mega-db" in resource_ids


def test_severity_ordering(db_session):
    """Anomalies should be sorted by severity descending."""
    _seed_variance(db_session)
    anomalies = detect_anomalies("2025-02")
    severities = [a["severity"] for a in anomalies]
    assert severities == sorted(severities, reverse=True)


def test_anomaly_summary_structure(db_session):
    """anomaly_summary should return a well-structured dict."""
    _seed_variance(db_session)
    anomalies = detect_anomalies("2025-02")
    summary = anomaly_summary(anomalies)
    assert summary["count"] >= 2
    assert summary["total_impact"] > 0
    assert summary["top_service"] is not None
    assert summary["top_team"] is not None


def test_no_anomalies_on_empty(db_session):
    """No anomalies on a period with no data."""
    anomalies = detect_anomalies("2030-01")
    assert anomalies == []
    summary = anomaly_summary(anomalies)
    assert summary["count"] == 0
