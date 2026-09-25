"""Verify that a webhook really came from Plaid.

Plaid signs every webhook: the `Plaid-Verification` header is an ES256 JWT whose
`request_body_sha256` claim is the SHA-256 of the raw request body. The signing key is
fetched (and cached) by key id. See https://plaid.com/docs/api/webhooks/webhook-verification/
"""
import hashlib
import hmac
import time

from jose import JWTError, jwt

from app.services import plaid_service

MAX_AGE_SECONDS = 5 * 60

_key_cache: dict[str, dict] = {}


class WebhookVerificationError(Exception):
    pass


def _get_key(key_id: str) -> dict:
    key = _key_cache.get(key_id)
    if key is None:
        key = plaid_service.get_webhook_verification_key(key_id)
        _key_cache[key_id] = key
    return key


def verify(body: bytes, token: str | None) -> None:
    """Raise WebhookVerificationError unless `token` is a fresh, valid signature for `body`."""
    if not token:
        raise WebhookVerificationError("missing Plaid-Verification header")
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise WebhookVerificationError("malformed token") from exc
    if header.get("alg") != "ES256" or not header.get("kid"):
        raise WebhookVerificationError("unexpected token header")

    key = _get_key(header["kid"])
    if key.get("expired_at") is not None:
        raise WebhookVerificationError("signing key expired")

    try:
        claims = jwt.decode(token, key, algorithms=["ES256"], options={"verify_aud": False, "verify_exp": False})
    except JWTError as exc:
        raise WebhookVerificationError("bad signature") from exc

    if time.time() - float(claims.get("iat", 0)) > MAX_AGE_SECONDS:
        raise WebhookVerificationError("token too old")
    expected = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(str(claims.get("request_body_sha256", "")), expected):
        raise WebhookVerificationError("body does not match signature")
