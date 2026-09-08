"""API-key hashing and verification (only hashes are stored)."""
from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    return "aiobs_" + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key(key: str, key_hash: str | None) -> bool:
    if not key_hash:
        return False
    candidate = hash_api_key(key)
    return hmac.compare_digest(candidate, key_hash)