"""Characterization tests for the variance classification decision tree.

Every branch of compute_variance's reason-code logic is tested here,
including the classify_resource pure function and its integration
through the full compute_variance pipeline.
"""

from datetime import date, timedelta
from decimal import Decimal

from cloudledger.database import Resource, ChangeEvent, VarianceReport, RawBillingLine
from cloudledger.variance import (
    compute_variance,
    classify_resource,
    _detect_charge_type_reason,
    _build_evidence_chain,
    _days_in_month,
)


# ── Helper ───────────────────────────────────────────────────────────────────

def _add_resource(session, rid, period, cost, in_tf=True, team=None,
                  service="Amazon EC2", iac_source=None, tf_module=None):
    """Seed a Resource row for a given period."""
    session.add(Resource(
        resource_id=rid,
        service_name=service,
        billing_period_start=period,
        total_cost=Decimal(str(cost)),
        in_terraform_state=in_tf,
        team=team,
        iac_source=iac_source or ("terraform" if in_tf else "none"),
        terraform_module=tf_module,
    ))


def _add_change_event(session, rid, event_date):
    """Seed a ChangeEvent for a resource."""
    session.add(ChangeEvent(
        resource_id=rid,
        event_type="terraform_apply",
        event_date=event_date,
        pr_number="42",
        pr_title="Scale capacity",
        pr_author="infra-bot",
    ))


def _get_vr(db_session, rid):
    """Fetch the VarianceReport for a resource_id as a plain dict (avoids DetachedInstanceError)."""
    with db_session() as session:
        vr = session.query(VarianceReport).filter_by(resource_id=rid).first()
        if vr is None:
            return None
        # Copy attributes to a SimpleNamespace so we can access them outside the session
        from types import SimpleNamespace
        return SimpleNamespace(
            reason_code=vr.reason_code,
            confidence_score=vr.confidence_score,
            prior_cost=vr.prior_cost,
            current_cost=vr.current_cost,
            delta_dollars=vr.delta_dollars,
            delta_pct=vr.delta_pct,
            excluded=vr.excluded,
            evidence=vr.evidence,
            evidence_chain=vr.evidence_chain,
            pr_number=vr.pr_number,
            in_terraform_state=vr.in_terraform_state,
        )


# ── Reason code branches ─────────────────────────────────────────────────────

