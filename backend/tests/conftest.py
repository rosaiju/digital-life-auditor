import os

# Settings are read at import time, so configure the environment first.
# A throwaway SQLite URL keeps tests from ever touching a real database.
os.environ.update(
    DATABASE_URL="sqlite://",
    PLAID_CLIENT_ID="test-client",
    PLAID_SECRET="test-secret",
    PLAID_ENV="sandbox",
    JWT_SECRET="test-jwt-secret",
    GROQ_API_KEY="",
    AIRFLOW_SYNC_SECRET="test-airflow-secret",
    TOKEN_ENCRYPTION_KEY="test-encryption-key",
    CORS_ORIGINS="*",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app import models as _models  # noqa: E402,F401  (registers all tables on Base.metadata)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.ratelimit import auth_limiter

    auth_limiter.reset()
    yield


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def register(client):
    """Register a user and return (headers, user_id)."""

    def _register(email="user@example.com", password="correct-horse"):
        response = client.post("/auth/register", json={"email": email, "password": password})
        assert response.status_code == 201, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return headers, client.get("/auth/me", headers=headers).json()["id"]

    return _register


@pytest.fixture()
def auth_headers(register):
    return register()[0]
