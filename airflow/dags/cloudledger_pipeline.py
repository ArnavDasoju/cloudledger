"""CloudLedger monthly close pipeline — orchestrated by Apache Airflow.

DAG: cloudledger_monthly_close
Schedule: 1st of each month at midnight UTC
Tasks:
  1. check_new_billing_files — scan Azure Blob for new FOCUS exports
  2. ingest_billing_data — load CSVs into raw_billing_lines
  3. normalize_data — aggregate invoices and enrich resources
  4. run_dbt_transformations — execute dbt run + dbt test
  5. compute_variance — month-over-month variance with reason codes
  6. run_quality_checks — fail the DAG if any check fails
"""

import os
from datetime import datetime, timedelta

from airflow import DAG

try:
    from airflow.providers.standard.operators.python import PythonOperator
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.python import PythonOperator
    from airflow.operators.bash import BashOperator

try:
    from airflow.sdk.exceptions import AirflowFailException
except ImportError:
    try:
        from airflow.exceptions import AirflowFailException
    except ImportError:
        AirflowFailException = RuntimeError


default_args = {
    "owner": "cloudledger",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    dag_id="cloudledger_monthly_close",
    default_args=default_args,
    description="Monthly cloud billing close: ingest → normalize → transform → variance → quality",
    schedule="0 0 1 * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["cloudledger", "finops", "billing"],
)


# ── Task 1: Check for new billing files in Azure Blob ─────────────────────

def _check_new_billing_files(**context):
    """Check Azure Blob Storage for new FOCUS CSV exports.

    Falls back to data/samples/ if Azure is not configured.
    """
    from cloudledger.azure_storage import list_billing_files
    from cloudledger.config import AZURE_STORAGE_CONN_STRING

    execution_date = context["execution_date"]
    prefix = execution_date.strftime("%Y/%m/")

    files = []
    if AZURE_STORAGE_CONN_STRING:
        files = list_billing_files(prefix=prefix)
        if not files:
            files = list_billing_files()

    # Fall back to local sample files if Azure not configured or no files found
    if not files:
        samples_dir = "data/samples"
        if os.path.exists(samples_dir):
            files = [
                os.path.join(samples_dir, f)
                for f in os.listdir(samples_dir)
                if f.endswith(".csv")
            ]
            print(f"Azure not configured — falling back to local samples: {files}")

    print(f"Found {len(files)} billing files: {files}")
    context["ti"].xcom_push(key="billing_files", value=files)
    return files


check_new_billing_files = PythonOperator(
    task_id="check_new_billing_files",
    python_callable=_check_new_billing_files,
    dag=dag,
)


# ── Task 2: Ingest billing data ──────────────────────────────────────────

def _ingest_billing_data(**context):
    """Download and ingest FOCUS CSV files into raw_billing_lines."""
    from cloudledger.database import create_all_tables
    from cloudledger.ingest import ingest_focus_csv
    from cloudledger.config import AZURE_STORAGE_CONN_STRING

    create_all_tables()

    files = context["ti"].xcom_pull(
        task_ids="check_new_billing_files", key="billing_files"
    ) or []

    total_stats = {"rows_read": 0, "rows_inserted": 0, "rows_skipped": 0, "errors": 0}

    for file_path in files:
        # If it's a blob name (not a local path), download first
        if not os.path.exists(file_path) and AZURE_STORAGE_CONN_STRING:
            from cloudledger.azure_storage import download_billing_file
            file_path = download_billing_file(file_path)

        stats = ingest_focus_csv(file_path)
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

    print(f"Ingestion complete: {total_stats}")
    return total_stats


ingest_billing_data = PythonOperator(
    task_id="ingest_billing_data",
    python_callable=_ingest_billing_data,
    dag=dag,
)


# ── Task 3: Normalize data ──────────────────────────────────────────────

def _normalize_data(**context):
    """Run invoice normalization and resource enrichment."""
    from cloudledger.normalize import normalize_invoices, normalize_resources

    normalize_invoices()
    normalize_resources("data/samples/terraform.tfstate")
    print("Normalization complete")


normalize_data = PythonOperator(
    task_id="normalize_data",
    python_callable=_normalize_data,
    dag=dag,
)


# ── Task 4: Run dbt transformations ──────────────────────────────────────

run_dbt_transformations = BashOperator(
    task_id="run_dbt_transformations",
    bash_command="cd ${DBT_PROFILES_DIR:-dbt_project} && dbt run --profiles-dir . && dbt test --profiles-dir .",
    dag=dag,
)


# ── Task 5: Compute variance ─────────────────────────────────────────────

def _compute_variance(**context):
    """Compute month-over-month variance with reason codes."""
    from cloudledger.variance import compute_variance

    execution_date = context["execution_date"]
    current_period = execution_date.strftime("%Y-%m")

    # Prior month
    prior_date = execution_date.replace(day=1) - timedelta(days=1)
    prior_period = prior_date.strftime("%Y-%m")

    result = compute_variance(prior_period, current_period)
    print(f"Variance: {result}")
    return result


compute_variance_task = PythonOperator(
    task_id="compute_variance",
    python_callable=_compute_variance,
    dag=dag,
)


# ── Task 6: Run quality checks ───────────────────────────────────────────

def _run_quality_checks(**context):
    """Run data quality checks — fails the DAG if any check fails."""
    from cloudledger.quality import run_quality_checks

    execution_date = context["execution_date"]
    period = execution_date.strftime("%Y-%m")

    results = run_quality_checks(period)
    failed = [r for r in results if r["status"] == "fail"]

    for r in results:
        icon = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}[r["status"]]
        print(f"  [{icon}] {r['check']}: {r['detail']}")

    if failed:
        raise AirflowFailException(
            f"{len(failed)} quality check(s) failed: "
            + ", ".join(r["check"] for r in failed)
        )

    print(f"All {len(results)} quality checks passed")
    return results


run_quality_checks_task = PythonOperator(
    task_id="run_quality_checks",
    python_callable=_run_quality_checks,
    dag=dag,
)


# ── Task dependencies (>> chaining) ──────────────────────────────────────

(
    check_new_billing_files
    >> ingest_billing_data
    >> normalize_data
    >> run_dbt_transformations
    >> compute_variance_task
    >> run_quality_checks_task
)
