"""Screen 6 — Engineering view."""

import streamlit as st
from cloudledger.database import get_db, VarianceReport
from sqlalchemy import func


def render():
    current = st.session_state.get("current_period")

    # Load planned (PR-linked) and drift data
    with get_db() as session:
        planned_rows = (
            session.query(VarianceReport)
            .filter(
                VarianceReport.current_period_start == current,
                VarianceReport.reason_code == "planned",
            )
            .order_by(func.abs(VarianceReport.delta_dollars).desc())
            .limit(5)
            .all()
        )
        planned_total = sum(abs(float(r.delta_dollars or 0)) for r in planned_rows)
        top_pr = planned_rows[0] if planned_rows else None

        drift_rows = (
            session.query(VarianceReport)
            .filter(
                VarianceReport.current_period_start == current,
                VarianceReport.reason_code == "drift",
            )
            .all()
        )
        drift_total = sum(abs(float(r.delta_dollars or 0)) for r in drift_rows)
        drift_count = len(drift_rows)

    pr_label = f"PR #{top_pr.pr_number}" if top_pr and top_pr.pr_number else "Infrastructure Change"
    pr_author = top_pr.pr_author if top_pr else "engineering"

    st.markdown(f"### Jake's engineering view — his team's fingerprint on the bill")
    st.markdown(
        f"Jake, the platform engineer, sees the same data from the other side. "
        f"His {pr_label} accounts for ${planned_total:,.0f} in planned cost changes. "
        f"But there are also {drift_count} drifted resources that need attention."
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">{pr_label} Cost Impact</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${planned_total:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Planned infrastructure change by {pr_author}</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0;display:flex;align-items:center;gap:8px">Drift Alert
                <span style="background:#F5F1E8;color:#1E3A8A;padding:2px 8px;border-radius:4px;font-size:10px">ACTION REQUIRED</span>
            </p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${drift_total:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">{drift_count} unmanaged resources</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("")

    # What Happens Next card
    st.markdown(
        f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
        <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0 0 8px 0">What Happens Next</p>
        <p style="font-size:13px;color:#1E3A8A;line-height:1.6;margin:0">
            Jake will import the {drift_count} drifted resources into Terraform state, bringing them under IaC management.
            Next month, these resources will show up as "planned" instead of "drift" — and the close process will be
            even faster. The ${drift_total:,.0f} in drift spend becomes ${drift_total:,.0f} in managed spend, and Sarah's
            close packet shrinks from a question to a confirmation.
        </p>
        </div>""",
        unsafe_allow_html=True,
    )
