"""Plaid routes and the sync pipeline, with the Plaid API itself mocked."""
from datetime import date, timedelta

import pytest

from app.models.connection import PlaidItem
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.services import plaid_service
from app.services.plaid_service import PlaidError


def plaid_txn(txn_id, merchant, amount, day, pending=False):
    return {
        "transaction_id": txn_id,
        "merchant_name": merchant,
        "name": merchant,
        "amount": amount,
        "date": day.isoformat(),
        "pending": pending,
        "personal_finance_category": {"primary": "ENTERTAINMENT"},
    }


def monthly_history(merchant, amount, months=4, prefix=None, end=None):
    """Monthly charges ending a few days ago, so the subscription is still current."""
    end = end or date.today() - timedelta(days=3)
    start = end - timedelta(days=30 * (months - 1))
    prefix = prefix or merchant.lower()
    return [plaid_txn(f"{prefix}-{i}", merchant, amount, start + timedelta(days=30 * i)) for i in range(months)]


@pytest.fixture()
def fake_plaid(monkeypatch):
    """Patch the Plaid service with a scripted, inspectable fake."""

    class Fake:
        sync_result = {"added": [], "modified": [], "removed": [], "cursor": "cursor-1"}
        sync_error = None
        exchange_error = None
        cursors_seen = []
        removed_tokens = []

    def create_link_token(user_id, access_token=None):
        return f"link-sandbox-{user_id}"

    def exchange(public_token):
        if Fake.exchange_error:
            raise Fake.exchange_error
        return {"access_token": "access-sandbox-secret", "item_id": f"item-{public_token}"}

    def sync(access_token, cursor=None):
        Fake.cursors_seen.append(cursor)
        if Fake.sync_error:
            raise Fake.sync_error
        return Fake.sync_result

    monkeypatch.setattr(plaid_service, "create_link_token", create_link_token)
    monkeypatch.setattr(plaid_service, "exchange_public_token", exchange)
    monkeypatch.setattr(plaid_service, "sync_transactions", sync)
    monkeypatch.setattr(plaid_service, "remove_item", lambda token: Fake.removed_tokens.append(token))
    Fake.cursors_seen = []
    Fake.removed_tokens = []
    Fake.sync_error = Fake.exchange_error = None
    Fake.sync_result = {"added": [], "modified": [], "removed": [], "cursor": "cursor-1"}
    return Fake


def connect(client, headers, token="pub-1", institution="Chase"):
    return client.post("/plaid/exchange", json={"public_token": token, "institution_name": institution}, headers=headers)


# ---------- link token / exchange ----------

def test_link_token_requires_auth(client):
    assert client.post("/plaid/link-token").status_code == 401


def test_link_token(client, register, fake_plaid):
    headers, user_id = register()
    assert client.post("/plaid/link-token", headers=headers).json() == {"link_token": f"link-sandbox-{user_id}"}


def test_exchange_stores_item_syncs_and_detects_subscriptions(client, register, fake_plaid, db_session):
    fake_plaid.sync_result["added"] = monthly_history("Netflix", 15.49) + monthly_history("Spotify", 10.99)
    headers, _ = register()

    response = connect(client, headers)

    assert response.status_code == 200
    body = response.json()
    assert body["synced"] is True
    assert body["transactions_added"] == 8
    assert body["subscriptions_found"] == 2
    names = {s["merchant_name"] for s in client.get("/subscriptions", headers=headers).json()}
    assert names == {"netflix", "spotify"}
    assert db_session.query(Transaction).count() == 8
    assert db_session.query(PlaidItem).one().cursor == "cursor-1"


def test_access_token_is_encrypted_at_rest(client, register, fake_plaid, db_session):
    headers, _ = register()
    connect(client, headers)
    raw = db_session.connection().exec_driver_sql("SELECT access_token FROM plaid_items").scalar()
    assert "access-sandbox-secret" not in raw
    assert raw.startswith("enc:v1:")
    assert db_session.query(PlaidItem).one().access_token == "access-sandbox-secret"  # decrypts transparently


