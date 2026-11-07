"""FastAPI 依赖：当前用户、客户端信息。"""

import ipaddress

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RefreshToken, User
from ..models.base import utcnow
from .config import settings
from .db import get_session
from .errors import forbidden, unauthorized
from .ownership import get_owner_user_id
from .security import ACCESS, decode_token


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise unauthorized()

    token = header.split(" ", 1)[1].strip()
    payload = decode_token(token, ACCESS)
    user = await session.get(User, payload["sub"])
    sid = payload.get("sid")
    if user is None or payload["ver"] != user.credential_version or not isinstance(sid, str):
        raise unauthorized()
    active = await session.scalar(select(RefreshToken.id).where(
        RefreshToken.user_id == user.id,
        RefreshToken.session_id == sid,
        RefreshToken.credential_version == user.credential_version,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > utcnow(),
    ).limit(1))
    if active is None:
        raise unauthorized()
    request.state.auth_session_id = sid
    return user


async def require_owner_user(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    if await get_owner_user_id(session) != user.id:
        raise forbidden("仅部署所有者可操作此功能")
    return user


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    raw_trusted = getattr(settings, "trusted_proxy_ips", "")
    try:
        trusted = [ipaddress.ip_network(v.strip(), strict=False) for v in raw_trusted.split(",") if v.strip()]
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return peer
    if not any(peer_ip in network for network in trusted):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded or len(forwarded) > 1024:
        return peer
    try:
        chain = [ipaddress.ip_address(v.strip()) for v in forwarded.split(",")]
        if len(chain) > 20:
            return peer
        for address in reversed(chain):
            if not any(address in network for network in trusted):
                return str(address)
        return str(chain[0])
    except ValueError:
        return peer


def user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:500]
