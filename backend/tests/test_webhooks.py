"""Plaid webhook verification and handling. Signatures are produced with a locally generated
ES256 key; the only thing faked is Plaid's key-lookup endpoint."""
import base64
import hashlib
import json
import time
from contextlib import contextmanager

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from jose import jwt

from app.models.connection import PlaidItem
from app.routers import plaid as plaid_router
from app.services import plaid_service, plaid_webhooks
from app.services.plaid_service import PlaidError
from tests.test_plaid_sync import connect, fake_plaid, monthly_history  # noqa: F401

KID = "test-key-1"


def _b64(n: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(32, "big")).rstrip(b"=").decode()


class Signer:
    def __init__(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        numbers = self.private.public_key().public_numbers()
        self.jwk = {"kty": "EC", "crv": "P-256", "kid": KID, "alg": "ES256", "use": "sig",
                    "x": _b64(numbers.x), "y": _b64(numbers.y), "created_at": 1, "expired_at": None}
        self.pem = self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

    def token(self, body: bytes, iat=None, kid=KID):
        claims = {"iat": int(iat if iat is not None else time.time()), "request_body_sha256": hashlib.sha256(body).hexdigest()}
        return jwt.encode(claims, self.pem, algorithm="ES256", headers={"kid": kid})


@pytest.fixture()
def signer(monkeypatch):
    signer = Signer()
    plaid_webhooks._key_cache.clear()
    monkeypatch.setattr(plaid_service, "get_webhook_verification_key", lambda kid: dict(signer.jwk))
    return signer


@pytest.fixture()
def in_test_session(db_session, monkeypatch):
    """Background tasks open their own session; point them at the test database."""

    @contextmanager
    def scope():
        yield db_session

    monkeypatch.setattr(plaid_router, "session_scope", scope)


def post(client, signer, payload, token=None, body=None, **token_kwargs):
    body = body if body is not None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    token = token if token is not None else signer.token(body, **token_kwargs)
    if token:
        headers["Plaid-Verification"] = token
    return client.post("/plaid/webhook", content=body, headers=headers)


def connected_item(client, register, fake_plaid, db_session):
    fake_plaid.sync_result["added"] = monthly_history("Netflix", 15.49)
    headers, _ = register()
    connect(client, headers)
    return headers, db_session.query(PlaidItem).one()


# ---------- signature checks ----------

def test_missing_signature_is_rejected(client, signer):
    assert post(client, signer, {"webhook_type": "TRANSACTIONS"}, token="").status_code == 401


def test_garbage_signature_is_rejected(client, signer):
    assert post(client, signer, {"webhook_type": "TRANSACTIONS"}, token="not-a-jwt").status_code == 401


def test_signature_from_another_key_is_rejected(client, signer):
    forged = Signer().token(b'{"webhook_type": "TRANSACTIONS"}')
    assert post(client, signer, {"webhook_type": "TRANSACTIONS"}, token=forged).status_code == 401


def test_tampered_body_is_rejected(client, signer):
    token = signer.token(b'{"item_id": "a"}')
    assert post(client, signer, None, token=token, body=b'{"item_id": "b"}').status_code == 401


def test_old_signature_is_rejected(client, signer):
    response = post(client, signer, {"webhook_type": "TRANSACTIONS"}, iat=time.time() - 600)
    assert response.status_code == 401


def test_hs256_token_is_rejected(client, signer):
    body = b"{}"
    weak = jwt.encode({"iat": int(time.time()), "request_body_sha256": hashlib.sha256(body).hexdigest()},
                      "secret", algorithm="HS256", headers={"kid": KID})
    assert post(client, signer, None, token=weak, body=body).status_code == 401


def test_expired_key_is_rejected(client, signer, monkeypatch):
    monkeypatch.setattr(plaid_service, "get_webhook_verification_key", lambda kid: {**signer.jwk, "expired_at": 5})
    assert post(client, signer, {"webhook_type": "TRANSACTIONS"}).status_code == 401


def test_key_lookup_failure_is_a_503_not_a_pass(client, signer, monkeypatch):
    def boom(kid):
        raise PlaidError("plaid unreachable")

    monkeypatch.setattr(plaid_service, "get_webhook_verification_key", boom)
    assert post(client, signer, {"webhook_type": "TRANSACTIONS"}).status_code == 503


def test_verification_keys_are_cached(client, signer, monkeypatch):
    calls = []
    monkeypatch.setattr(plaid_service, "get_webhook_verification_key", lambda kid: calls.append(kid) or dict(signer.jwk))
    plaid_webhooks._key_cache.clear()
    for _ in range(3):
        post(client, signer, {"webhook_type": "X", "item_id": "nope"})
    assert calls == [KID]


# ---------- handling ----------

def test_transactions_webhook_triggers_a_sync(client, register, fake_plaid, db_session, signer, in_test_session):
    headers, item = connected_item(client, register, fake_plaid, db_session)
    fake_plaid.cursors_seen.clear()
    fake_plaid.sync_result = {
        "added": [], "modified": [], "removed": [], "cursor": "cursor-from-webhook",
    }

    response = post(client, signer, {
        "webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": item.item_id,
    })

    assert response.status_code == 200 and response.json() == {"status": "accepted"}
    assert fake_plaid.cursors_seen == ["cursor-1"]
    db_session.refresh(item)
    assert item.cursor == "cursor-from-webhook"


def test_login_required_webhook_flags_the_item(client, register, fake_plaid, db_session, signer, in_test_session):
    headers, item = connected_item(client, register, fake_plaid, db_session)

    response = post(client, signer, {
        "webhook_type": "ITEM", "webhook_code": "ERROR", "item_id": item.item_id,
        "error": {"error_code": "ITEM_LOGIN_REQUIRED"},
    })

    assert response.json() == {"status": "accepted"}
    [listed] = client.get("/plaid/items", headers=headers).json()
    assert listed["status"] == "login_required"
    assert "sign in again" in listed["last_error"]


def test_pending_expiration_webhook_flags_the_item(client, register, fake_plaid, db_session, signer, in_test_session):
    headers, item = connected_item(client, register, fake_plaid, db_session)
    post(client, signer, {"webhook_type": "ITEM", "webhook_code": "PENDING_EXPIRATION", "item_id": item.item_id})
    assert client.get("/plaid/items", headers=headers).json()[0]["last_error"] == "Bank access expires soon"


def test_unknown_item_and_unknown_events_are_acknowledged_and_ignored(client, register, fake_plaid, db_session, signer, in_test_session):
    headers, item = connected_item(client, register, fake_plaid, db_session)
    fake_plaid.cursors_seen.clear()

    unknown_item = post(client, signer, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": "item-nobody"})
    other_event = post(client, signer, {"webhook_type": "HOLDINGS", "webhook_code": "DEFAULT_UPDATE", "item_id": item.item_id})
    no_item = post(client, signer, {"webhook_type": "TRANSACTIONS"})

    assert unknown_item.status_code == other_event.status_code == no_item.status_code == 200
    assert other_event.json() == no_item.json() == {"status": "ignored"}
    assert fake_plaid.cursors_seen == []          # nothing synced for the unknown item or event


def test_failing_background_sync_does_not_break_the_webhook(client, register, fake_plaid, db_session, signer, in_test_session):
    headers, item = connected_item(client, register, fake_plaid, db_session)
    fake_plaid.sync_error = PlaidError("bank down", "INSTITUTION_DOWN")

    response = post(client, signer, {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": item.item_id})

    assert response.status_code == 200
    assert client.get("/plaid/items", headers=headers).json()[0]["status"] == "error"


def test_malformed_but_correctly_signed_body_is_a_400(client, signer):
    assert post(client, signer, None, body=b"not json").status_code == 400
