"""审计日志查询。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..core.deps import get_current_user
from ..models import AuditLog, User

router = APIRouter(tags=["audit"])


@router.get("/audit", summary="审计日志（倒序，游标分页）")
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, description="上一页最后一条的 createdAt"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    stmt = (
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    )
    if cursor:
        stmt = stmt.where(AuditLog.created_at < cursor)

    rows = list((await session.scalars(stmt.limit(limit + 1))).all())
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "items": [
            {
                "id": row.id,
                "time": row.created_at.isoformat(),
                "action": row.action,
                "ip": row.ip,
                "ua": row.user_agent,
                "meta": row.meta,
            }
            for row in rows
        ],
        "nextCursor": rows[-1].created_at.isoformat() if has_more and rows else None,
    }
