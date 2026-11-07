"""数据库层测试：PRAGMA、外键级联、时间类型往返。"""

from datetime import datetime, timezone

from sqlalchemy import select, text

from app.core.db import SessionLocal, engine
from app.models import Folder, User


async def test_sqlite_pragmas_applied() -> None:
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await conn.execute(text("PRAGMA busy_timeout"))).scalar() == 5000


async def test_delete_user_cascades_to_folders() -> None:
    async with SessionLocal() as session:
        user = User(
            email="cascade@example.com",
            auth_hash="hash",
            kdf_salt="salt",
            wrapped_dek="wrapped",
            dek_nonce="nonce",
        )
        session.add(user)
        await session.commit()

        session.add(Folder(user_id=user.id, ciphertext="cipher", nonce="nonce"))
        await session.commit()

        await session.delete(user)
        await session.commit()

        folders = (await session.execute(select(Folder))).scalars().all()
        assert folders == []


async def test_utc_datetime_roundtrip_keeps_timezone() -> None:
    moment = datetime(2026, 11, 1, 13, 5, 30, tzinfo=timezone.utc)
    async with SessionLocal() as session:
        user = User(
            email="time@example.com",
            auth_hash="hash",
            kdf_salt="salt",
            wrapped_dek="wrapped",
            dek_nonce="nonce",
            created_at=moment,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.created_at.tzinfo is not None
        assert user.created_at == moment
