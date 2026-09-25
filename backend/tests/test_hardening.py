import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.ratelimit import SlidingWindowLimiter

_BASE = dict(
    database_url="sqlite://",
    plaid_client_id="a",
    plaid_secret="b",
    jwt_secret="x" * 40,
    airflow_sync_secret="a-real-shared-secret",
    cors_origins="https://app.example.com",
)


def test_limiter_blocks_after_limit_then_recovers(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("app.ratelimit.time.monotonic", lambda: now[0])
    limiter = SlidingWindowLimiter(window=60)
    assert [limiter.check("k", 3) for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.check("k", 3) == pytest.approx(60)
    assert limiter.check("other", 3) == 0.0  # keys are independent
    now[0] += 61
    assert limiter.check("k", 3) == 0.0


def test_login_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 3)
    form = {"username": "nobody@example.com", "password": "wrong-password"}
    assert [client.post("/auth/login", data=form).status_code for _ in range(3)] == [401] * 3
    blocked = client.post("/auth/login", data=form)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


def test_register_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 2)
    codes = [
        client.post("/auth/register", json={"email": f"u{i}@example.com", "password": "correct-horse"}).status_code
        for i in range(3)
    ]
    assert codes == [201, 201, 429]


def test_rate_limit_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_rate_limit_per_minute", 0)
    form = {"username": "nobody@example.com", "password": "wrong-password"}
    assert all(client.post("/auth/login", data=form).status_code == 401 for _ in range(30))


def test_production_config_with_real_secrets_is_accepted():
    Settings(_env_file=None, plaid_env="production", **_BASE)


@pytest.mark.parametrize(
    "override, message",
    [
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"jwt_secret": "change_this_to_a_random_secret_key"}, "JWT_SECRET"),
        ({"airflow_sync_secret": "airflowsecret"}, "AIRFLOW_SYNC_SECRET"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
    ],
)
def test_production_config_rejects_placeholders(override, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, plaid_env="production", **{**_BASE, **override})


def test_sandbox_allows_dev_defaults():
    Settings(_env_file=None, plaid_env="sandbox", **{**_BASE, "jwt_secret": "dev", "cors_origins": "*"})
