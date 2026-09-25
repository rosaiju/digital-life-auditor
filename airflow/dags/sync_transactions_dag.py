"""
Airflow DAG: sync_transactions
Runs daily at 2 AM UTC. It calls the backend's /plaid/sync-all endpoint, which
pulls new transactions for every connected bank and re-runs subscription
detection. The run fails (and shows red in the Airflow UI) if any connection
failed to sync, so problems are visible instead of silently swallowed.
"""

import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator

API_URL = os.getenv("DLA_API_URL", "http://backend:8000")
AIRFLOW_SECRET = os.getenv("DLA_AIRFLOW_SECRET", "airflowsecret")

default_args = {
    "owner": "airflow",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def sync_all_users(**context):
    response = requests.post(
        f"{API_URL}/plaid/sync-all",
        headers={"x-airflow-secret": AIRFLOW_SECRET},
        timeout=300,
    )
    response.raise_for_status()
    result = response.json()
    print(f"Sync complete: {result}")
    return result


def log_run_summary(**context):
    result = context["task_instance"].xcom_pull(task_ids="sync_all_users") or {}
    synced = result.get("items_synced", 0)
    failed = result.get("items_failed", [])
    print(f"[DLA] Daily sync: {synced} Plaid items refreshed, {len(failed)} failed.")
    if failed:
        raise AirflowFailException(f"Sync failed for Plaid item ids: {failed}")


with DAG(
    dag_id="sync_transactions",
    description="Daily Plaid transaction sync + subscription detection for all users",
    schedule="0 2 * * *",  # 2 AM UTC daily
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["digital-life-auditor", "plaid", "subscriptions"],
) as dag:

    sync_task = PythonOperator(
        task_id="sync_all_users",
        python_callable=sync_all_users,
    )

    summary_task = PythonOperator(
        task_id="log_run_summary",
        python_callable=log_run_summary,
    )

    sync_task >> summary_task
