"""测试夹具：使用独立的 SQLite 文件，绝不影响开发库。"""

import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import delete

TEST_DB = Path(__file__).parent / "test_bypw.db"

# 必须在导入 app.* 之前设置环境变量
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef0123456789abcdef"
os.environ["SERVER_SECRET"] = "test-server-secret-0123456789abcdef0123456789"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["ALLOW_REGISTRATION_AFTER_FIRST"] = "true"

if TEST_DB.exists():
    TEST_DB.unlink()


def pytest_configure(config):  # noqa: ANN001
    """会话开始前建表；测试环境关闭限流（否则连续登录会被 429 打断）。"""
    from app.core.db import engine
    from app.core.rate_limit import limiter
    from app.models import Base

    limiter.enabled = False

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())


@pytest.fixture(autouse=True)
async def clean_database():
    """每个测试前清空所有业务表，保证用例互不影响。"""
    from app.core.db import SessionLocal
    from app.models import (
        AuditLog,
        Folder,
        Item,
        PasswordReset,
        RefreshToken,
        TotpRecoveryCode,
        User,
        UserSecret,
        UserSettings,
        VaultState,
    )

    async with SessionLocal() as session:
        for model in (
            TotpRecoveryCode,
            PasswordReset,
            RefreshToken,
            AuditLog,
            Item,
            Folder,
            VaultState,
            UserSecret,
            UserSettings,
            User,
        ):
            await session.execute(delete(model))
        await session.commit()

    yield
