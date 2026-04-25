"""Screen 1 — Bill arrives."""

import streamlit as st
from cloudledger.database import get_db, Invoice


def render():
    prior = st.session_state.get("prior_period")
    current = st.session_state.get("current_period")

    # Load totals
    prior_total = 0
    current_total = 0
    with get_db() as session:
        for inv in session.query(Invoice).filter(Invoice.billing_period_start == prior).all():
            prior_total += float(inv.total_billed_cost or 0)
        for inv in session.query(Invoice).filter(Invoice.billing_period_start == current).all():
            current_total += float(inv.total_billed_cost or 0)

    prior_label = prior.strftime("%B") if prior else "Prior"
    current_label = current.strftime("%B") if current else "Current"
    delta = current_total - prior_total

    st.markdown(f"### April 2 — the {current_label} AWS bill arrives")
    st.markdown(
        f"Sarah, the cloud finance controller, opens the {current_label} bill. "
        f"It's ${current_total:,.0f} — up ${delta:,.0f} from {prior_label}'s ${prior_total:,.0f}. "
        f"She needs to understand where every dollar went before the books close."
    )

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">{prior_label} Bill</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${prior_total:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Baseline month</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">{current_label} Bill</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${current_total:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">+${delta:,.0f} from {prior_label}</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Sarah's Question</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">Why?</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Where did the extra ${delta:,.0f} go?</p>
            </div>""",
            unsafe_allow_html=True,
        )
