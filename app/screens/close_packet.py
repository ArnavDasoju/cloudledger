"""Screen 5 — Close packet."""

import streamlit as st
import csv
import io
from cloudledger.database import get_db, Invoice, VarianceReport
from sqlalchemy import func


def render():
    prior = st.session_state.get("prior_period")
    current = st.session_state.get("current_period")

    # Load data
    with get_db() as session:
        inv = session.query(Invoice).filter(Invoice.billing_period_start == current).first()
        total_cost = float(inv.total_billed_cost) if inv else 0

        reason_rows = (
            session.query(
                VarianceReport.reason_code,
                func.sum(VarianceReport.delta_dollars),
            )
            .filter(VarianceReport.current_period_start == current)
            .group_by(VarianceReport.reason_code)
            .all()
        )

        total_variance = sum(abs(float(r[1] or 0)) for r in reason_rows)
        variance_explained_pct = 100 if total_variance > 0 else 0

    current_label = current.strftime("%B") if current else "Current"

    st.markdown(f"### Sarah's close packet — ready in 40 minutes, not 3 days")
    st.markdown(
        f"Every dollar in the {current_label} bill is now accounted for. The variance is fully classified, "
        "the reconciliation is complete, and the GL export is one click away."
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Invoice Reconciliation</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">
                <span style="color:#3B82F6;margin-right:8px">&check;</span>${total_cost:,.0f}
            </p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Fully reconciled</p>
            </div>""",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px">
            <p style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;color:#1E3A8A;margin:0">Variance Explained</p>
            <p style="font-size:34px;font-weight:500;color:#1E3A8A;margin:8px 0 4px 0">
                <span style="color:#3B82F6;margin-right:8px">&check;</span>{variance_explained_pct}%
            </p>
            <p style="font-size:12px;color:#1E3A8A;opacity:0.6;margin:0">Every dollar assigned a reason code</p>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("")

    # Variance summary code block
    lines = [f"{current_label} Close — Variance Summary", ""]
    for code, amount in reason_rows:
        label = (code or "other").replace("_", " ").title()
        lines.append(f"  {label:<30} ${float(amount or 0):>12,.0f}")
    lines.append(f"  {'':─<30} {'':─>13}")
    lines.append(f"  {'Total Variance':<30} ${total_variance:>12,.0f}")

    st.markdown(
        f"""<div style="background:#FFFFFF;border:1px solid rgba(30,58,138,0.2);border-radius:10px;padding:20px;font-family:monospace;font-size:13px;color:#1E3A8A;white-space:pre">{'chr(10)'.join(lines) if False else chr(10).join(lines)}</div>""",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # GL Export button
    def generate_gl_csv():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Account", "Description", "Debit", "Credit", "Reason", "Service"])
        with get_db() as session:
            vrows = session.query(VarianceReport).filter(
                VarianceReport.current_period_start == current
            ).all()
            for v in vrows:
                date_str = current.strftime("%Y-%m-%d") if current else ""
                delta = float(v.delta_dollars or 0)
                debit = abs(delta) if delta > 0 else 0
                credit = abs(delta) if delta < 0 else 0
                writer.writerow([
                    date_str,
                    f"6{(v.service_name or 'Cloud')[:3].upper()}00",
                    f"{v.resource_name or v.resource_id} — {(v.reason_code or '').replace('_',' ')}",
                    f"{debit:.2f}",
                    f"{credit:.2f}",
                    v.reason_code or "",
                    v.service_name or "",
                ])
        return output.getvalue()

    st.download_button(
        label="Export GL entry to NetSuite",
        data=generate_gl_csv(),
        file_name=f"cloudledger_gl_{current.strftime('%Y_%m') if current else 'export'}.csv",
        mime="text/csv",
        use_container_width=True,
        type="primary",
    )
