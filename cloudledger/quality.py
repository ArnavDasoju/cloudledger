"""Data quality checks for billing data."""

import logging
from datetime import date
from decimal import Decimal
from typing import List, Dict

from sqlalchemy import func

from cloudledger.database import get_db, RawBillingLine, Invoice

logger = logging.getLogger(__name__)


def run_quality_checks(billing_period: str) -> List[Dict]:
    """Run all data quality checks for a billing period (YYYY-MM format).

    Returns a list of check results, each with keys: check, status, detail.
    """
    period_start = date.fromisoformat(f"{billing_period}-01")
    results = []

    with get_db() as session:
        # 1. Invoice reconciliation — sum of lines matches invoice total
        line_sum = session.query(func.sum(RawBillingLine.billed_cost)).filter(
            RawBillingLine.billing_period_start == period_start
        ).scalar() or Decimal("0")

        inv = session.query(Invoice).filter(
            Invoice.billing_period_start == period_start
        ).first()

        if inv:
            invoice_total = Decimal(str(inv.total_billed_cost or 0))
            diff = abs(float(line_sum) - float(invoice_total))
            results.append({
                "check": "Invoice reconciliation",
                "status": "pass" if diff < 0.01 else "fail",
                "detail": f"Line sum: ${float(line_sum):,.2f}, Invoice: ${float(invoice_total):,.2f}, Diff: ${diff:.2f}",
            })
        else:
            results.append({
                "check": "Invoice reconciliation",
                "status": "warn",
                "detail": "No invoice found for this period",
            })

        # 2. No duplicate billing lines
        dupes = (
            session.query(
                RawBillingLine.invoice_id,
                RawBillingLine.resource_id,
                RawBillingLine.charge_period_start,
                func.count(RawBillingLine.id),
            )
            .filter(RawBillingLine.billing_period_start == period_start)
            .group_by(
                RawBillingLine.invoice_id,
                RawBillingLine.resource_id,
                RawBillingLine.charge_period_start,
            )
            .having(func.count(RawBillingLine.id) > 1)
            .all()
        )
        results.append({
            "check": "No duplicate billing lines",
            "status": "pass" if len(dupes) == 0 else "warn",
            "detail": f"{len(dupes)} duplicate groups found" if dupes else "No duplicates",
        })

        # 3. No missing resource IDs
        missing_rid = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == period_start,
            (RawBillingLine.resource_id == None) | (RawBillingLine.resource_id == ""),
        ).scalar() or 0

        total_lines = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == period_start
        ).scalar() or 0

        results.append({
            "check": "Resource ID coverage",
            "status": "pass" if missing_rid == 0 else "warn",
            "detail": f"{missing_rid} of {total_lines} lines missing resource_id",
        })

        # 4. No unexpected negative costs (non-credit)
        negative_lines = session.query(func.count(RawBillingLine.id)).filter(
            RawBillingLine.billing_period_start == period_start,
            RawBillingLine.billed_cost < 0,
            RawBillingLine.charge_type != "Credit",
            RawBillingLine.charge_type != "Refund",
        ).scalar() or 0

        results.append({
            "check": "No negative costs (non-credit)",
            "status": "pass" if negative_lines == 0 else "warn",
            "detail": f"{negative_lines} non-credit negative cost lines",
        })

        # 5. Attribution coverage
        if inv:
            coverage = float(inv.attribution_coverage_pct or 0)
            results.append({
                "check": "Attribution coverage >= 80%",
                "status": "pass" if coverage >= 80 else "fail",
                "detail": f"Attribution coverage: {coverage:.1f}%",
            })
        else:
            results.append({
                "check": "Attribution coverage >= 80%",
                "status": "warn",
                "detail": "No invoice data to check attribution",
            })

    return results
