"""ORM 基类与公共类型。"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """带时区的当前时间（UTC）。"""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


class UTCDateTime(TypeDecorator):
    """以 ISO8601 字符串（UTC）存储时间。

    SQLite 没有原生时间类型，直接用 DATETIME 会丢掉时区信息；
    这里统一存成 `2026-11-01T13:05:30Z`，读出来仍是带时区的 datetime。
    """

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def process_result_value(self, value: str | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Base(DeclarativeBase):
    pass
