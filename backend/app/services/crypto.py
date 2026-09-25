"""Encryption at rest for Plaid access tokens."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    material = settings.token_encryption_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _PREFIX + _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    """Decrypt a stored value. Legacy plaintext values are returned unchanged."""
    if not value.startswith(_PREFIX):
        return value
    try:
        return _fernet().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored token cannot be decrypted with the current key") from exc
