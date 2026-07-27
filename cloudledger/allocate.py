"""Cost allocation engine — attributes billing lines to teams/cost centers."""

import logging
from decimal import Decimal

from sqlalchemy import func

from cloudledger.database import get_db, RawBillingLine, Invoice, Resource, Allocation

logger = logging.getLogger(__name__)


def run_allocations() -> int:
    """Allocate each billing line to a team/cost center.

    Attribution methods (in priority order):
    1. terraform_state — resource is in Terraform, team from state tags (confidence 0.95)
    2. tag — resource has team tag but not in Terraform (confidence 0.80)
    3. service_default — fallback based on service name heuristics (confidence 0.50)

    Returns number of allocations created.
    """
    count = 0

    with get_db() as session:
        # Clear existing allocations
        session.query(Allocation).delete()

        # Build resource lookup for team/cost_center/terraform
        resources = {}
        for r in session.query(Resource).all():
            key = (r.resource_id, r.billing_period_start)
            resources[key] = r

        # Process each billing line
        lines = session.query(RawBillingLine).all()

        for line in lines:
            resource = resources.get((line.resource_id, line.billing_period_start))

            team = None
            cost_center = None
            method = "unattributed"
            confidence = Decimal("0.30")

            if resource:
                if resource.in_terraform_state and resource.team:
                    team = resource.team
                    cost_center = resource.cost_center
                    method = "terraform_state"
                    confidence = Decimal("0.95")
                elif resource.team:
                    team = resource.team
                    cost_center = resource.cost_center
                    method = "tag"
                    confidence = Decimal("0.80")
                elif resource.service_name:
                    method = "service_default"
                    confidence = Decimal("0.50")

            alloc = Allocation(
                billing_line_id=line.id,
                resource_id=line.resource_id,
                billing_period_start=line.billing_period_start,
                team=team,
                cost_center=cost_center,
                allocated_cost=line.billed_cost,
                attribution_method=method,
                confidence_score=confidence,
            )
            session.add(alloc)
            count += 1

        # Update invoice attribution coverage
        invoices = session.query(Invoice).all()
        for inv in invoices:
            total_allocs = session.query(Allocation).filter(
                Allocation.billing_period_start == inv.billing_period_start,
            ).count()
            attributed = session.query(Allocation).filter(
                Allocation.billing_period_start == inv.billing_period_start,
                Allocation.team != None,
            ).count()

            if total_allocs > 0:
                inv.attribution_coverage_pct = Decimal(str(
                    round(attributed / total_allocs * 100, 2)
                ))

    logger.info("Created %d allocations", count)
    return count
