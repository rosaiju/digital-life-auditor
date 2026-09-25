import pytest

from app.config import Settings
from app.services import crypto


def test_roundtrip_and_ciphertext_differs():
    token = crypto.encrypt("access-production-123")
    assert token.startswith("enc:v1:")
    assert "access-production-123" not in token
    assert crypto.decrypt(token) == "access-production-123"


def test_encryption_is_randomized():
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_legacy_plaintext_values_still_readable():
    assert crypto.decrypt("access-sandbox-legacy") == "access-sandbox-legacy"


def test_wrong_key_fails_loudly(monkeypatch):
    token = crypto.encrypt("secret")
    monkeypatch.setattr(crypto.settings, "token_encryption_key", "a-different-key")
    with pytest.raises(ValueError):
        crypto.decrypt(token)


def test_key_falls_back_to_jwt_secret(monkeypatch):
    monkeypatch.setattr(crypto.settings, "token_encryption_key", "")
    assert crypto.decrypt(crypto.encrypt("x")) == "x"


def test_settings_validate_plaid_env_and_cors():
    base = dict(database_url="sqlite://", plaid_client_id="a", plaid_secret="b", jwt_secret="c")
    with pytest.raises(ValueError):
        Settings(**base, plaid_env="staging")
    hardened = dict(base, jwt_secret="x" * 40, airflow_sync_secret="a-real-shared-secret", cors_origins="https://a.com")
    assert Settings(**hardened, plaid_env="PRODUCTION").plaid_env == "production"
    assert Settings(**base, cors_origins="http://a.com, http://b.com").cors_origin_list == ["http://a.com", "http://b.com"]
