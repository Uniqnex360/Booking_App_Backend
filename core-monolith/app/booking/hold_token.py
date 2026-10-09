"""Guest hold-token helpers. Only the SHA-256 hash is ever stored."""
from __future__ import annotations

import hashlib
import hmac

MIN_TOKEN_LENGTH = 43  # ~32 bytes base64url


def hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def verify(plain: str, stored_hash: str | None) -> bool:
    if not plain or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(plain), stored_hash)


def sign_booking_token(booking_id) -> str:
    from app.core.config import settings
    secret = getattr(settings, "JWT_SECRET_KEY", "vyhbz_default_booking_secret")
    return hmac.new(
        secret.encode("utf-8"),
        f"booking_access:{booking_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_booking_token(booking_id, token: str | None) -> bool:
    if not token or not isinstance(token, str):
        return False
    expected = sign_booking_token(booking_id)
    return hmac.compare_digest(token.strip(), expected)