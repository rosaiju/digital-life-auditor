"""Subscription lifecycle (ended/resumed), per-bank health, reconnect flow and concurrent syncs."""
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from app.models.connection import PlaidItem
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services import plaid_service, sync
from app.services.money import lapse_grace_days
from app.services.plaid_service import PlaidError
from tests.test_plaid_sync import connect, fake_plaid, monthly_history, plaid_txn  # noqa: F401
from tests.test_subscriptions_api import add_sub


def names(client, headers, status="active"):
    return sorted(s["merchant_name"] for s in client.get(f"/subscriptions?status={status}", headers=headers).json())


# ---------- lapsed / resumed subscriptions ----------

def test_grace_period_scales_with_frequency():
    assert lapse_grace_days("weekly") == 7
    assert lapse_grace_days("monthly") == 8
    assert lapse_grace_days("annual") == 91


def test_is_lapsed_boundary():
    today = date(2026, 9, 25)
    due = today - timedelta(days=8)
    assert not sync.is_lapsed(due, "monthly", today)                     # exactly at the grace limit
    assert sync.is_lapsed(due - timedelta(days=1), "monthly", today)
    assert not sync.is_lapsed(None, "monthly", today)


def test_cancelled_subscription_is_ended_not_active(client, register, fake_plaid):
    long_ago = date.today() - timedelta(days=100)
    fake_plaid.sync_result["added"] = (
        monthly_history("Netflix", 15.49) + monthly_history("Peloton", 44.0, end=long_ago)
    )
    headers, _ = register()

    body = connect(client, headers).json()

    assert body["subscriptions_found"] == 1                  # only Netflix is still being charged
    assert names(client, headers) == ["netflix"]
    assert names(client, headers, "ended") == ["peloton"]
    assert names(client, headers, "all") == ["netflix", "peloton"]


def test_subscription_becomes_active_again_when_charges_resume(client, register, fake_plaid):
    # Three monthly charges, the last 60 days ago: overdue by a month, so it reads as ended.
    fake_plaid.sync_result["added"] = monthly_history("Peloton", 44.0, months=3, end=date.today() - timedelta(days=60))
    headers, _ = register()
    connect(client, headers)
    assert names(client, headers) == []
    assert names(client, headers, "ended") == ["peloton"]

    # The bank reports the delayed charge on the next sync: it is billing normally after all.
    fake_plaid.sync_result = {
        "added": [plaid_txn("peloton-late", "Peloton", 44.0, date.today() - timedelta(days=28))],
        "modified": [], "removed": [], "cursor": "cursor-2",
    }
    client.post("/plaid/sync", headers=headers)

    assert names(client, headers) == ["peloton"]
    assert names(client, headers, "ended") == []


def test_listing_expires_subscriptions_whose_charges_stopped(client, register, db_session):
    headers, user_id = register()
    stale = add_sub(db_session, user_id, "gym")
    stale.next_charge_date = date.today() - timedelta(days=60)
    add_sub(db_session, user_id, "netflix")
    db_session.commit()

    assert names(client, headers) == ["netflix"]
    assert names(client, headers, "ended") == ["gym"]


def test_dismissed_stays_dismissed_even_when_lapsed(client, register, db_session):
    headers, user_id = register()
    sub = add_sub(db_session, user_id, "gym", status="dismissed")
    sub.next_charge_date = date.today() - timedelta(days=60)
    db_session.commit()

    client.get("/subscriptions", headers=headers)

    assert names(client, headers, "dismissed") == ["gym"]


def test_subscription_with_vanished_evidence_is_ended(client, register, fake_plaid, db_session):
    history = monthly_history("Netflix", 15.49)
    fake_plaid.sync_result["added"] = history
    headers, _ = register()
    connect(client, headers)
    assert names(client, headers) == ["netflix"]

    fake_plaid.sync_result = {
        "added": [], "modified": [], "removed": [t["transaction_id"] for t in history], "cursor": "cursor-2",
    }
    client.post("/plaid/sync", headers=headers)

    assert names(client, headers) == []
    assert names(client, headers, "ended") == ["netflix"]


# ---------- per-bank health ----------

def test_login_required_is_recorded_and_cleared_on_next_success(client, register, fake_plaid, db_session):
    headers, _ = register()
    connect(client, headers)

    fake_plaid.sync_error = PlaidError("the login details changed", "ITEM_LOGIN_REQUIRED")
    assert client.post("/plaid/sync", headers=headers).status_code == 502
    [item] = client.get("/plaid/items", headers=headers).json()
    assert item["status"] == "login_required"
    assert "login details" in item["last_error"]

    fake_plaid.sync_error = None
    assert client.post("/plaid/sync", headers=headers).status_code == 200
    [item] = client.get("/plaid/items", headers=headers).json()
    assert item["status"] == "ok"
    assert item["last_error"] is None
    assert item["last_synced_at"] is not None


def test_other_plaid_errors_mark_the_item_as_error(client, register, fake_plaid):
    headers, _ = register()
    connect(client, headers)
    fake_plaid.sync_error = PlaidError("bank is down", "INSTITUTION_DOWN")
    client.post("/plaid/sync", headers=headers)
    assert client.get("/plaid/items", headers=headers).json()[0]["status"] == "error"


