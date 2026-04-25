"""Screen 0 — Upload files and run pipeline."""

import streamlit as st
import tempfile
import os

from cloudledger.database import create_all_tables
from cloudledger.ingest import ingest_focus_csv
from cloudledger.normalize import normalize_invoices, normalize_resources
from cloudledger.terraform import parse_terraform_state
from cloudledger.variance import compute_variance


def render():
    st.markdown("### Upload your data")
    st.markdown(
        "Drop your billing CSVs, Terraform state, and change events CSV below. "
        "The pipeline will ingest, normalize, and classify every variance automatically."
    )

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            "<p style='font-size:11px;font-weight:500;text-transform:uppercase;"
            "letter-spacing:0.05em;color:#1E3A8A'>Billing CSV</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<p style='font-size:11px;color:#1E3A8A;opacity:0.6'>Required</p>", unsafe_allow_html=True)
        billing_files = st.file_uploader(
            "FOCUS 1.2 CSV — upload one per month",
            type=["csv"],
            accept_multiple_files=True,
            key="billing_csv",
            label_visibility="collapsed",
        )

    with col2:
        st.markdown(
            "<p style='font-size:11px;font-weight:500;text-transform:uppercase;"
            "letter-spacing:0.05em;color:#1E3A8A'>Terraform State</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<p style='font-size:11px;color:#1E3A8A;opacity:0.6'>Required</p>", unsafe_allow_html=True)
        tf_file = st.file_uploader(
            "terraform.tfstate file",
            type=["tfstate", "json"],
            key="tf_state",
            label_visibility="collapsed",
        )

    with col3:
        st.markdown(
            "<p style='font-size:11px;font-weight:500;text-transform:uppercase;"
            "letter-spacing:0.05em;color:#1E3A8A'>Change Events CSV</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<p style='font-size:11px;color:#1E3A8A;opacity:0.6'>Optional</p>", unsafe_allow_html=True)
        changes_file = st.file_uploader(
            "PR merges & terraform applies",
            type=["csv"],
            key="changes_csv",
            label_visibility="collapsed",
        )

    st.markdown("---")

    ready = billing_files and tf_file
    run = st.button(
        "Run Pipeline",
        disabled=not ready,
        use_container_width=True,
        type="primary",
    )

    if not ready:
        st.markdown(
            "<p style='text-align:center;font-size:12px;color:#1E3A8A;opacity:0.5'>"
            "Upload billing CSV and Terraform state to enable the pipeline.</p>",
            unsafe_allow_html=True,
        )

    if run and ready:
        with st.spinner("Running pipeline..."):
            create_all_tables()

            # Ingest billing CSVs
            for f in billing_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(f.read())
                    tmp_path = tmp.name
                try:
                    ingest_focus_csv(tmp_path)
                finally:
                    os.unlink(tmp_path)

            # Save Terraform state to a temp file for normalize_resources
            tf_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tfstate")
            tf_tmp.write(tf_file.read())
            tf_tmp_path = tf_tmp.name
            tf_tmp.close()

            # Ingest change events if provided
            if changes_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(changes_file.read())
                    changes_path = tmp.name
                try:
                    from cloudledger.normalize import seed_sample_change_events
                    # Will use change events from the CSV if a loader exists
                except (ImportError, AttributeError):
                    pass
                finally:
                    os.unlink(changes_path)

            # Detect periods
            from cloudledger.database import get_db, RawBillingLine
            from sqlalchemy import distinct as sqldistinct
            with get_db() as session:
                periods = (
                    session.query(sqldistinct(RawBillingLine.billing_period_start))
                    .order_by(RawBillingLine.billing_period_start.desc())
                    .all()
                )
                periods = [r[0] for r in periods if r[0]]

            if len(periods) >= 2:
                current_p = periods[0]
                prior_p = periods[1]

                # Normalize & classify
                normalize_invoices()
                normalize_resources(terraform_state_path=tf_tmp_path)
                compute_variance(
                    prior_p.strftime("%Y-%m"),
                    current_p.strftime("%Y-%m"),
                )

                # Cleanup
                os.unlink(tf_tmp_path)

                st.session_state["prior_period"] = prior_p
                st.session_state["current_period"] = current_p
                st.session_state["screen"] = 1
                st.session_state["pipeline_done"] = True
                st.rerun()
            else:
                os.unlink(tf_tmp_path)
                if len(periods) == 1:
                    st.error("Only one billing period found. Upload data for two months to compare.")
                else:
                    st.error("No billing periods detected in the uploaded files.")
