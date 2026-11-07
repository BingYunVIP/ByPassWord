"""FastAPI 应用入口。

启动：uvicorn app.main:app --reload --port 8000
文档：/api/docs
"""

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from slowapi.errors import RateLimitExceeded

from .api import audit, auth, backup, health, vault
from .api import settings as settings_api
from .core.config import settings
from .core.db import dispose_engine
from .core.errors import ApiError
from .core.rate_limit import limiter, rate_limit_handler
from .core.runtime_security import SecurityMiddleware, validate_runtime_paths
from .jobs.backup_job import run_periodic_backup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bypw")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_paths()
    logger.info("ByPassWord API 启动 (env=%s)", settings.app_env)
    if settings.auto_migrate:
        from .core.migrate import run_migrations

        try:
            await asyncio.to_thread(run_migrations)
        except Exception:
            logger.exception("数据库迁移失败，服务终止启动")
            raise

    stop_event = asyncio.Event()
    backup_task = asyncio.create_task(run_periodic_backup(stop_event))

    yield

    stop_event.set()
    backup_task.cancel()
    try:
        await backup_task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    await dispose_engine()
    logger.info("ByPassWord API 已关闭")


app = FastAPI(
    title="ByPassWord API",
    version=settings.app_version,
    description="零知识密码库后端：服务端只存密文，不具备解密能力。",
    docs_url=f"{settings.api_prefix}/docs" if settings.app_env in {"development", "test"} else None,
    redoc_url=None,
    openapi_url=f"{settings.api_prefix}/openapi.json" if settings.app_env in {"development", "test"} else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
limiter.enabled = settings.rate_limit_enabled

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityMiddleware)

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "bad_request",
                "message": "参数不合法",
                "detail": [{"loc": list(error["loc"]), "type": error["type"], "message": "参数不合法"} for error in exc.errors()[:5]],
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """统一错误结构：{ error: { code, message, detail } }，不向客户端泄露堆栈。"""
    logger.exception("未处理异常: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "服务端异常",
                "detail": None,
            }
        },
    )


app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(vault.router, prefix=settings.api_prefix)
app.include_router(settings_api.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(backup.router, prefix=settings.api_prefix)


@app.get("/{resource_path:path}", include_in_schema=False)
async def serve_frontend(resource_path: str):
    """Serve one-origin built SPA; never turn an unknown API into index.html."""
    if not settings.static_dir or resource_path == settings.api_prefix.lstrip("/") or resource_path.startswith(settings.api_prefix.lstrip("/") + "/"):
        raise HTTPException(404)
    directory = Path(settings.static_dir).resolve()
    target = (directory / resource_path).resolve()
    if not target.is_relative_to(directory) or any(part.startswith(".") for part in Path(resource_path).parts):
        raise HTTPException(404)
    if target.is_file():
        return FileResponse(target)
    if Path(resource_path).suffix:
        raise HTTPException(404)
    index = (directory / "index.html").resolve()
    if not index.is_relative_to(directory) or not index.is_file():
        raise HTTPException(404)
    return FileResponse(index)
