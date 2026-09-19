"""Password hashing and session-token helpers.

Deliberately uses only Python's standard library (hashlib, secrets) rather
than bcrypt/passlib/argon2, which ship as compiled packages -- given the
Rust-build issues hit installing pydantic-core, adding another native
dependency here wasn't worth the risk. PBKDF2-HMAC-SHA256 with a per-user
random salt is a reasonable, standard choice for a project at this scope.
"""
from __future__ import annotations

import hashlib
import secrets

PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> tuple[str, str]:
    """Returns (password_hash_hex, salt_hex)."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return secrets.compare_digest(digest.hex(), password_hash)


def new_session_token() -> str:
    return secrets.token_hex(32)