class TestReasonCodeBranches:
    """Each test targets a specific branch in the classification decision tree."""

    def test_planned_in_tf_with_change_event(self, db_session):
        """In TF + change event within window -> 'planned'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-planned"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=True)
            _add_resource(s, rid, date(2025, 2, 1), 1500, in_tf=True)
            _add_change_event(s, rid, date(2025, 2, 3))  # within +/-7 day window

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "planned"
        assert float(vr.confidence_score) == 0.95

    def test_usage_growth_in_tf_no_event_big_delta(self, db_session):
        """In TF, no change event, normalized delta > 5% -> 'usage_growth'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-growth"
        with db_session() as s:
            # Both months 31 days to isolate the logic from day-normalization
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=True)
            _add_resource(s, rid, date(2025, 3, 1), 1200, in_tf=True)  # +20%

        compute_variance("2025-01", "2025-03")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "usage_growth"

    def test_steady_state_in_tf_no_event_small_delta(self, db_session):
        """In TF, no change event, normalized delta <= 5% -> 'steady_state'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-steady"
        with db_session() as s:
            # Same-length months, tiny cost change
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=True)
            _add_resource(s, rid, date(2025, 3, 1), 1030, in_tf=True)  # +3%

        compute_variance("2025-01", "2025-03")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "steady_state"

    def test_new_resource(self, db_session):
        """Resource only in current period -> 'new_resource'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-new"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 2, 1), 500, in_tf=True)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "new_resource"
        assert float(vr.prior_cost) == 0
        assert float(vr.current_cost) == 500

    def test_removed_resource(self, db_session):
        """Resource only in prior period -> 'removed_resource'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-removed"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 800, in_tf=True)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "removed_resource"
        assert float(vr.current_cost) == 0
        assert float(vr.prior_cost) == 800

    def test_orphan_sdk_created_not_in_tf_has_team(self, db_session):
        """Not in TF, has team tag -> 'orphan_sdk_created'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-orphan-sdk"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=False, team="backend")
            _add_resource(s, rid, date(2025, 2, 1), 1200, in_tf=False, team="backend")

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "orphan_sdk_created"
        assert float(vr.confidence_score) == 0.70

    def test_orphan_unknown_not_in_tf_no_tags_high_cost(self, db_session):
        """Not in TF, no team, current cost >= $200 -> 'orphan_unknown'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-orphan-unk"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=False)
            _add_resource(s, rid, date(2025, 2, 1), 600, in_tf=False)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "orphan_unknown"
        assert float(vr.confidence_score) == 0.50

    def test_legacy_untracked_not_in_tf_low_cost(self, db_session):
        """Not in TF, no team, has prior cost, current < $200 -> 'legacy_untracked'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-legacy"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 100, in_tf=False)
            _add_resource(s, rid, date(2025, 2, 1), 50, in_tf=False)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "legacy_untracked"
        assert float(vr.confidence_score) == 0.60

    def test_non_terraform_iac_cloudformation_via_billing_tags(self, db_session):
        """Not in TF, but billing line has CloudFormation tags -> 'non_terraform_iac'.

        Tags are read from RawBillingLine (not Resource, which has no tags column).
        """
        rid = "arn:aws:ec2:us-east-1:123:instance/i-cfn"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=False, team="infra")
            _add_resource(s, rid, date(2025, 2, 1), 1100, in_tf=False, team="infra")
            s.add(RawBillingLine(
                resource_id=rid,
                billing_period_start=date(2025, 2, 1),
                charge_type="Usage",
                billed_cost=Decimal("1100"),
                tags={"aws:cloudformation:stack-name": "my-stack", "team": "infra"},
            ))

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "non_terraform_iac"
        assert float(vr.confidence_score) == 0.85

    def test_non_terraform_iac_managed_by_pulumi(self, db_session):
        """Not in TF, managed_by=pulumi tag on billing line -> 'non_terraform_iac'."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-pulumi"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=False, team="platform")
            _add_resource(s, rid, date(2025, 2, 1), 550, in_tf=False, team="platform")
            s.add(RawBillingLine(
                resource_id=rid,
                billing_period_start=date(2025, 2, 1),
                charge_type="Usage",
                billed_cost=Decimal("550"),
                tags={"managed_by": "pulumi", "team": "platform"},
            ))

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "non_terraform_iac"


# ── Edge-case charge type detection ──────────────────────────────────────────

class TestEdgeCaseChargeTypeDetection:
    """Tests for _detect_charge_type_reason — the function that maps
    billing charge types and descriptions to edge-case reason codes."""

    def test_savings_plan_covered_usage(self):
        assert _detect_charge_type_reason(["SavingsPlanCoveredUsage"], "") == "savings_plan_allocation"

    def test_savings_plan_negation(self):
        assert _detect_charge_type_reason(["SavingsPlanNegation"], "") == "savings_plan_allocation"

    def test_savings_plan_recurring_fee(self):
        assert _detect_charge_type_reason(["SavingsPlanRecurringFee"], "") == "savings_plan_allocation"

    def test_ri_fee(self):
        assert _detect_charge_type_reason(["RIFee"], "") == "ri_coverage_shift"

    def test_discounted_usage(self):
        assert _detect_charge_type_reason(["DiscountedUsage"], "") == "ri_coverage_shift"

    def test_credit(self):
        assert _detect_charge_type_reason(["Credit"], "") == "credit_applied"

    def test_refund(self):
        assert _detect_charge_type_reason(["Refund"], "") == "credit_applied"

    def test_bundled_discount(self):
        assert _detect_charge_type_reason(["BundledDiscount"], "") == "credit_applied"

    def test_marketplace_description(self):
        assert _detect_charge_type_reason(["Usage"], "AWS Marketplace subscription") == "marketplace_subscription"

    def test_spot_description(self):
        assert _detect_charge_type_reason(["Usage"], "SpotUsage for i-abc") == "spot_price_volatility"

    def test_spot_charge_type(self):
        assert _detect_charge_type_reason(["SpotUsage"], "some instance") == "spot_price_volatility"

    def test_data_transfer_description(self):
        assert _detect_charge_type_reason(["Usage"], "DataTransfer-Out-Bytes") == "cross_service_transfer"

    def test_nat_gateway_description(self):
        assert _detect_charge_type_reason(["Usage"], "NAT Gateway processing") == "cross_service_transfer"

    def test_cloudfront_description(self):
        assert _detect_charge_type_reason(["Usage"], "CloudFront data transfer") == "cross_service_transfer"

    def test_no_match_returns_none(self):
        assert _detect_charge_type_reason(["Usage"], "EC2 running hours") is None

    def test_empty_inputs(self):
        assert _detect_charge_type_reason([], "") is None
        assert _detect_charge_type_reason([], None) is None

    def test_charge_type_takes_priority_over_description(self):
        """If charge type matches, description is not checked."""
        result = _detect_charge_type_reason(["Credit"], "marketplace subscription")
        assert result == "credit_applied"  # Not marketplace_subscription


class TestEdgeCaseIntegration:
    """Edge cases flowing through compute_variance end-to-end."""

    def test_savings_plan_excluded_from_normal_classification(self, db_session):
        """A resource with SavingsPlan charge type should be excluded=True."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-sp"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=True)
            _add_resource(s, rid, date(2025, 2, 1), 600, in_tf=True)
            s.add(RawBillingLine(
                resource_id=rid,
                billing_period_start=date(2025, 2, 1),
                charge_type="SavingsPlanCoveredUsage",
                billed_cost=Decimal("600"),
            ))

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "savings_plan_allocation"
        assert vr.excluded is True
        assert float(vr.confidence_score) == 0.90

    def test_credit_excluded(self, db_session):
        """Credit charge type -> excluded with credit_applied reason."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-credit"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=True)
            _add_resource(s, rid, date(2025, 2, 1), 400, in_tf=True)
            s.add(RawBillingLine(
                resource_id=rid,
                billing_period_start=date(2025, 2, 1),
                charge_type="Credit",
                billed_cost=Decimal("-100"),
            ))

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "credit_applied"
        assert vr.excluded is True


# ── Evidence chain construction ──────────────────────────────────────────────

class TestEvidenceChain:
    """Tests for _build_evidence_chain — the structured audit trail."""

    def test_edge_case_short_circuits(self):
        """Edge case evidence chain should only have the edge_case_detection step."""
        chain = _build_evidence_chain(
            reason_code="savings_plan_allocation",
            rid="r1", prior_cost=Decimal("100"), current_cost=Decimal("120"),
            delta_pct=Decimal("20"), in_tf=True, iac_source="terraform",
            tf_module="modules/compute", change_event=None,
            charge_types=["SavingsPlanCoveredUsage"], is_excluded=True,
        )
        assert chain["reason_code"] == "savings_plan_allocation"
        assert len(chain["classification_steps"]) == 1
        assert chain["classification_steps"][0]["step"] == "edge_case_detection"

    def test_new_resource_chain(self):
        chain = _build_evidence_chain(
            reason_code="new_resource",
            rid="r1", prior_cost=Decimal("0"), current_cost=Decimal("500"),
            delta_pct=None, in_tf=True, iac_source="terraform",
            tf_module=None, change_event=None,
            charge_types=[], is_excluded=False,
        )
        assert len(chain["classification_steps"]) == 1
        assert chain["classification_steps"][0]["result"] == "new_resource"

    def test_removed_resource_chain(self):
        chain = _build_evidence_chain(
            reason_code="removed_resource",
            rid="r1", prior_cost=Decimal("500"), current_cost=Decimal("0"),
            delta_pct=Decimal("-100"), in_tf=True, iac_source="terraform",
            tf_module=None, change_event=None,
            charge_types=[], is_excluded=False,
        )
        assert len(chain["classification_steps"]) == 1
        assert chain["classification_steps"][0]["result"] == "removed_resource"

    def test_managed_with_change_event(self):
        """Full chain: iac_lookup + change_event_match + classification."""
        class FakeCE:
            pr_number = "99"
            pr_title = "Resize cluster"

        chain = _build_evidence_chain(
            reason_code="planned",
            rid="r1", prior_cost=Decimal("100"), current_cost=Decimal("200"),
            delta_pct=Decimal("100"), in_tf=True, iac_source="terraform",
            tf_module="modules/eks", change_event=FakeCE(),
            charge_types=[], is_excluded=False,
        )
        steps = chain["classification_steps"]
        assert len(steps) == 3
        assert steps[0]["step"] == "iac_lookup"
        assert steps[0]["result"] == "managed"
        assert steps[1]["step"] == "change_event_match"
        assert steps[1]["result"] == "matched"
        assert "PR #99" in steps[1]["detail"]
        assert steps[2]["step"] == "classification"
        assert steps[2]["result"] == "planned"

    def test_managed_without_change_event(self):
        """Chain for usage_growth: iac_lookup + no_match + classification."""
        chain = _build_evidence_chain(
            reason_code="usage_growth",
            rid="r1", prior_cost=Decimal("100"), current_cost=Decimal("200"),
            delta_pct=Decimal("100"), in_tf=True, iac_source="terraform",
            tf_module="modules/compute", change_event=None,
            charge_types=[], is_excluded=False,
        )
        steps = chain["classification_steps"]
        assert len(steps) == 3
        assert steps[1]["step"] == "change_event_match"
        assert steps[1]["result"] == "no_match"

    def test_unmanaged_chain(self):
        """Unmanaged resource: iac_lookup shows 'unmanaged'."""
        chain = _build_evidence_chain(
            reason_code="orphan_unknown",
            rid="r1", prior_cost=Decimal("100"), current_cost=Decimal("200"),
            delta_pct=Decimal("100"), in_tf=False, iac_source="none",
            tf_module=None, change_event=None,
            charge_types=[], is_excluded=False,
        )
        steps = chain["classification_steps"]
        assert steps[0]["result"] == "unmanaged"

    def test_inputs_section_populated(self):
        """The inputs section should contain all classification inputs."""
        chain = _build_evidence_chain(
            reason_code="planned",
            rid="r1", prior_cost=Decimal("100"), current_cost=Decimal("200"),
            delta_pct=Decimal("100"), in_tf=True, iac_source="terraform",
            tf_module="modules/eks", change_event=None,
            charge_types=["Usage"], is_excluded=False,
        )
        inputs = chain["inputs"]
        assert inputs["resource_id"] == "r1"
        assert inputs["prior_cost"] == 100.0
        assert inputs["current_cost"] == 200.0
        assert inputs["in_iac"] is True
        assert inputs["iac_source"] == "terraform"
        assert inputs["charge_types"] == ["Usage"]


# ── Day-length normalization ─────────────────────────────────────────────────

class TestDayLengthNormalization:
    """Verify that month-length differences don't produce false usage_growth."""

    def test_days_in_month_helper(self):
        assert _days_in_month(date(2025, 1, 1)) == 31
        assert _days_in_month(date(2025, 2, 1)) == 28
        assert _days_in_month(date(2024, 2, 1)) == 29  # leap year
        assert _days_in_month(date(2025, 4, 1)) == 30

    def test_feb_to_jan_normalization_prevents_false_growth(self, db_session):
        """A resource with identical per-day cost in Jan (31d) and Feb (28d)
        should be classified as steady_state, not usage_growth, because the
        day-normalization should cancel out the month-length difference.
        """
        rid = "arn:aws:ec2:us-east-1:123:instance/i-daylen"
        daily_cost = Decimal("32.26")
        jan_cost = daily_cost * 31  # ~1000.06
        feb_cost = daily_cost * 28  # ~903.28

        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), jan_cost, in_tf=True)
            _add_resource(s, rid, date(2025, 2, 1), feb_cost, in_tf=True)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert vr.reason_code == "steady_state", (
            f"Expected steady_state but got {vr.reason_code}; "
            f"day-normalization should cancel out the month-length difference"
        )


