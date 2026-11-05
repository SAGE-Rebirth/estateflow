import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from cryptography.fernet import Fernet

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _secret(token_type: str) -> str:
    s = get_settings()
    return s.jwt_refresh_secret if token_type == "refresh" else s.jwt_secret


def _encode(claims: dict[str, Any], ttl: timedelta) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, _secret(claims["typ"]), algorithm=s.jwt_algorithm)


def create_access_token(user_id: str, tenant_id: str, role: str, version: int = 0) -> str:
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "tid": str(tenant_id), "role": role, "ver": version, "typ": "access"},
        timedelta(minutes=s.access_token_minutes),
    )


def create_refresh_token(user_id: str, tenant_id: str, version: int = 0) -> str:
    """`version` must match users.token_version; bumping it signs the user out everywhere."""
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "tid": str(tenant_id), "ver": version, "typ": "refresh"},
        timedelta(days=s.refresh_token_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    s = get_settings()
    payload = jwt.decode(token, _secret(expected_type), algorithms=[s.jwt_algorithm])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
