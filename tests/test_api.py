"""Tests for the FastAPI backend endpoints."""

import csv
import io
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Override DATABASE_URL before importing the app
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ALLOWED_ORIGINS"] = "*"


@pytest.fixture
def client(db_session, monkeypatch):
    """Create a test client with patched database.

    We need to ensure the server's get_db() uses the test's in-memory SQLite.
    The server calls _db.get_db() where _db = cloudledger.database.
    The conftest autouse fixture already patches cloudledger.database.get_db.
    We also need to ensure create_all_tables in the lifespan is a no-op.
    """
    import cloudledger.database
    import backend.server as server_mod

    # Patch create_all_tables both at module level and as the server's imported reference
    monkeypatch.setattr(cloudledger.database, "create_all_tables", lambda: None)
    monkeypatch.setattr(server_mod, "create_all_tables", lambda: None)

    from backend.server import app
    from backend.auth import create_token

    # Create a test user directly in the DB so we don't need the register endpoint
    from cloudledger.database import User
    from backend.auth import hash_password as _hash
    with db_session() as session:
        user = User(email="test@example.com", password_hash=_hash("testpass123"), name="Test")
        session.add(user)
        session.flush()
        uid = user.id

    token = create_token(uid, "test@example.com")

    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as tc:
        yield tc


def _seed_full_pipeline(db_session):
    """Seed billing data, invoices, resources, and variance for 2 periods."""
    from cloudledger.database import RawBillingLine, Invoice, Resource, VarianceReport

    with db_session() as session:
        for period_start, invoice_id, cost in [
            (date(2025, 1, 1), "INV-JAN", Decimal("5000.00")),
            (date(2025, 2, 1), "INV-FEB", Decimal("5800.00")),
        ]:
            session.add(Invoice(
                user_id=1,
                invoice_id=invoice_id,
                billing_period_start=period_start,
                billing_period_end=date(period_start.year, period_start.month, 28),
                total_billed_cost=cost,
                total_line_items=5,
                attributed_cost=cost * Decimal("0.85"),
                unattributed_cost=cost * Decimal("0.15"),
                attribution_coverage_pct=Decimal("85.00"),
            ))

            for i in range(5):
                session.add(RawBillingLine(
                    user_id=1,
                    invoice_id=invoice_id,
                    billing_period_start=period_start,
                    billing_period_end=date(period_start.year, period_start.month, 28),
                    service_name="Amazon EC2",
                    resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-{i:04d}",
                    resource_name=f"i-{i:04d}",
                    billed_cost=cost / 5,
                    charge_type="Usage",
                    provider="AWS",
                ))

                session.add(Resource(
                    resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-{i:04d}",
                    resource_name=f"i-{i:04d}",
                    service_name="Amazon EC2",
                    billing_period_start=period_start,
                    total_cost=cost / 5,
                    in_terraform_state=(i < 3),
                    iac_source="terraform" if i < 3 else "none",
                    team="backend" if i < 2 else None,
                ))

        # Add variance rows
        for i in range(5):
            delta = Decimal("160.00") if i < 3 else Decimal("-20.00")
            session.add(VarianceReport(
                resource_id=f"arn:aws:ec2:us-east-1:123:instance/i-{i:04d}",
                resource_name=f"i-{i:04d}",
                service_name="Amazon EC2",
                prior_period_start=date(2025, 1, 1),
                current_period_start=date(2025, 2, 1),
                prior_cost=Decimal("1000.00"),
                current_cost=Decimal("1160.00") if i < 3 else Decimal("980.00"),
                delta_dollars=delta,
                delta_pct=Decimal("16.00") if i < 3 else Decimal("-2.00"),
                reason_code="usage_growth" if i < 3 else "steady_state",
                confidence_score=Decimal("0.95"),
                in_terraform_state=(i < 3),
                iac_source="terraform" if i < 3 else "none",
                team="backend" if i < 2 else None,
            ))


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_periods_empty(client):
    resp = client.get("/api/periods")
    assert resp.status_code == 200
    assert resp.json() == {"periods": []}


def test_periods_with_data(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/periods")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["periods"]) == 2
    assert "2025-02" in data["periods"]
    assert "2025-01" in data["periods"]


def test_bill_overview(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/bill-overview?prior_period=2025-01&current_period=2025-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["prior_total"] == 5000.0
    assert data["current_total"] == 5800.0
    assert data["delta"] == 800.0


def test_bill_overview_invalid_period(client):
    resp = client.get("/api/bill-overview?prior_period=invalid&current_period=2025-02")
    assert resp.status_code == 400


def test_ingestion_stats(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/ingestion-stats?current_period=2025-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource_count"] == 5
    assert data["terraform_resources"] == 3
    assert len(data["services"]) >= 1
    assert data["data_quality"]["missing_resource_id"] == 0


def test_variance_by_service(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/variance-by-service?current_period=2025-02")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["services"]) >= 1
    assert len(data["resources"]) == 5
    assert len(data["reasons"]) >= 1
    assert data["total_variance"] > 0


def test_root_causes(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/root-causes?current_period=2025-02")
    assert resp.status_code == 200
    data = resp.json()
    assert "planned" in data
    assert "drift" in data
    assert "usage" in data
    assert "edge_cases" in data
    assert data["usage"]["count"] >= 1


def test_close_packet(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/close-packet?current_period=2025-02&prior_period=2025-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost"] == 5800.0
    assert data["prior_cost"] == 5000.0
    assert data["resource_count"] == 5
    assert len(data["reasons"]) >= 1


def test_engineering_view(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/engineering-view?current_period=2025-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["managed_count"] == 3
    assert data["unmanaged_count"] == 2
    assert data["total_resources"] == 5
    assert len(data["teams"]) >= 1


def test_trends(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["totals"]) == 2
    assert data["totals"][0]["period"] == "2025-01"


def test_gl_export(client, db_session):
    _seed_full_pipeline(db_session)
    resp = client.get("/api/gl-export?current_period=2025-02")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    lines = resp.text.strip().split("\n")
    assert len(lines) == 6  # header + 5 rows


def test_github_status_unconfigured(client):
    resp = client.get("/api/github/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False


def test_upload_rejects_non_csv(client):
    resp = client.post("/api/upload", files=[("files", ("test.txt", b"hello", "text/plain"))])
    assert resp.status_code == 400


def test_upload_csv(client):
    """Upload a valid CSV and verify it's ingested."""
    csv_content = (
        "InvoiceId,BillingPeriodStart,BillingPeriodEnd,ServiceName,ResourceId,"
        "ResourceName,BilledCost,ChargeType,ChargePeriodStart\n"
        "INV-001,2025-03-01,2025-03-31,Amazon S3,arn:aws:s3:::bucket-1,"
        "bucket-1,50.00,Usage,2025-03-01T00:00:00\n"
        "INV-001,2025-03-01,2025-03-31,Amazon S3,arn:aws:s3:::bucket-2,"
        "bucket-2,75.00,Usage,2025-03-01T00:00:00\n"
    )
    resp = client.post("/api/upload", files=[("files", ("march.csv", csv_content.encode(), "text/csv"))])
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_inserted"] == 2
    assert data["files_count"] == 1


def test_chat_requires_api_key(client, monkeypatch):
    import backend.server as server_mod
    monkeypatch.setattr(server_mod, "ANTHROPIC_API_KEY", "")
    resp = client.post("/api/chat", json={
        "message": "hello", "screen": "Overview", "screen_data": None, "history": [],
    })
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]