# ── Confidence scores ────────────────────────────────────────────────────────

class TestConfidenceScores:
    """Confidence scores should reflect classification certainty."""

    def test_terraform_managed_high_confidence(self, db_session):
        """TF-managed resources get confidence 0.95."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-tf-conf"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 1000, in_tf=True)
            _add_resource(s, rid, date(2025, 3, 1), 1500, in_tf=True)

        compute_variance("2025-01", "2025-03")
        vr = _get_vr(db_session, rid)
        assert float(vr.confidence_score) == 0.95

    def test_unmanaged_no_team_low_confidence(self, db_session):
        """Unmanaged + no team -> confidence 0.50."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-low-conf"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=False)
            _add_resource(s, rid, date(2025, 2, 1), 600, in_tf=False)

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert float(vr.confidence_score) == 0.50

    def test_unmanaged_with_team_medium_confidence(self, db_session):
        """Unmanaged + has team -> confidence 0.70."""
        rid = "arn:aws:ec2:us-east-1:123:instance/i-med-conf"
        with db_session() as s:
            _add_resource(s, rid, date(2025, 1, 1), 500, in_tf=False, team="backend")
            _add_resource(s, rid, date(2025, 2, 1), 600, in_tf=False, team="backend")

        compute_variance("2025-01", "2025-02")
        vr = _get_vr(db_session, rid)
        assert float(vr.confidence_score) == 0.70


