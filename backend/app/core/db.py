"""数据库引擎与会话。

SQLite 必须显式开启 WAL / 外键 / 忙等待，否则并发与外键约束都会失效。
"""

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .runtime_security import sqlite_file

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)


if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
        # Existing permission mistakes are refused by deployed startup; newly
        # created SQLite/WAL files inherit the service's restrictive umask.
        path = sqlite_file()
        if path is not None:
            for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
                if candidate.is_file() and not candidate.is_symlink():
                    candidate.chmod(0o600)


SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with SessionLocal() as session:
        yield session


async def check_database() -> None:
    """健康检查用：连接可用即返回，异常向上抛。"""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    await engine.dispose()
