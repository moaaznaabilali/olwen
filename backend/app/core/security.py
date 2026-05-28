"""Password hashing, JWT, OTP, and secret-encryption helpers."""
import base64
import datetime as dt
import functools
import hashlib
import hmac
import secrets
import uuid
from typing import Any

import jwt
from cryptography.fernet import Fernet
from pwdlib import PasswordHash

from app.core.config import settings

# Argon2 (recommended) password hashing.
_password_hash = PasswordHash.recommended()


@functools.lru_cache(maxsize=1)
def _fernet() -> Fernet:
    # Prefer a dedicated encryption key; fall back to JWT_SECRET so existing
    # encrypted rows remain readable. Rotating ENCRYPTION_KEY would need a
    # re-encryption migration over the stored ciphertexts.
    src = settings.encryption_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(src.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    """Encrypt a sensitive value (e.g. a user's API key) for storage at rest."""
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask_secret(plain: str) -> str:
    """e.g. 'sk-ant-…aB12' — safe to show in the UI."""
    if len(plain) <= 8:
        return "••••"
    return f"{plain[:6]}…{plain[-4:]}"


def generate_otp() -> str:
    """A 6-digit numeric one-time code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    """Keyed hash so we never store the raw OTP. Fast (codes are short-lived)."""
    return hmac.new(
        settings.jwt_secret.encode(), code.encode(), hashlib.sha256
    ).hexdigest()


def verify_otp(code: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_otp(code), hashed)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _password_hash.verify(password, hashed)


def _create_token(subject: Any, token_type: str, expires: dt.timedelta) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(subject),
        "type": token_type,
        "iat": now,
        "exp": now + expires,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: Any) -> str:
    return _create_token(
        subject, "access", dt.timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(subject: Any) -> str:
    return _create_token(
        subject, "refresh", dt.timedelta(days=settings.refresh_token_expire_days)
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