def test_one_failing_bank_does_not_block_the_others(client, register, fake_plaid, db_session, monkeypatch):
    headers, _ = register()
    connect(client, headers, token="pub-a", institution="Chase")
    connect(client, headers, token="pub-b", institution="Ally")
    real_sync = plaid_service.sync_transactions

    def flaky(access_token, cursor=None):
        flaky.calls += 1
        if flaky.calls == 1:
            raise PlaidError("Chase is down", "INSTITUTION_DOWN")
        return real_sync(access_token, cursor)

    flaky.calls = 0
    monkeypatch.setattr(plaid_service, "sync_transactions", flaky)

    body = client.post("/plaid/sync", headers=headers).json()

    assert body["status"] == "partial"
    assert body["accounts"] == 2
    assert [f["institution_name"] for f in body["failed"]] == ["Chase"]
    statuses = {i["institution_name"]: i["status"] for i in client.get("/plaid/items", headers=headers).json()}
    assert statuses == {"Chase": "error", "Ally": "ok"}


def test_successful_sync_records_last_synced_time(client, register, fake_plaid):
    headers, _ = register()
    connect(client, headers)
    assert client.get("/plaid/items", headers=headers).json()[0]["last_synced_at"] is not None


# ---------- reconnect (Link update mode) ----------

def test_reconnect_link_token_is_created_in_update_mode(client, register, fake_plaid, monkeypatch):
    headers, user_id = register()
    connect(client, headers)
    [item] = client.get("/plaid/items", headers=headers).json()
    calls = []
    monkeypatch.setattr(
        plaid_service, "create_link_token", lambda uid, access_token=None: calls.append((uid, access_token)) or "link-update"
    )

    response = client.post(f"/plaid/items/{item['id']}/link-token", headers=headers)

    assert response.json() == {"link_token": "link-update"}
    assert calls == [(user_id, "access-sandbox-secret")]


def test_reconnect_link_token_rejects_someone_elses_item(client, register, fake_plaid):
    alice, _ = register("alice@example.com")
    bob, _ = register("bob@example.com")
    connect(client, alice)
    [item] = client.get("/plaid/items", headers=alice).json()
    assert client.post(f"/plaid/items/{item['id']}/link-token", headers=bob).status_code == 404
    assert client.post(f"/plaid/items/{item['id']}/reconnected", headers=bob).status_code == 404


def test_reconnected_syncs_and_clears_the_error(client, register, fake_plaid):
    headers, _ = register()
    connect(client, headers)
    fake_plaid.sync_error = PlaidError("login", "ITEM_LOGIN_REQUIRED")
    client.post("/plaid/sync", headers=headers)
    fake_plaid.sync_error = None

    response = client.post(f"/plaid/items/{client.get('/plaid/items', headers=headers).json()[0]['id']}/reconnected", headers=headers)

    assert response.status_code == 200
    assert client.get("/plaid/items", headers=headers).json()[0]["status"] == "ok"


def test_update_mode_link_request_has_no_products_and_carries_access_token(monkeypatch):
    sent = []

    class FakeClient:
        def link_token_create(self, request):
            sent.append(request.to_dict())
            return {"link_token": "link-x"}

    monkeypatch.setattr(plaid_service, "get_client", lambda: FakeClient())
    monkeypatch.setattr(plaid_service.settings, "plaid_webhook_url", "")

    plaid_service.create_link_token(1)
    plaid_service.create_link_token(1, access_token="access-sandbox-abc")

    assert sent[0]["products"] == ["transactions"] and "access_token" not in sent[0]
    assert "products" not in sent[1] and sent[1]["access_token"] == "access-sandbox-abc"


def test_link_request_includes_webhook_only_when_configured(monkeypatch):
    sent = []

    class FakeClient:
        def link_token_create(self, request):
            sent.append(request.to_dict())
            return {"link_token": "link-x"}

    monkeypatch.setattr(plaid_service, "get_client", lambda: FakeClient())
    monkeypatch.setattr(plaid_service.settings, "plaid_webhook_url", "")
    plaid_service.create_link_token(1)
    monkeypatch.setattr(plaid_service.settings, "plaid_webhook_url", "https://api.example.com/plaid/webhook")
    plaid_service.create_link_token(1)

    assert "webhook" not in sent[0]
    assert sent[1]["webhook"] == "https://api.example.com/plaid/webhook"


# ---------- concurrent syncs ----------

def test_sync_retries_once_when_a_concurrent_sync_wins_the_race(client, register, fake_plaid, db_session, monkeypatch):
    fake_plaid.sync_result["added"] = monthly_history("Netflix", 15.49)
    headers, _ = register()
    connect(client, headers)

    real_apply = sync.apply_changes
    attempts = []

    def racing_apply(db, *args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise IntegrityError("INSERT", {}, Exception("duplicate plaid_transaction_id"))
        return real_apply(db, *args, **kwargs)

    monkeypatch.setattr(sync, "apply_changes", racing_apply)
    item = db_session.query(PlaidItem).one()

    stats = sync.sync_item(db_session, item)

    assert len(attempts) == 2
    assert stats.subscriptions == 1
    assert db_session.query(Transaction).count() == 4
    assert db_session.query(Subscription).count() == 1
