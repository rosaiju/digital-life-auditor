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
