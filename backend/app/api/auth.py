"""认证路由：/api/auth/*"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import get_session
from ..core.deps import client_ip, get_current_user, user_agent
from ..core.rate_limit import limiter
from ..core.ownership import get_owner_user_id
from ..models import User
from ..schemas.auth import (
    ChangePasswordRequest,
    DisableTwoFactorRequest,
    EnableTwoFactorRequest,
    ForgotRequest,
    ForgotVerifyRequest,
    LoginRequest,
    MeResponse,
    PreloginRequest,
    RegisterRequest,
    RecoveryConfigurationRequest,
    ResetPasswordRequest,
    VerifyRecoveryRequest,
    VerifyTwoFactorRequest,
)
from ..services import auth_service
from ..services.auth_service import AuthResult

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "bypw_refresh"
REFRESH_PATH = "/api/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=settings.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path=REFRESH_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)


def _payload(result: AuthResult) -> dict:
    if result.requires_2fa:
        return {
            "requires2fa": True,
            "challenge": result.challenge,
            "expiresIn": result.expires_in,
        }
    return {
        "accessToken": result.access_token,
        "expiresIn": result.expires_in,
        "wrappedDek": result.wrapped_dek,
        "dekNonce": result.dek_nonce,
    }


@router.get("/registration-status", summary="个人密码库初始化状态")
async def registration_status(session: AsyncSession = Depends(get_session)) -> dict:
    return await auth_service.registration_status(session)


@router.post("/prelogin", summary="预登录：取 KDF 参数")
@limiter.limit("20/minute")
async def prelogin(
    request: Request,
    payload: PreloginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await auth_service.prelogin(session, payload.email)


@router.post("/register", summary="注册（客户端已生成 DEK 与恢复码副本）", status_code=201)
@limiter.limit("3/hour")
async def register(
    request: Request,
    payload: RegisterRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await auth_service.register(
        session, payload, client_ip(request), user_agent(request)
    )
    if result.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
    return _payload(result)


@router.post("/login", summary="登录（开启 2FA 时返回 challenge）")
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await auth_service.login(
        session, payload, client_ip(request), user_agent(request)
    )
    if result.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
    return _payload(result)


@router.post("/refresh", summary="刷新访问令牌（轮换 refresh token）")
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        from ..core.errors import unauthorized

        raise unauthorized("登录已过期，请重新登录")

    result = await auth_service.refresh_session(
        session, token, client_ip(request), user_agent(request)
    )
    if result.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
    return _payload(result)


@router.post("/logout", summary="登出（撤销当前 refresh token）")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    token = request.cookies.get(REFRESH_COOKIE)
    await auth_service.logout(session, token)
    _clear_refresh_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse, summary="当前用户信息")
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        twoFactorEnabled=user.totp_enabled_at is not None,
        recoveryConfigured=bool(user.recovery_auth_hash),
        isOwner=await get_owner_user_id(session) == user.id,
        createdAt=user.created_at.isoformat(),
        lastLoginAt=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/change-password", summary="修改主密码（重新包裹同一 DEK）")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await auth_service.change_password(
        session, user, payload, client_ip(request), user_agent(request)
    )
    return {"ok": True}


@router.put("/recovery", summary="验证主密码后升级或轮换金库恢复码")
@limiter.limit("5/minute")
async def configure_recovery(
    request: Request,
    payload: RecoveryConfigurationRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await auth_service.configure_recovery(
        session, user, payload, client_ip(request), user_agent(request),
        session_id=request.state.auth_session_id,
    )
    return {"ok": True, "recoveryConfigured": True}


# ============================================================
# 账号 2FA
# ============================================================


@router.post("/2fa/setup", summary="生成 TOTP 密钥与 otpauth 链接")
@limiter.limit("3/minute")
async def setup_2fa(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await auth_service.setup_two_factor(session, user)


@router.post("/unlock/verify-totp", summary="锁定后解锁时的 2FA 校验")
@limiter.limit("5/5minutes")
async def unlock_verify_totp(
    request: Request,
    payload: EnableTwoFactorRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await auth_service.verify_unlock_totp(
        session, user, payload.code, client_ip(request), user_agent(request)
    )
    return {"ok": True}


@router.post("/2fa/enable", summary="校验验证码并启用 2FA（返回 10 个恢复码）")
@limiter.limit("5/5minutes")
async def enable_2fa(
    request: Request,
    payload: EnableTwoFactorRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    codes = await auth_service.enable_two_factor(
        session, user, payload.code, client_ip(request), user_agent(request),
        session_id=request.state.auth_session_id,
    )
    return {"recoveryCodes": codes}


@router.post("/2fa/verify", summary="登录第二步：校验 TOTP")
@limiter.limit("5/5minutes")
async def verify_2fa(
    request: Request,
    payload: VerifyTwoFactorRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await auth_service.verify_two_factor(
        session, payload.challenge, payload.code, client_ip(request), user_agent(request)
    )
    if result.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
    return _payload(result)


@router.post("/2fa/verify-recovery", summary="登录第二步：用一次性恢复码")
@limiter.limit("5/5minutes")
async def verify_2fa_recovery(
    request: Request,
    payload: VerifyRecoveryRequest,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await auth_service.verify_recovery_code(
        session, payload.challenge, payload.recoveryCode, client_ip(request), user_agent(request)
    )
    if result.refresh_token:
        _set_refresh_cookie(response, result.refresh_token)
    return _payload(result)


@router.post("/2fa/disable", summary="关闭 2FA（需主密码 + 当前验证码）")
@limiter.limit("5/5minutes")
async def disable_2fa(
    request: Request,
    payload: DisableTwoFactorRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    await auth_service.disable_two_factor(
        session, user, payload.authHash, payload.code, client_ip(request), user_agent(request),
        session_id=request.state.auth_session_id,
    )
    return {"ok": True}


@router.get("/2fa/recovery-codes", summary="剩余可用恢复码数量")
async def recovery_codes(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return {"remaining": await auth_service.count_recovery_codes(session, user)}


@router.post("/2fa/recovery-codes/regenerate", summary="重新生成恢复码（旧的作废）")
@limiter.limit("5/5minutes")
async def regenerate_recovery_codes(
    request: Request,
    payload: DisableTwoFactorRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    codes = await auth_service.regenerate_recovery_codes(
        session, user, payload.authHash, payload.code, client_ip(request), user_agent(request),
        session_id=request.state.auth_session_id,
    )
    return {"recoveryCodes": codes}


# ============================================================
# 忘记主密码
# ============================================================


@router.post("/forgot", summary="发送重置验证码（无论邮箱是否存在都返回 202）", status_code=202)
@limiter.limit("3/hour")
async def forgot(
    request: Request,
    payload: ForgotRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await auth_service.request_password_reset(
        session, payload.email, client_ip(request), user_agent(request)
    )
    return {"ok": True, "message": "若该邮箱已注册，验证码已发送"}


@router.post("/forgot/verify", summary="校验验证码，换取一次性重置凭证")
@limiter.limit("5/10minutes")
async def forgot_verify(
    request: Request,
    payload: ForgotVerifyRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await auth_service.verify_reset_code(
        session, payload.email, payload.code, client_ip(request), user_agent(request)
    )


@router.post("/reset", summary="重置主密码（客户端用恢复码解出 DEK 后重新包裹）")
@limiter.limit("5/10minutes")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await auth_service.reset_password(
        session, payload, client_ip(request), user_agent(request)
    )
    return {"ok": True}
