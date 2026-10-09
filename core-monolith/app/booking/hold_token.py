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