"""
Airflow DAG: sync_transactions
Runs daily at 2 AM UTC — calls backend /plaid/sync-all to refresh
all users' transactions and re-run subscription detection.
"""

import os
from datetime import datetime, timedelta

import requests
from airflow import DAG
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
    url = f"{API_URL}/plaid/sync-all"
    headers = {"x-airflow-secret": AIRFLOW_SECRET}

    response = requests.post(url, headers=headers, timeout=300)
    response.raise_for_status()

    result = response.json()
    print(f"Sync complete: {result}")
    return result


def log_run_summary(**context):
    ti = context["task_instance"]
    result = ti.xcom_pull(task_ids="sync_all_users")
    items_synced = result.get("items_synced", 0) if result else 0
    print(f"[DLA] Daily sync complete — {items_synced} Plaid items refreshed.")


with DAG(
    dag_id="sync_transactions",
    description="Daily Plaid transaction sync + subscription detection for all users",
    schedule_interval="0 2 * * *",  # 2 AM UTC daily
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
