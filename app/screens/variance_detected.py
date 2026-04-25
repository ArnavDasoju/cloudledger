"""Screen 3 — Variance detected."""

import streamlit as st
from cloudledger.database import get_db, VarianceReport
from sqlalchemy import func
from decimal import Decimal


def render():
    current = st.session_state.get("current_period")

    # Load service breakdown
    with get_db() as session:
        rows = (
            session.query(
                VarianceReport.service_name,
                func.sum(func.abs(VarianceReport.delta_dollars)),
            )
            .filter(VarianceReport.current_period_start == current)
            .group_by(VarianceReport.service_name)
            .order_by(func.sum(func.abs(VarianceReport.delta_dollars)).desc())
            .all()
        )
        total_variance = sum(float(r[1] or 0) for r in rows)

    st.markdown(f"### Variance detected — ${total_variance:,.0f} unaccounted for")
    st.markdown(
        "The tool flags every service where spend changed between the two billing periods. "
        "The breakdown below shows where the variance concentrates — a starting point for root cause analysis."
    )

    st.markdown("---")

    # Show top 5 + Other as horizontal bars
    top_n = 5
    display_rows = []
    other_total = 0.0

    for i, (svc, amount) in enumerate(rows):
        if i < top_n:
            display_rows.append((svc or "Unknown", float(amount or 0)))
        else:
            other_total += float(amount or 0)
    if other_total > 0:
        display_rows.append(("Other", other_total))

    max_val = max((r[1] for r in display_rows), default=1)

    for svc, amount in display_rows:
        pct = (amount / max_val * 100) if max_val > 0 else 0
        st.markdown(
            f"""<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
            <div style="width:180px;font-size:13px;color:#1E3A8A;text-align:right;flex-shrink:0">{svc}</div>
            <div style="flex:1;background:rgba(30,58,138,0.08);border-radius:4px;height:24px;overflow:hidden">
                <div style="width:{pct:.0f}%;height:100%;background:#3B82F6;border-radius:4px"></div>
            </div>
            <div style="width:100px;font-size:13px;font-weight:500;color:#1E3A8A;flex-shrink:0">${amount:,.0f}</div>
            </div>""",
            unsafe_allow_html=True,
        )