def test_exchange_is_idempotent_for_same_item(client, register, fake_plaid, db_session):
    headers, _ = register()
    connect(client, headers)
    connect(client, headers)
    assert db_session.query(PlaidItem).count() == 1


def test_exchange_rejects_item_owned_by_another_user(client, register, fake_plaid):
    alice, _ = register("alice@example.com")
    bob, _ = register("bob@example.com")
    assert connect(client, alice).status_code == 200
    assert connect(client, bob).status_code == 409


def test_exchange_plaid_failure_is_a_502_and_stores_nothing(client, register, fake_plaid, db_session):
    fake_plaid.exchange_error = PlaidError("invalid public_token", "INVALID_PUBLIC_TOKEN")
    headers, _ = register()
    response = connect(client, headers)
    assert response.status_code == 502
    assert "invalid public_token" in response.json()["detail"]
    assert db_session.query(PlaidItem).count() == 0


def test_exchange_keeps_connection_when_first_sync_fails(client, register, fake_plaid, db_session):
    fake_plaid.sync_error = PlaidError("PRODUCT_NOT_READY", "PRODUCT_NOT_READY")
    headers, _ = register()
    response = connect(client, headers)
    assert response.status_code == 200
    assert response.json()["synced"] is False
    assert db_session.query(PlaidItem).count() == 1


# ---------- sync behaviour ----------

def test_sync_uses_saved_cursor_and_handles_modified_and_removed(client, register, fake_plaid, db_session):
    headers, _ = register()
    fake_plaid.sync_result["added"] = [
        plaid_txn("t1", "Coffee", 4.0, date(2026, 8, 1), pending=True),
        plaid_txn("t2", "Coffee", 4.0, date(2026, 8, 2)),
    ]
    connect(client, headers)
    assert fake_plaid.cursors_seen == [None]

    fake_plaid.sync_result = {
        "added": [plaid_txn("t3", "Book Store", 20.0, date(2026, 8, 5))],
        "modified": [plaid_txn("t2", "Coffee", 4.5, date(2026, 8, 2))],
        "removed": ["t1"],
        "cursor": "cursor-2",
    }
    response = client.post("/plaid/sync", headers=headers)

    assert response.status_code == 200
    assert fake_plaid.cursors_seen[-1] == "cursor-1"
    ids = {t.plaid_transaction_id: t for t in db_session.query(Transaction).all()}
    assert set(ids) == {"t2", "t3"}                    # t1 removed
    assert ids["t2"].amount == 4.5                     # t2 updated
    assert db_session.query(PlaidItem).one().cursor == "cursor-2"


def test_cursor_not_advanced_when_sync_fails(client, register, fake_plaid, db_session):
    headers, _ = register()
    connect(client, headers)
    fake_plaid.sync_error = PlaidError("boom")
    assert client.post("/plaid/sync", headers=headers).status_code == 502
    assert db_session.query(PlaidItem).one().cursor == "cursor-1"


def test_sync_without_connected_accounts_is_404(client, auth_headers):
    assert client.post("/plaid/sync", headers=auth_headers).status_code == 404


def test_dismissed_subscription_stays_dismissed_after_resync(client, register, fake_plaid, db_session):
    fake_plaid.sync_result["added"] = monthly_history("Netflix", 15.49)
    headers, _ = register()
    connect(client, headers)
    sub_id = client.get("/subscriptions", headers=headers).json()[0]["id"]
    client.patch(f"/subscriptions/{sub_id}/dismiss", headers=headers)

    fake_plaid.sync_result = {"added": [], "modified": [], "removed": [], "cursor": "cursor-2"}
    client.post("/plaid/sync", headers=headers)

    assert client.get("/subscriptions", headers=headers).json() == []
    assert db_session.query(Subscription).one().status == "dismissed"


