from jose import jwt

from app.config import settings
from app.routers.auth import hash_password, verify_password


def test_register_returns_token_usable_on_me(client):
    response = client.post("/auth/register", json={"email": "a@example.com", "password": "password123"})
    assert response.status_code == 201
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"
    assert "hashed_password" not in me.json()


def test_register_normalizes_email_case_and_rejects_duplicates(client):
    assert client.post("/auth/register", json={"email": "Case@Example.com", "password": "password123"}).status_code == 201
    dup = client.post("/auth/register", json={"email": "case@example.com", "password": "password123"})
    assert dup.status_code == 400


def test_register_validates_input(client):
    assert client.post("/auth/register", json={"email": "not-an-email", "password": "password123"}).status_code == 422
    assert client.post("/auth/register", json={"email": "b@example.com", "password": "short"}).status_code == 422


def test_login_success_and_case_insensitive_email(client):
    client.post("/auth/register", json={"email": "c@example.com", "password": "password123"})
    response = client.post("/auth/login", data={"username": "C@Example.com", "password": "password123"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_login_wrong_password_and_unknown_user_look_identical(client):
    client.post("/auth/register", json={"email": "d@example.com", "password": "password123"})
    wrong = client.post("/auth/login", data={"username": "d@example.com", "password": "nope-nope-nope"})
    unknown = client.post("/auth/login", data={"username": "ghost@example.com", "password": "password123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_protected_routes_require_a_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/subscriptions").status_code == 401


def test_token_signed_with_another_secret_is_rejected(client):
    forged = jwt.encode({"sub": "1"}, "some-other-secret", algorithm=settings.jwt_algorithm)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_for_deleted_user_is_rejected(client):
    token = jwt.encode({"sub": "9999"}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_password_hashing_roundtrip():
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("other", hashed)
    assert not verify_password("anything", "not-a-bcrypt-hash")


def test_long_passwords_do_not_crash():
    assert verify_password("x" * 200, hash_password("x" * 200))


def test_health_checks_database(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---------- change password / delete account ----------

def test_change_password(client, register):
    headers, _ = register("cp@example.com", "old-password-1")
    ok = client.post("/auth/change-password", json={"current_password": "old-password-1", "new_password": "new-password-2"}, headers=headers)
    assert ok.status_code == 204
    assert client.post("/auth/login", data={"username": "cp@example.com", "password": "old-password-1"}).status_code == 401
    assert client.post("/auth/login", data={"username": "cp@example.com", "password": "new-password-2"}).status_code == 200


def test_change_password_checks_current_password_and_new_password_rules(client, register):
    headers, _ = register("cp2@example.com", "old-password-1")
    change = lambda cur, new: client.post("/auth/change-password", json={"current_password": cur, "new_password": new}, headers=headers).status_code
    assert change("wrong-password", "new-password-2") == 403
    assert change("old-password-1", "short") == 422
    assert change("old-password-1", "old-password-1") == 400
    assert client.post("/auth/change-password", json={"current_password": "x", "new_password": "new-password-2"}).status_code == 401


def test_delete_account_requires_the_right_password(client, register):
    headers, _ = register("del@example.com", "right-password")
    assert client.post("/auth/delete-account", json={"password": "wrong"}, headers=headers).status_code == 403
    assert client.get("/auth/me", headers=headers).status_code == 200      # still there
    assert client.post("/auth/delete-account", json={"password": "right-password"}).status_code == 401


def test_delete_account_removes_everything_and_revokes_bank_access(client, register, db_session, monkeypatch):
    from app.models.connection import PlaidItem
    from app.models.insight import Insight
    from app.models.subscription import Subscription
    from app.models.transaction import Transaction
    from app.models.user import User
    from app.services import plaid_service
    from tests.test_plaid_sync import monthly_history

    revoked = []
    monkeypatch.setattr(plaid_service, "create_link_token", lambda *a, **k: "x")
    monkeypatch.setattr(plaid_service, "exchange_public_token", lambda t: {"access_token": "access-1", "item_id": "item-1"})
    monkeypatch.setattr(plaid_service, "sync_transactions", lambda tok, cur=None: {
        "added": monthly_history("Netflix", 15.49), "modified": [], "removed": [], "cursor": "c"})
    monkeypatch.setattr(plaid_service, "remove_item", lambda tok: revoked.append(tok))
    headers, _ = register("gone@example.com", "right-password")
    other, _ = register("stays@example.com", "right-password")
    client.post("/plaid/exchange", json={"public_token": "p"}, headers=headers)
    client.post("/insights/generate", headers=headers)
    assert db_session.query(Transaction).count() == 4

    assert client.post("/auth/delete-account", json={"password": "right-password"}, headers=headers).status_code == 204

    assert revoked == ["access-1"]
    for model in (PlaidItem, Transaction, Subscription, Insight):
        assert db_session.query(model).count() == 0, model
    assert [u.email for u in db_session.query(User)] == ["stays@example.com"]
    assert client.get("/auth/me", headers=headers).status_code == 401       # the old token is dead
    assert client.get("/auth/me", headers=other).status_code == 200
    assert client.post("/auth/login", data={"username": "gone@example.com", "password": "right-password"}).status_code == 401


def test_delete_account_succeeds_even_if_plaid_revocation_fails(client, register, db_session, monkeypatch):
    from app.models.connection import PlaidItem
    from app.models.user import User
    from app.services import plaid_service
    from app.services.plaid_service import PlaidError

    headers, user_id = register("gone2@example.com", "right-password")
    db_session.add(PlaidItem(user_id=user_id, access_token="access-2", item_id="item-2"))
    db_session.commit()

    def fail(token):
        raise PlaidError("plaid down")

    monkeypatch.setattr(plaid_service, "remove_item", fail)
    assert client.post("/auth/delete-account", json={"password": "right-password"}, headers=headers).status_code == 204
    assert db_session.query(User).count() == 0
    assert db_session.query(PlaidItem).count() == 0
