"""备份快照路由。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..core.deps import require_owner_user
from ..core.errors import ApiError
from ..models import User
from ..services import auth_service, backup_service, mailer

router = APIRouter(prefix="/backup", tags=["backup"])


def _now_text() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


@router.get("/list", summary="备份快照列表")
async def list_backups(_user: User = Depends(require_owner_user)) -> dict:
    items = backup_service.list_snapshots()
    return {"items": items, "capacity": 2, "count": len(items), "canCreate": len(items) < 2}


@router.post("/snapshot", summary="立即创建手动快照（不受保留策略清理）")
async def create_snapshot(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_owner_user),
) -> dict:
    try:
        meta = backup_service.create_snapshot("manual")
    except backup_service.BackupLimitReached:
        raise ApiError(409, "backup_limit", "已有两份备份；请先在运维端验证和归档现有备份，未创建新备份") from None
    except Exception as exc:  # noqa: BLE001
        await mailer.notify(
            session, user, "backup_failed", {"time": _now_text(), "detail": str(exc)[:200]}
        )
        raise
    await auth_service.write_audit(session, user.id, "backup_snapshot", meta=meta["id"])
    await mailer.notify(
        session, user, "backup_created", {"time": _now_text(), "detail": "手动快照"}
    )
    return meta
