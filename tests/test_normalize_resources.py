"""Tests for normalize_resources and _derive_environment."""

import json
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal

import pytest

from cloudledger.database import RawBillingLine, Resource
from cloudledger.normalize import normalize_resources, _derive_environment


# ── _derive_environment unit tests ───────────────────────────────────────────

class TestDeriveEnvironment:
    """Environment derivation checks tags first, then TF module, then name."""

    def test_tag_environment_prod(self):
        assert _derive_environment("my-server", {"environment": "production"}, "") == "production"

    def test_tag_env_shorthand(self):
        assert _derive_environment("my-server", {"env": "prod"}, "") == "production"

    def test_tag_staging(self):
        assert _derive_environment("my-server", {"Environment": "staging"}, "") == "staging"

    def test_tag_dev(self):
        assert _derive_environment("my-server", {"environment": "development"}, "") == "dev"

    def test_tag_uat(self):
        assert _derive_environment("my-server", {"env": "uat"}, "") == "staging"

    def test_terraform_module_prod(self):
        assert _derive_environment("my-server", {}, "modules/production/compute") == "production"

    def test_terraform_module_staging(self):
        assert _derive_environment("my-server", {}, "modules/staging/rds") == "staging"

    def test_resource_name_prod(self):
        assert _derive_environment("api-prod-us-east-1", {}, "") == "production"

    def test_resource_name_dev(self):
        assert _derive_environment("sandbox-test-instance", {}, "") == "dev"

    def test_fallback_to_other(self):
        assert _derive_environment("my-resource", {}, "") == "other"

    def test_none_inputs(self):
        assert _derive_environment(None, None, None) == "other"

    def test_empty_inputs(self):
        assert _derive_environment("", {}, "") == "other"

    def test_tag_takes_priority_over_name(self):
        """Tags should win over resource name."""
        result = _derive_environment("my-prod-server", {"environment": "staging"}, "")
        assert result == "staging"

    def test_module_takes_priority_over_name(self):
        """TF module should win over resource name."""
        result = _derive_environment("my-prod-server", {}, "modules/staging/compute")
        assert result == "staging"


# ── normalize_resources integration tests ────────────────────────────────────

def _write_tf_state(resources):
    """Write a minimal terraform state JSON with the given resources.
    Each resource is a dict with keys: type, name, id, module (optional).
    """
    state = {
        "version": 4,
        "resources": [
            {
                "type": r["type"],
                "name": r["name"],
                "module": r.get("module", ""),
                "instances": [
                    {"attributes": {"id": r["id"]}}
                ]
            }
            for r in resources
        ]
    }
    fd, path = tempfile.mkstemp(suffix=".tfstate")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    return path


class TestNormalizeResources:

    def test_resource_created_from_billing_line(self, db_session):
        """A billing line should produce a resource row."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id="arn:aws:ec2:us-east-1:123:instance/i-abc",
                resource_name="i-abc",
                billed_cost=Decimal("500.00"),
                region="us-east-1",
            ))

        count = normalize_resources()
        assert count == 1

        with db_session() as s:
            r = s.query(Resource).first()
            assert r.resource_id == "arn:aws:ec2:us-east-1:123:instance/i-abc"
            assert float(r.total_cost) == 500.00
            assert r.in_terraform_state is False  # no TF state provided
            assert r.iac_source == "none"

    def test_terraform_state_marks_managed(self, db_session):
        """Resources found in TF state should be marked in_terraform_state=True."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-managed"
        tf_path = _write_tf_state([{
            "type": "aws_instance",
            "name": "web",
            "id": rid,
            "module": "module.compute",
        }])

        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id=rid,
                billed_cost=Decimal("500.00"),
            ))

        try:
            normalize_resources(terraform_state_path=tf_path)
            with db_session() as s:
                r = s.query(Resource).first()
                assert r.in_terraform_state is True
                assert r.iac_source == "terraform"
                assert r.terraform_module == "module.compute"
        finally:
            os.unlink(tf_path)

    def test_team_extracted_from_tags(self, db_session):
        """Team and cost_center should be extracted from billing line tags."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id="arn:aws:ec2:us-east-1:123:instance/i-tagged",
                billed_cost=Decimal("500.00"),
                tags={"team": "backend", "cost_center": "CC-1001"},
            ))

        normalize_resources()
        with db_session() as s:
            r = s.query(Resource).first()
            assert r.team == "backend"
            assert r.cost_center == "CC-1001"

    def test_tags_as_json_string(self, db_session):
        """Tags stored as a JSON string should be parsed correctly."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id="arn:aws:ec2:us-east-1:123:instance/i-strtag",
                billed_cost=Decimal("500.00"),
                tags='{"team": "data-eng"}',
            ))

        normalize_resources()
        with db_session() as s:
            r = s.query(Resource).first()
            assert r.team == "data-eng"

    def test_null_resource_id_skipped(self, db_session):
        """Billing lines with null resource_id should be skipped."""
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id=None,
                billed_cost=Decimal("500.00"),
            ))

        count = normalize_resources()
        assert count == 0

    def test_multiple_lines_same_resource_aggregated(self, db_session):
        """Multiple billing lines for the same resource should aggregate cost."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-multi"
        with db_session() as s:
            for cost in [Decimal("100"), Decimal("200"), Decimal("300")]:
                s.add(RawBillingLine(
                    invoice_id="INV-001",
                    billing_period_start=date(2025, 1, 1),
                    billing_period_end=date(2025, 1, 31),
                    service_name="Amazon EC2",
                    resource_id=rid,
                    resource_name="i-multi",
                    billed_cost=cost,
                ))

        normalize_resources()
        with db_session() as s:
            r = s.query(Resource).first()
            assert abs(float(r.total_cost) - 600.00) < 0.01

    def test_upsert_updates_existing_resource(self, db_session):
        """Calling normalize_resources twice should update the existing resource,
        not create a duplicate row."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-upsert"
        with db_session() as s:
            s.add(RawBillingLine(
                invoice_id="INV-001",
                billing_period_start=date(2025, 1, 1),
                billing_period_end=date(2025, 1, 31),
                service_name="Amazon EC2",
                resource_id=rid,
                billed_cost=Decimal("500.00"),
            ))

        normalize_resources()

        # Verify initial state
        with db_session() as s:
            assert s.query(Resource).count() == 1
            r = s.query(Resource).first()
            assert float(r.total_cost) == 500.00
            assert r.in_terraform_state is False

        # Run again — should update, not dupe
        tf_path = _write_tf_state([{
            "type": "aws_instance", "name": "web", "id": rid,
        }])
        try:
            normalize_resources(terraform_state_path=tf_path)
            with db_session() as s:
                assert s.query(Resource).count() == 1  # still 1 row
                r = s.query(Resource).first()
                assert r.in_terraform_state is True  # updated
        finally:
            os.unlink(tf_path)
