"""认证服务：密码哈希（pbkdf2）+ JWT 签发/校验。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from ..config import get_settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), iterations)
    return f"pbkdf2${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, hex_hash = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations)
        )
        return hmac.compare_digest(dk.hex(), hex_hash)
    except Exception:  # noqa: BLE001
        return False


def create_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "kind": "tenant",
        "iat": _now(),
        "exp": _now() + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_mp_token(openid: str) -> str:
    """求职端小程序 token（C 端，无企业租户）。"""
    settings = get_settings()
    payload = {
        "sub": openid,
        "kind": "mp",
        "iat": _now(),
        "exp": _now() + timedelta(days=settings.mp_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """校验并解析 token；无效/过期抛异常。"""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
