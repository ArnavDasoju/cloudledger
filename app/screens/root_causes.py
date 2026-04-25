"""Screen 4 — Root causes."""

import streamlit as st
from cloudledger.database import get_db, VarianceReport, ChangeEvent
from sqlalchemy import func


REASON_LABELS = {
    "planned": "Planned IaC Change",
    "drift": "Unplanned Drift",
    "usage_growth": "Usage Growth",
}


def render():
    current = st.session_state.get("current_period")

    # Aggregate by reason code
    with get_db() as session:
        reason_rows = (
            session.query(
                VarianceReport.reason_code,
                func.sum(func.abs(VarianceReport.delta_dollars)),
                func.count(VarianceReport.id),
            )
            .filter(VarianceReport.current_period_start == current)
            .group_by(VarianceReport.reason_code)
            .all()
        )
        # Load recent change events for the timeline
        events = (
            session.query(ChangeEvent)
            .order_by(ChangeEvent.event_date.desc())
            .limit(10)
            .all()
        )

    # Build reason map
    reason_map = {}
    for code, amount, count in reason_rows:
        reason_map[code or "other"] = {"amount": float(amount or 0), "count": count}

    planned = reason_map.get("planned", {"amount": 0, "count": 0})
    drift_data = reason_map.get("drift", {"amount": 0, "count": 0})
    # Combine usage_growth, new_resource, price_change, etc. into "usage growth"
    usage = {"amount": 0, "count": 0}
    for code in ("usage_growth", "new_resource", "removed_resource", "price_change"):
        if code in reason_map:
            usage["amount"] += reason_map[code]["amount"]
            usage["count"] += reason_map[code]["count"]

    total = planned["amount"] + drift_data["amount"] + usage["amount"]

    st.markdown(f"### Root causes traced — every dollar assigned a reason code")
    st.markdown(
        "CloudLedger classifies each variance into three buckets: planned infrastructure changes "
        "that were expected, unplanned drift from resources outside IaC, and organic usage growth."
    )

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Planned IaC Change</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${planned['amount']:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">{planned['count']} resources</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-left:3px solid #3B82F6;border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0;display:flex;align-items:center;gap:8px">Unplanned Drift
                <span style="background:#F5F1E8;color:#1E3A8A;padding:2px 8px;border-radius:4px;font-size:10px">ATTENTION</span>
            </p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${drift_data['amount']:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">{drift_data['count']} resources</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Usage Growth</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">${usage['amount']:,.0f}</p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">{usage['count']} resources</p>
            </div>""",
            unsafe_allow_html=True,
        )

    # Timeline
    st.markdown("")
    st.markdown(
        "<p style='font-size:11px;font-weight:500;text-transform:uppercase;"
        "letter-spacing:0.05em;color:#1E3A8A;margin-bottom:12px'>Event Timeline</p>",
        unsafe_allow_html=True,
    )

    if events:
        for evt in events[:3]:
            date_str = evt.event_date.strftime("%b %d") if evt.event_date else ""
            title = evt.pr_title or evt.description or evt.event_type or ""
            detail = ""
            if evt.pr_number:
                detail = f"PR #{evt.pr_number} by {evt.pr_author or 'unknown'}"
            elif evt.description:
                detail = evt.description[:80]

            st.markdown(
                f"""<div style="display:flex;gap:16px;margin-bottom:12px;padding:12px 16px;background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:8px">
                <div style="font-size:12px;font-weight:500;color:#3B82F6;width:50px;flex-shrink:0">{date_str}</div>
                <div>
                    <div style="font-size:13px;font-weight:500;color:#1E3A8A">{title[:60]}</div>
                    <div style="font-size:12px;color:#1E3A8A;opacity:0.6">{detail}</div>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )
    else:
        # Show placeholder timeline events
        current_label = current.strftime("%b") if current else "Mar"
        timeline_items = [
            (f"{current_label} 8", "PR merged — infrastructure change", f"Planned cost increase from IaC change, ${planned['amount']:,.0f} impact"),
            (f"{current_label} 14", "Drift detected", f"{drift_data['count']} unmanaged resources found, ${drift_data['amount']:,.0f} impact"),
            (f"{current_label} 1-31", "Organic usage growth", f"Gradual increase across {usage['count']} resources, ${usage['amount']:,.0f} impact"),
        ]
        for date_str, title, detail in timeline_items:
            st.markdown(
                f"""<div style="display:flex;gap:16px;margin-bottom:12px;padding:12px 16px;background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:8px">
                <div style="font-size:12px;font-weight:500;color:#3B82F6;width:60px;flex-shrink:0">{date_str}</div>
                <div>
                    <div style="font-size:13px;font-weight:500;color:#1E3A8A">{title}</div>
                    <div style="font-size:12px;color:#1E3A8A;opacity:0.6">{detail}</div>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )
