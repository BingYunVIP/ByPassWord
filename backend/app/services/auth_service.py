"""认证业务逻辑：注册、登录、刷新、2FA、找回密码。

服务端全程不接触主密码与 DEK 明文，只做「认证 + 存取密文」。
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyotp
from sqlalchemy import case, delete, exists, func, literal, or_, select, update
from sqlalchemy.exc import IntegrityError
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.errors import ApiError, bad_request, conflict, forbidden, locked, unauthorized
from ..core.ownership import get_owner_user_id
from ..core.security import (
    RESET,
    TWO_FA,
    burn_time,
    create_access_token,
    create_reset_token,
    create_two_factor_challenge,
    decode_token,
    decrypt_server,
    encrypt_server,
    hash_auth_key,
    hmac_hex,
    new_numeric_code,
    new_recovery_codes,
    new_refresh_token,
    sha256_hex,
    verify_auth_key,
)
from ..models import AuthChallenge, AuditLog, InstallationOwner, PasswordReset, RefreshToken, TotpRecoveryCode, User
from ..models.base import utcnow
from ..schemas.auth import (
    ChangePasswordRequest,
    KdfParams,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RecoveryConfigurationRequest,
)
from . import mailer, secrets

logger = logging.getLogger("bypw.auth")


def _now_text() -> str:
    """邮件模板里的 {time} 占位符。"""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


async def _notify_login_failed(session, user, ip: str, ua: str) -> None:
    """连续登录失败：10 分钟内累计 >=3 次时通知一次，发完清空窗口避免刷屏。"""
    try:
        now = datetime.now(UTC)
        raw = await secrets.get_secret(session, user.id, "login_fail_window")
        window = json.loads(raw) if raw else []
        if not isinstance(window, list):
            window = []
        cutoff = now.timestamp() - 600
        window = [t for t in window if isinstance(t, (int, float)) and t >= cutoff]
        window.append(now.timestamp())
        await secrets.set_secret(session, user.id, "login_fail_window", json.dumps(window))

        if len(window) >= 3:
            await mailer.notify(
                session,
                user,
                "login_failed_burst",
                {"ip": ip, "ua": ua or "未知设备", "time": _now_text()},
            )
            await secrets.set_secret(session, user.id, "login_fail_window", "[]")
    except Exception:  # noqa: BLE001
        logger.warning("连续登录失败通知异常", exc_info=True)


async def _notify_login(
    session, user, ip: str, ua: str, prev_ip: str | None, recovery: bool = False
) -> None:
    """登录类安全事件：恢复码登录 / IP 变化 / 新设备。失败不影响登录。"""
    ctx = {"ip": ip, "ua": ua or "未知设备", "time": _now_text()}
    try:
        if recovery:
            await mailer.notify(session, user, "login_recovery_code", ctx)
            return
        if prev_ip and prev_ip != ip:
            await mailer.notify(session, user, "login_ip_changed", ctx)

        fingerprint = hashlib.sha256((ua or "unknown").encode("utf-8")).hexdigest()[:16]
        raw = await secrets.get_secret(session, user.id, "known_devices")
        devices = json.loads(raw) if raw else []
        if not isinstance(devices, list):
            devices = []
        # 首次登录不报新设备，避免注册即告警
        if prev_ip and fingerprint not in devices:
            await mailer.notify(session, user, "login_new_device", ctx)
        devices = (devices + [fingerprint])[-10:]
        await secrets.set_secret(session, user.id, "known_devices", json.dumps(devices))
    except Exception:  # noqa: BLE001
        logger.warning("登录安全通知失败", exc_info=True)

MAX_FAILED_ATTEMPTS = 10
LOCK_MINUTES = 15
RESET_CODE_MINUTES = 10
RESET_CODE_MAX_ATTEMPTS = 5
CHALLENGE_MAX_ATTEMPTS = 5


@dataclass
class AuthResult:
    access_token: str | None = None
    expires_in: int = 0
    wrapped_dek: str | None = None
    dek_nonce: str | None = None
    refresh_token: str | None = None
    requires_2fa: bool = False
    challenge: str | None = None


async def write_audit(session, user_id, action, ip=None, ua=None, target=None, meta=None) -> None:
    session.add(AuditLog(user_id=user_id, action=action, ip=ip, user_agent=ua, target=target, meta=meta))
    await session.commit()


async def _issue_tokens(session, user, ip, ua, session_id=None) -> tuple[str, int, str]:
    sid = session_id or str(uuid4())
    refresh = new_refresh_token()
    session.add(RefreshToken(
        user_id=user.id, token_hash=sha256_hex(refresh), session_id=sid,
        credential_version=user.credential_version,
        expires_at=utcnow() + timedelta(days=settings.refresh_token_days), ip=ip, user_agent=ua,
    ))
    await session.flush()
    token, seconds = create_access_token(user.id, user.credential_version, sid)
    await session.commit()
    return token, seconds, refresh


def _full_result(user, access_token, expires_in, refresh_token) -> AuthResult:
    return AuthResult(access_token=access_token, expires_in=expires_in,
                      wrapped_dek=user.wrapped_dek, dek_nonce=user.dek_nonce,
                      refresh_token=refresh_token)


def _version_matches(user, payload) -> bool:
    return (payload.get("ver") == user.credential_version
            and payload.get("tfv") == user.two_factor_version)


async def _new_challenge(session, user, purpose) -> tuple[str, int]:
    creator = create_two_factor_challenge if purpose == TWO_FA else create_reset_token
    token, seconds = creator(user.id, user.credential_version, user.two_factor_version)
    data = decode_token(token, purpose)
    session.add(AuthChallenge(
        id=data["jti"], user_id=user.id, purpose=purpose,
        credential_version=user.credential_version, two_factor_version=user.two_factor_version,
        expires_at=datetime.fromtimestamp(data["exp"], UTC),
    ))
    # Only expired challenges are removed; live consumption state stays auditable.
    await session.execute(delete(AuthChallenge).where(AuthChallenge.user_id == user.id,
                                                     AuthChallenge.expires_at <= utcnow()))
    return token, seconds


def _challenge_filters(payload, purpose):
    return (
        AuthChallenge.id == payload["jti"], AuthChallenge.user_id == payload["sub"],
        AuthChallenge.purpose == purpose, AuthChallenge.consumed_at.is_(None),
        AuthChallenge.attempts < CHALLENGE_MAX_ATTEMPTS, AuthChallenge.expires_at > utcnow(),
        AuthChallenge.credential_version == payload["ver"],
        AuthChallenge.two_factor_version == payload["tfv"],
        exists(select(User.id).where(User.id == payload["sub"],
                                    User.credential_version == payload["ver"],
                                    User.two_factor_version == payload["tfv"])),
    )


async def _challenge_user(session, token, purpose):
    payload = decode_token(token, purpose)
    if type(payload.get("tfv")) is not int:
        raise unauthorized("验证凭证已失效，请重新开始")
    user = await session.get(User, payload["sub"])
    if user is None or not _version_matches(user, payload):
        raise unauthorized("验证凭证已失效，请重新开始")
    found = await session.scalar(select(AuthChallenge.id).where(*_challenge_filters(payload, purpose)))
    if found is None:
        raise unauthorized("验证凭证已使用、过期或尝试次数过多")
    return user, payload


async def _consume_challenge(session, payload, purpose) -> None:
    result = await session.execute(update(AuthChallenge).where(*_challenge_filters(payload, purpose))
                                   .values(consumed_at=utcnow()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("验证凭证已使用、过期或尝试次数过多")


async def _fail_challenge(session, payload, purpose, message="验证码错误", code="invalid_code") -> None:
    await session.execute(update(AuthChallenge).where(*_challenge_filters(payload, purpose)).values(
        attempts=AuthChallenge.attempts + 1,
        consumed_at=case((AuthChallenge.attempts >= CHALLENGE_MAX_ATTEMPTS - 1,
                          literal(utcnow(), type_=AuthChallenge.consumed_at.type)), else_=None),
    ).execution_options(synchronize_session=False))
    await session.commit()
    raise unauthorized(message, code)


async def _revoke_all_sessions(session, user_id) -> None:
    await session.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                                    RefreshToken.revoked_at.is_(None))
                          .values(revoked_at=utcnow()).execution_options(synchronize_session=False))
    await _invalidate_challenges(session, user_id)


async def _invalidate_challenges(session, user_id) -> None:
    await session.execute(update(AuthChallenge).where(AuthChallenge.user_id == user_id,
                                                     AuthChallenge.consumed_at.is_(None))
                          .values(consumed_at=utcnow()).execution_options(synchronize_session=False))
    await session.execute(update(PasswordReset).where(PasswordReset.user_id == user_id,
                                                     PasswordReset.used_at.is_(None))
                          .values(used_at=utcnow()).execution_options(synchronize_session=False))


async def _revoke_other_sessions(session, user_id, session_id) -> None:
    filters = [RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)]
    if session_id:
        filters.append(or_(RefreshToken.session_id != session_id, RefreshToken.session_id.is_(None)))
    await session.execute(update(RefreshToken).where(*filters).values(revoked_at=utcnow())
                          .execution_options(synchronize_session=False))
    await _invalidate_challenges(session, user_id)


async def registration_status(session) -> dict:
    initialized = await get_owner_user_id(session) is not None
    return {"initialized": initialized,
            "allowed": not initialized or settings.allow_registration_after_first}


async def prelogin(session: AsyncSession, email: str) -> dict:
    email = email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        # Stable per-email pseudorandom salt avoids the repeat-request existence oracle.
        import base64
        salt = base64.b64encode(bytes.fromhex(hmac_hex(email, "prelogin-salt"))[:16]).decode("ascii")
        return {"kdf": {"algo": "argon2id", "salt": salt, "memoryKib": 65536, "time": 3, "parallel": 1}}
    return {"kdf": {"algo": user.kdf_algo, "salt": user.kdf_salt,
                    "memoryKib": user.kdf_memory_kib, "time": user.kdf_time, "parallel": user.kdf_parallel}}


async def register(session: AsyncSession, payload: RegisterRequest, ip: str, ua: str) -> AuthResult:
    email = payload.email.lower()
    owner = await get_owner_user_id(session)
    if owner is not None and not settings.allow_registration_after_first:
        raise forbidden("此个人密码库已完成初始化，不再开放注册")
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise conflict("email_exists", "该邮箱已注册")
    user = User(email=email, auth_hash=hash_auth_key(payload.authHash),
                credential_version=0, two_factor_version=0,
                kdf_algo=payload.kdf.algo, kdf_salt=payload.kdf.salt,
                kdf_memory_kib=payload.kdf.memoryKib, kdf_time=payload.kdf.time,
                kdf_parallel=payload.kdf.parallel, wrapped_dek=payload.wrappedDek,
                dek_nonce=payload.dekNonce, recovery_wrapped_dek=payload.recoveryWrappedDek,
                recovery_dek_nonce=payload.recoveryDekNonce,
                recovery_auth_hash=hash_auth_key(payload.recoveryAuthHash) if payload.recoveryAuthHash else None,
                last_login_at=utcnow(), last_login_ip=ip)
    session.add(user)
    try:
        await session.flush()
        if owner is None:
            session.add(InstallationOwner(id=1, owner_user_id=user.id))
            await session.flush()  # Singleton claim and account creation are one transaction.
        result = await _issue_tokens(session, user, ip, ua)
    except IntegrityError:
        await session.rollback()
        raise conflict("registration_conflict", "密码库已初始化或邮箱已注册，请重新登录")
    await write_audit(session, user.id, "register", ip, ua)
    return _full_result(user, *result)


async def login(session: AsyncSession, payload: LoginRequest, ip: str, ua: str) -> AuthResult:
    user = await session.scalar(select(User).where(User.email == payload.email.lower()))
    now = utcnow()
    if user is None:
        burn_time()
        await write_audit(session, None, "login_failed", ip, ua, meta="unknown_email")
        raise unauthorized("邮箱或主密码错误", "invalid_credentials")
    if user.locked_until is not None and user.locked_until > now:
        raise locked(f"尝试次数过多，请于 {user.locked_until:%H:%M} 后重试")
    if not verify_auth_key(payload.authHash, user.auth_hash):
        await session.execute(update(User).where(User.id == user.id,
                                                 User.credential_version == user.credential_version,
                                                 or_(User.locked_until.is_(None), User.locked_until <= now)).values(
            failed_attempts=case((User.failed_attempts >= MAX_FAILED_ATTEMPTS - 1, 0), else_=User.failed_attempts + 1),
            locked_until=case((User.failed_attempts >= MAX_FAILED_ATTEMPTS - 1,
                               literal(now + timedelta(minutes=LOCK_MINUTES), type_=User.locked_until.type)),
                              else_=User.locked_until),
        ).execution_options(synchronize_session=False))
        await session.commit()
        await session.refresh(user)
        is_locked = user.locked_until is not None and user.locked_until > now
        await write_audit(session, user.id, "account_locked" if is_locked else "login_failed", ip, ua)
        if is_locked:
            await mailer.notify(session, user, "account_locked", {"ip": ip, "ua": ua, "time": _now_text()})
        else:
            await _notify_login_failed(session, user, ip, ua)
        raise unauthorized("邮箱或主密码错误", "invalid_credentials")
    prev_ip = user.last_login_ip
    result = await session.execute(update(User).where(User.id == user.id,
                                                      User.credential_version == user.credential_version,
                                                      User.auth_hash == user.auth_hash,
                                                      or_(User.locked_until.is_(None), User.locked_until <= now))
                                   .values(failed_attempts=0, locked_until=None, last_login_at=now,
                                           last_login_ip=ip).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("登录状态已变化，请重新登录")
    await session.refresh(user)
    if user.totp_enabled_at is not None:
        challenge, seconds = await _new_challenge(session, user, TWO_FA)
        await write_audit(session, user.id, "login_password_ok", ip, ua)
        return AuthResult(requires_2fa=True, challenge=challenge, expires_in=seconds)
    issued = await _issue_tokens(session, user, ip, ua)
    await write_audit(session, user.id, "login_success", ip, ua)
    await _notify_login(session, user, ip, ua, prev_ip)
    return _full_result(user, *issued)


async def refresh_session(session: AsyncSession, refresh_token: str, ip: str, ua: str) -> AuthResult:
    row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(refresh_token)))
    now = utcnow()
    user = await session.get(User, row.user_id) if row else None
    if (row is None or user is None or not row.session_id or row.revoked_at is not None
            or row.expires_at <= now or row.credential_version != user.credential_version):
        raise unauthorized("登录已过期，请重新登录")
    result = await session.execute(update(RefreshToken).where(
        RefreshToken.id == row.id, RefreshToken.revoked_at.is_(None), RefreshToken.expires_at > now,
        RefreshToken.credential_version == user.credential_version,
        exists(select(User.id).where(User.id == user.id, User.credential_version == row.credential_version)),
    ).values(revoked_at=now).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("登录已过期，请重新登录")
    issued = await _issue_tokens(session, user, ip, ua, row.session_id)
    return _full_result(user, *issued)


async def logout(session: AsyncSession, refresh_token: str | None, user_id: str | None = None) -> None:
    if refresh_token:
        row = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(refresh_token)))
        if row is not None and row.session_id:
            await session.execute(update(RefreshToken).where(RefreshToken.user_id == row.user_id,
                                                            RefreshToken.session_id == row.session_id)
                                  .values(revoked_at=utcnow()).execution_options(synchronize_session=False))
            user_id = row.user_id
            await session.commit()
    if user_id:
        await write_audit(session, user_id, "logout")


async def _replace_credentials(session, user, kdf, auth_hash, wrapped, nonce) -> None:
    result = await session.execute(update(User).where(User.id == user.id,
                                                      User.credential_version == user.credential_version).values(
        auth_hash=hash_auth_key(auth_hash), kdf_algo=kdf.algo, kdf_salt=kdf.salt,
        kdf_memory_kib=kdf.memoryKib, kdf_time=kdf.time, kdf_parallel=kdf.parallel,
        wrapped_dek=wrapped, dek_nonce=nonce, credential_version=User.credential_version + 1,
        failed_attempts=0, locked_until=None,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("凭据已变化，请重新开始")
    await session.refresh(user)
    await _revoke_all_sessions(session, user.id)


async def change_password(session, user, payload: ChangePasswordRequest, ip, ua) -> None:
    if not verify_auth_key(payload.oldAuthHash, user.auth_hash):
        raise unauthorized("当前主密码错误", "invalid_credentials")
    await _replace_credentials(session, user, payload.newKdf, payload.newAuthHash,
                               payload.wrappedDek, payload.dekNonce)
    await write_audit(session, user.id, "password_changed", ip, ua)
    await mailer.notify(session, user, "password_changed", {"ip": ip, "ua": ua, "time": _now_text()})


def _current_totp(user) -> pyotp.TOTP:
    if not user.totp_secret_enc or not user.totp_secret_nonce:
        raise bad_request("尚未初始化 2FA，请先绑定")
    return pyotp.TOTP(decrypt_server(user.totp_secret_enc, user.totp_secret_nonce))


def _totp_step(user, code):
    totp = _current_totp(user)
    current = int(utcnow().timestamp()) // totp.interval
    for step in [current, current - 1, current + 1]:
        if step >= 0 and pyotp.utils.strings_equal(str(code).strip(), totp.at(step * totp.interval)):
            return step
    return None


async def _claim_totp_step(session, user, step) -> None:
    result = await session.execute(update(User).where(
        User.id == user.id, User.credential_version == user.credential_version,
        User.two_factor_version == user.two_factor_version, User.totp_enabled_at.is_not(None),
        or_(User.totp_last_step.is_(None), User.totp_last_step < step),
    ).values(totp_last_step=step).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("验证码已使用，请等待下一个验证码", "invalid_code")


async def setup_two_factor(session: AsyncSession, user: User) -> dict:
    if user.totp_enabled_at is not None:
        raise conflict("2fa_already_enabled", "已开启 2FA，请先关闭再重新绑定")
    secret = pyotp.random_base32()
    ciphertext, nonce = encrypt_server(secret)
    result = await session.execute(update(User).where(User.id == user.id, User.totp_enabled_at.is_(None),
                                                      User.credential_version == user.credential_version)
                                   .values(totp_secret_enc=ciphertext, totp_secret_nonce=nonce)
                                   .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise conflict("2fa_already_enabled", "两步验证状态已变化")
    await session.commit()
    return {"secret": secret, "otpauthUrl": pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="ByPassWord")}


async def verify_unlock_totp(session, user, code, ip="", ua="") -> bool:
    if user.totp_enabled_at is None:
        raise bad_request("该账号未开启两步验证")
    step = _totp_step(user, code)
    if step is None:
        await write_audit(session, user.id, "2fa_failed", ip, ua, meta="unlock")
        raise unauthorized("验证码错误", "invalid_code")
    await _claim_totp_step(session, user, step)
    await write_audit(session, user.id, "2fa_verified", ip, ua, meta="unlock")
    return True


def _add_recovery_codes(session, user_id) -> list[str]:
    codes = new_recovery_codes(10)
    for value in codes:
        session.add(TotpRecoveryCode(user_id=user_id, code_hash=hmac_hex(value, "recovery")))
    return codes


async def enable_two_factor(session, user, code, ip, ua, session_id=None) -> list[str]:
    if user.totp_enabled_at is not None:
        raise conflict("2fa_already_enabled", "已开启 2FA，请勿重复启用")
    step = _totp_step(user, code)
    if step is None:
        raise unauthorized("验证码错误", "invalid_code")
    result = await session.execute(update(User).where(
        User.id == user.id, User.totp_enabled_at.is_(None), User.totp_secret_enc == user.totp_secret_enc,
        User.credential_version == user.credential_version,
        User.two_factor_version == user.two_factor_version,
    ).values(totp_enabled_at=utcnow(), two_factor_version=User.two_factor_version + 1, totp_last_step=step)
      .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise conflict("2fa_already_enabled", "已开启 2FA，请勿重复启用")
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user.id))
    codes = _add_recovery_codes(session, user.id)
    await _revoke_other_sessions(session, user.id, session_id)
    await write_audit(session, user.id, "2fa_enabled", ip, ua)
    await session.refresh(user)
    await mailer.notify(session, user, "two_factor_changed", {"ip": ip, "ua": ua, "time": _now_text(), "detail": "已开启两步验证"})
    return codes


async def verify_two_factor(session, challenge, code, ip, ua) -> AuthResult:
    user, payload = await _challenge_user(session, challenge, TWO_FA)
    if user.totp_enabled_at is None:
        raise unauthorized("二次验证已失效，请重新登录")
    step = _totp_step(user, code)
    if step is None:
        await _fail_challenge(session, payload, TWO_FA)
    await _consume_challenge(session, payload, TWO_FA)
    await _claim_totp_step(session, user, step)
    issued = await _issue_tokens(session, user, ip, ua)
    await write_audit(session, user.id, "login_success_2fa", ip, ua)
    return _full_result(user, *issued)


def _normalize_recovery_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{raw[:4]}-{raw[4:]}" if len(raw) >= 8 else raw


async def verify_recovery_code(session, challenge, recovery_code, ip, ua) -> AuthResult:
    user, payload = await _challenge_user(session, challenge, TWO_FA)
    if user.totp_enabled_at is None:
        raise unauthorized("二次验证已失效，请重新登录")
    target = hmac_hex(_normalize_recovery_code(recovery_code), "recovery")
    await _consume_challenge(session, payload, TWO_FA)
    result = await session.execute(update(TotpRecoveryCode).where(
        TotpRecoveryCode.user_id == user.id, TotpRecoveryCode.code_hash == target,
        TotpRecoveryCode.used_at.is_(None),
    ).values(used_at=utcnow()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()  # Invalid code must not consume a valid challenge.
        await _fail_challenge(session, payload, TWO_FA, "恢复码无效或已使用", "invalid_recovery_code")
    issued = await _issue_tokens(session, user, ip, ua)
    await write_audit(session, user.id, "login_success_recovery", ip, ua)
    await _notify_login(session, user, ip, ua, None, recovery=True)
    return _full_result(user, *issued)


async def _claim_two_factor_change(session, user, **values):
    result = await session.execute(update(User).where(User.id == user.id,
                                                      User.credential_version == user.credential_version,
                                                      User.two_factor_version == user.two_factor_version)
                                   .values(two_factor_version=User.two_factor_version + 1, **values)
                                   .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("两步验证状态已变化，请重试")


async def disable_two_factor(session, user, auth_hash, code, ip, ua, session_id=None) -> None:
    if not verify_auth_key(auth_hash, user.auth_hash):
        raise unauthorized("主密码错误", "invalid_credentials")
    step = _totp_step(user, code) if user.totp_enabled_at is not None else None
    if step is None:
        raise unauthorized("验证码错误", "invalid_code")
    await _claim_totp_step(session, user, step)
    await _claim_two_factor_change(session, user, totp_secret_enc=None, totp_secret_nonce=None,
                                   totp_enabled_at=None, totp_last_step=None)
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user.id))
    await _revoke_other_sessions(session, user.id, session_id)
    await write_audit(session, user.id, "2fa_disabled", ip, ua)
    await session.refresh(user)
    await mailer.notify(session, user, "two_factor_changed", {"ip": ip, "ua": ua, "time": _now_text(), "detail": "已关闭两步验证"})


async def count_recovery_codes(session, user) -> int:
    value = await session.scalar(select(func.count()).select_from(TotpRecoveryCode).where(
        TotpRecoveryCode.user_id == user.id, TotpRecoveryCode.used_at.is_(None)))
    return int(value or 0)


async def regenerate_recovery_codes(session, user, auth_hash, code, ip, ua, session_id=None) -> list[str]:
    if not verify_auth_key(auth_hash, user.auth_hash):
        raise unauthorized("主密码错误", "invalid_credentials")
    step = _totp_step(user, code) if user.totp_enabled_at is not None else None
    if step is None:
        raise unauthorized("验证码错误", "invalid_code")
    await _claim_totp_step(session, user, step)
    await _claim_two_factor_change(session, user)
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user.id))
    codes = _add_recovery_codes(session, user.id)
    await _revoke_other_sessions(session, user.id, session_id)
    await write_audit(session, user.id, "recovery_codes_regenerated", ip, ua)
    return codes


async def configure_recovery(session, user, payload: RecoveryConfigurationRequest, ip, ua, session_id=None):
    if not verify_auth_key(payload.authHash, user.auth_hash):
        raise unauthorized("主密码错误", "invalid_credentials")
    if user.totp_enabled_at is not None:
        step = _totp_step(user, payload.code) if payload.code else None
        if step is None:
            raise unauthorized("请输入有效的两步验证码", "invalid_code")
        await _claim_totp_step(session, user, step)
    await _claim_two_factor_change(session, user,
                                   recovery_auth_hash=hash_auth_key(payload.recoveryAuthHash),
                                   recovery_wrapped_dek=payload.recoveryWrappedDek,
                                   recovery_dek_nonce=payload.recoveryDekNonce)
    await _revoke_other_sessions(session, user.id, session_id)
    await write_audit(session, user.id, "recovery_configured", ip, ua)


async def request_password_reset(session, email, ip, ua) -> None:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        return
    code = new_numeric_code(6)
    # Invalidate prior unused mail codes before creating the next one.
    await session.execute(update(PasswordReset).where(PasswordReset.user_id == user.id,
                                                     PasswordReset.used_at.is_(None))
                          .values(used_at=utcnow()).execution_options(synchronize_session=False))
    session.add(PasswordReset(user_id=user.id, code_hash=hmac_hex(code, "reset"),
                              expires_at=utcnow() + timedelta(minutes=RESET_CODE_MINUTES), ip=ip))
    await session.commit()
    subject, text = mailer.reset_code_email(code)
    sent = await mailer.send_to_user(session, user, subject, text)
    await write_audit(session, user.id, "reset_code_sent", ip, ua, meta="sent" if sent else "mail_failed")


async def verify_reset_code(session, email, code, ip, ua) -> dict:
    user = await session.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        raise unauthorized("验证码错误或已过期", "invalid_code")
    row = await session.scalar(select(PasswordReset).where(
        PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None), PasswordReset.expires_at > utcnow(),
    ).order_by(PasswordReset.created_at.desc(), PasswordReset.id.desc()).limit(1))
    if row is None or row.attempts >= RESET_CODE_MAX_ATTEMPTS:
        raise unauthorized("验证码错误或已过期", "invalid_code")
    filters = (PasswordReset.id == row.id, PasswordReset.used_at.is_(None),
               PasswordReset.expires_at > utcnow(), PasswordReset.attempts < RESET_CODE_MAX_ATTEMPTS)
    if row.code_hash != hmac_hex(code, "reset"):
        await session.execute(update(PasswordReset).where(*filters).values(
            attempts=PasswordReset.attempts + 1,
            used_at=case((PasswordReset.attempts >= RESET_CODE_MAX_ATTEMPTS - 1,
                          literal(utcnow(), type_=PasswordReset.used_at.type)), else_=None),
        ).execution_options(synchronize_session=False))
        await session.commit()
        raise unauthorized("验证码错误或已过期", "invalid_code")
    result = await session.execute(update(PasswordReset).where(*filters, PasswordReset.code_hash == hmac_hex(code, "reset"))
                                   .values(used_at=utcnow()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        await session.rollback()
        raise unauthorized("验证码错误或已过期", "invalid_code")
    if not user.recovery_auth_hash:
        await session.commit()
        raise ApiError(403, "recovery_not_configured", "请先用现有主密码登录，在安全设置中升级恢复码后再使用邮件恢复")
    token, seconds = await _new_challenge(session, user, RESET)
    await write_audit(session, user.id, "reset_code_verified", ip, ua)
    return {"resetToken": token, "expiresIn": seconds,
            "recoveryWrappedDek": user.recovery_wrapped_dek,
            "recoveryDekNonce": user.recovery_dek_nonce}


async def reset_password(session, payload: ResetPasswordRequest, ip, ua) -> None:
    user, token = await _challenge_user(session, payload.resetToken, RESET)
    if not user.recovery_auth_hash:
        raise ApiError(403, "recovery_not_configured", "此账号尚未升级安全恢复配置")
    if not verify_auth_key(payload.recoveryAuthHash, user.recovery_auth_hash):
        await _fail_challenge(session, token, RESET, "恢复证明错误或已失效", "invalid_recovery_proof")
    await _consume_challenge(session, token, RESET)
    await _replace_credentials(session, user, payload.newKdf, payload.newAuthHash,
                               payload.wrappedDek, payload.dekNonce)
    await write_audit(session, user.id, "password_reset", ip, ua)
    await mailer.notify(session, user, "password_changed", {"ip": ip, "ua": ua, "time": _now_text()})
