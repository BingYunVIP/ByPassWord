"""健康检查：不鉴权，用于部署探活与监控。"""

from fastapi import APIRouter, Response, status

from ..core.config import settings
from ..core.db import check_database

router = APIRouter(tags=["health"])


@router.get("/health", summary="健康检查")
async def health(response: Response) -> dict:
    db_ok = True
    try:
        await check_database()
    except Exception:  # noqa: BLE001 - 健康检查不应因数据库异常而抛出
        db_ok = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.app_version,
        "db": "ok" if db_ok else "error",
        "env": settings.app_env,
    }