def test_resync_updates_price_of_existing_subscription(client, register, fake_plaid, db_session):
    history = monthly_history("Netflix", 15.49, months=3, end=date.today() - timedelta(days=33))
    fake_plaid.sync_result["added"] = history
    headers, _ = register()
    connect(client, headers)

    later = date.today() - timedelta(days=3)  # the fourth monthly charge
    fake_plaid.sync_result = {
        "added": [plaid_txn("netflix-3", "Netflix", 15.99, later)],
        "modified": [], "removed": [], "cursor": "cursor-2",
    }
    client.post("/plaid/sync", headers=headers)

    [sub] = client.get("/subscriptions", headers=headers).json()
    assert sub["amount"] == 15.99
    assert db_session.query(Subscription).count() == 1


# ---------- items ----------

def test_list_and_disconnect_items(client, register, fake_plaid, db_session):
    headers, _ = register()
    connect(client, headers)
    [item] = client.get("/plaid/items", headers=headers).json()
    assert item["institution_name"] == "Chase"
    assert "access_token" not in item

    assert client.delete(f"/plaid/items/{item['id']}", headers=headers).status_code == 204
    assert fake_plaid.removed_tokens == ["access-sandbox-secret"]
    assert client.get("/plaid/items", headers=headers).json() == []


def test_cannot_disconnect_someone_elses_item(client, register, fake_plaid):
    alice, _ = register("alice@example.com")
    bob, _ = register("bob@example.com")
    connect(client, alice)
    [item] = client.get("/plaid/items", headers=alice).json()
    assert client.delete(f"/plaid/items/{item['id']}", headers=bob).status_code == 404
    assert len(client.get("/plaid/items", headers=alice).json()) == 1


# ---------- Airflow endpoint ----------

def test_sync_all_requires_shared_secret(client, register, fake_plaid):
    assert client.post("/plaid/sync-all").status_code == 403
    assert client.post("/plaid/sync-all", headers={"x-airflow-secret": "wrong"}).status_code == 403


def test_sync_all_syncs_every_item_and_reports_failures(client, register, fake_plaid, db_session):
    alice, _ = register("alice@example.com")
    bob, _ = register("bob@example.com")
    connect(client, alice, token="pub-a")
    connect(client, bob, token="pub-b")
    good = {"x-airflow-secret": "test-airflow-secret"}

    ok = client.post("/plaid/sync-all", headers=good).json()
    assert ok == {"status": "ok", "items_synced": 2, "items_failed": []}

    fake_plaid.sync_error = PlaidError("bank down")
    partial = client.post("/plaid/sync-all", headers=good).json()
    assert partial["status"] == "partial"
    assert partial["items_synced"] == 0
    assert len(partial["items_failed"]) == 2


# ---------- link token options ----------

def test_link_token_request_includes_android_package_only_when_configured(monkeypatch):
    sent = []

    class FakeClient:
        def link_token_create(self, request):
            sent.append(request)
            return {"link_token": "link-sandbox-x"}

    monkeypatch.setattr(plaid_service, "get_client", lambda: FakeClient())

    monkeypatch.setattr(plaid_service.settings, "plaid_android_package_name", "")
    plaid_service.create_link_token(1)
    assert "android_package_name" not in sent[-1].to_dict()

    monkeypatch.setattr(plaid_service.settings, "plaid_android_package_name", "com.example.app")
    assert plaid_service.create_link_token(1) == "link-sandbox-x"
    assert sent[-1].to_dict()["android_package_name"] == "com.example.app"


# ---------- input validation ----------

def test_exchange_rejects_empty_or_oversized_input(client, register, fake_plaid, db_session):
    headers, _ = register()
    post = lambda body: client.post("/plaid/exchange", json=body, headers=headers).status_code
    assert post({"public_token": ""}) == 422
    assert post({"public_token": "x" * 513}) == 422
    assert post({"public_token": "pub", "institution_name": "y" * 201}) == 422
    assert post({}) == 422
    assert db_session.query(PlaidItem).count() == 0
