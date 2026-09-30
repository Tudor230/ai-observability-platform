"""Credential hashing and verification (only hashes are stored)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

SESSION_COOKIE = "aiobs_session"


def generate_api_key() -> str:
    return "aiobs_" + secrets.token_urlsafe(32)


def generate_password() -> str:
    return secrets.token_urlsafe(12)


def key_hint(key: str) -> str:
    """Trailing characters of a plaintext key, safe to display redacted."""
    return key[-4:]


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; truncate explicitly rather than fail.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], password_hash.encode("utf-8")
        )
    except ValueError:
        return False


def create_session_token(user_id: str, token_version: int, secret: str, ttl_s: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_s),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_session_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()