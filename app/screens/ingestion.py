"""Screen 2 — Ingestion."""

import streamlit as st
from cloudledger.database import get_db, RawBillingLine, Resource, Invoice
from sqlalchemy import func


def render():
    prior = st.session_state.get("prior_period")
    current = st.session_state.get("current_period")

    # Load stats
    with get_db() as session:
        billing_rows = session.query(func.count(RawBillingLine.id)).scalar() or 0
        resource_count = session.query(func.count(Resource.id)).filter(
            Resource.billing_period_start == current
        ).scalar() or 0
        tf_count = session.query(func.count(Resource.id)).filter(
            Resource.billing_period_start == current,
            Resource.in_terraform_state == True,
        ).scalar() or 0
        inv = session.query(Invoice).filter(Invoice.billing_period_start == current).first()
        total_cost = float(inv.total_billed_cost) if inv else 0
        coverage = float(inv.attribution_coverage_pct or 0) if inv else 0
        unattributed = float(inv.unattributed_cost or 0) if inv else 0

    st.markdown("### The tool ingests two streams simultaneously")
    st.markdown(
        "CloudLedger pulls billing data and engineering context in parallel. "
        "Billing lines are matched to Terraform-managed resources, and every dollar "
        "is reconciled against the infrastructure record."
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Billing Stream</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">{billing_rows:,}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Raw billing lines ingested</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Engineering Stream</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">{tf_count:,}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Terraform-managed resources matched</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("")

    current_label = current.strftime("%B %Y") if current else "Current"
    st.markdown(
        f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px;font-family:monospace;font-size:13px;color:#1E3A8A">
        <div>Invoice match: {resource_count:,} resources normalized</div>
        <div>Reconciliation: {coverage:.1f}% of spend attributed</div>
        <div>Unexplained variance: ${unattributed:,.0f}</div>
        </div>""",
        unsafe_allow_html=True,
    )