# ── Summary structure ────────────────────────────────────────────────────────

class TestVarianceSummary:
    """compute_variance returns a well-structured summary dict."""

    def test_summary_has_required_keys(self, db_session):
        with db_session() as s:
            _add_resource(s, "r1", date(2025, 1, 1), 100, in_tf=True)
            _add_resource(s, "r1", date(2025, 2, 1), 120, in_tf=True)

        summary = compute_variance("2025-01", "2025-02")
        assert "total_delta" in summary
        assert "by_reason" in summary
        assert "attribution_coverage_pct" in summary
        assert isinstance(summary["by_reason"], dict)

    def test_empty_periods_return_empty_summary(self, db_session):
        """No resources in either period -> empty summary, no crash."""
        summary = compute_variance("2030-01", "2030-02")
        assert summary["total_delta"] == 0
        assert summary["by_reason"] == {}

    def test_total_delta_is_sum_of_all_deltas(self, db_session):
        """total_delta should equal the sum across all resources."""
        with db_session() as s:
            _add_resource(s, "r1", date(2025, 1, 1), 100, in_tf=True)
            _add_resource(s, "r1", date(2025, 2, 1), 150, in_tf=True)
            _add_resource(s, "r2", date(2025, 1, 1), 200, in_tf=True)
            _add_resource(s, "r2", date(2025, 2, 1), 180, in_tf=True)

        summary = compute_variance("2025-01", "2025-02")
        # r1: +50, r2: -20, total: +30
        assert summary["total_delta"] == 30.0
