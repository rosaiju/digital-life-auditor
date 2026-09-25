"""The DAG file needs Airflow to import; stub the few names it uses so its logic can be tested."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

DAG_PATH = Path(__file__).resolve().parents[2] / "airflow" / "dags" / "sync_transactions_dag.py"


class AirflowFailException(Exception):
    pass


@pytest.fixture()
def dag_module(monkeypatch):
    class Recorder:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class Operator(Recorder):
        def __rshift__(self, other):
            return other

    stubs = {
        "airflow": types.ModuleType("airflow"),
        "airflow.exceptions": types.ModuleType("airflow.exceptions"),
        "airflow.operators": types.ModuleType("airflow.operators"),
        "airflow.operators.python": types.ModuleType("airflow.operators.python"),
    }
    stubs["airflow"].DAG = Recorder
    stubs["airflow.exceptions"].AirflowFailException = AirflowFailException
    stubs["airflow.operators.python"].PythonOperator = Operator
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location("sync_transactions_dag", DAG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTI:
    def __init__(self, value):
        self.value = value

    def xcom_pull(self, task_ids):
        assert task_ids == "sync_all_users"
        return self.value


def test_sync_task_calls_backend_with_secret(dag_module, monkeypatch):
    seen = {}

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "ok", "items_synced": 3, "items_failed": []}

    def fake_post(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return Response()

    monkeypatch.setattr(dag_module.requests, "post", fake_post)
    assert dag_module.sync_all_users()["items_synced"] == 3
    assert seen["url"].endswith("/plaid/sync-all")
    assert seen["headers"] == {"x-airflow-secret": dag_module.AIRFLOW_SECRET}


def test_summary_passes_when_everything_synced(dag_module):
    dag_module.log_run_summary(task_instance=FakeTI({"items_synced": 2, "items_failed": []}))


def test_summary_fails_run_when_any_item_failed(dag_module):
    with pytest.raises(AirflowFailException, match="7"):
        dag_module.log_run_summary(task_instance=FakeTI({"items_synced": 1, "items_failed": [7]}))
