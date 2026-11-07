"""密码哈希、JWT、随机凭证与服务端对称加密。"""

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import settings
from .errors import unauthorized

_hasher = PasswordHasher()

# ============================================================
# 账号凭证（authKey 由客户端从主密码派生，服务端只存它的 Argon2 哈希）
# ============================================================


def hash_auth_key(auth_key: str) -> str:
    return _hasher.hash(auth_key)


def verify_auth_key(auth_key: str, stored_hash: str) -> bool:
    try:
        return _hasher.verify(stored_hash, auth_key)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# 用于「用户不存在」时也做一次等价耗时的校验，避免时序侧信道暴露账号是否存在
DUMMY_AUTH_HASH = _hasher.hash("dummy-auth-key-for-timing-equalization")


def burn_time() -> None:
    verify_auth_key("dummy-auth-key-for-timing-equalization", DUMMY_AUTH_HASH)


# ============================================================
# JWT
# ============================================================

ACCESS = "access"
TWO_FA = "2fa"
RESET = "reset"


def _encode(user_id: str, token_type: str, minutes: int, **extra: Any) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": secrets.token_urlsafe(8),
        **extra,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(
    user_id: str, credential_version: int = 0, session_id: str | None = None
) -> tuple[str, int]:
    minutes = settings.access_token_minutes
    return _encode(user_id, ACCESS, minutes, ver=credential_version, sid=session_id), minutes * 60


def create_two_factor_challenge(
    user_id: str, credential_version: int = 0, two_factor_version: int = 0
) -> tuple[str, int]:
    minutes = 5
    return _encode(user_id, TWO_FA, minutes, ver=credential_version, tfv=two_factor_version), minutes * 60


def create_reset_token(
    user_id: str, credential_version: int = 0, two_factor_version: int = 0
) -> tuple[str, int]:
    minutes = 10
    return _encode(user_id, RESET, minutes, ver=credential_version, tfv=two_factor_version), minutes * 60


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"],
            options={"require": ["sub", "type", "iat", "exp", "jti", "ver"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("凭证已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized("凭证无效") from exc

    if payload.get("type") != expected_type:
        raise unauthorized("凭证类型不匹配")
    if (not isinstance(payload.get("sub"), str) or not payload["sub"]
            or not isinstance(payload.get("jti"), str) or not payload["jti"]
            or type(payload.get("ver")) is not int or payload["ver"] < 0):
        raise unauthorized("凭证无效")
    return payload


# ============================================================
# 随机凭证
# ============================================================

# 去掉易混淆字符（0/O/1/I）
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hmac_hex(value: str, purpose: str) -> str:
    """用 SERVER_SECRET 做带用途域的 HMAC，避免不同场景哈希互相复用。"""
    key = settings.server_secret.encode("utf-8")
    return hmac.new(key, f"{purpose}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_recovery_codes(count: int = 10) -> list[str]:
    """生成一次性恢复码，形如 ABCD-EFGH。"""
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def new_numeric_code(digits: int = 6) -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(digits))


# ============================================================
# 服务端对称加密（TOTP secret / SMTP 授权码）
# 这两类数据服务端必须可读，因此用 SERVER_SECRET 派生密钥加密
# ============================================================


def _server_key() -> bytes:
    return hashlib.sha256(settings.server_secret.encode("utf-8")).digest()


def encrypt_server(value: str) -> tuple[str, str]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_server_key()).encrypt(nonce, value.encode("utf-8"), None)
    return (
        base64.b64encode(ciphertext).decode("ascii"),
        base64.b64encode(nonce).decode("ascii"),
    )


def decrypt_server(ciphertext_b64: str, nonce_b64: str) -> str:
    plaintext = AESGCM(_server_key()).decrypt(
        base64.b64decode(nonce_b64),
        base64.b64decode(ciphertext_b64),
        None,
    )
    return plaintext.decode("utf-8")
