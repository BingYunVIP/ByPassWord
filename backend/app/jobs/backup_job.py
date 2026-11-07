"""Timezone-aware scheduled snapshots, with one scheduler across worker processes."""
import asyncio
import fcntl
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from ..core.config import settings
from ..core.db import SessionLocal
from ..core.ownership import get_owner_user_id
from ..core.runtime_security import private_directory
from ..models import User
from ..services import backup_service, mailer, secrets

logger = logging.getLogger("bypw.jobs")
INTERVAL_SECONDS = 60

async def _retention_days(session) -> int:
    owner = await get_owner_user_id(session)
    raw = await secrets.get_secret(session, owner, "backup_retention_days") if owner else None
    return int(raw) if raw and raw.isdigit() else 30

async def _should_snapshot(session, now: datetime | None = None) -> bool:
    owner = await get_owner_user_id(session)
    if owner is None:
        return False
    schedule = await secrets.get_secret(session, owner, "backup_schedule") or "weekly-02:00"
    current = now or datetime.now(ZoneInfo(settings.backup_timezone))
    if current.tzinfo is None:
        raise ValueError("scheduler time must include a timezone")
    if schedule == "daily-03:00":
        hour = 3
    elif schedule == "weekly-02:00":
        if current.weekday() != 6:
            return False
        hour = 2
    else:
        return False
    if current.hour != hour:
        return False
    scheduled = current.replace(hour=hour, minute=0, second=0, microsecond=0)
    snapshots = [item for item in backup_service.list_snapshots() if item["kind"] == "auto"]
    return not snapshots or datetime.fromisoformat(snapshots[0]["createdAt"]) < scheduled

async def run_periodic_backup(stop_event: asyncio.Event) -> None:
    directory = backup_service.backup_dir()
    private_directory(directory)
    lock = os.open(directory / ".scheduler.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.fchmod(lock, 0o600)
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("另一工作进程负责备份调度")
            return
        last_capacity_notice = None
        while not stop_event.is_set():
            try:
                async with SessionLocal() as session:
                    if await _should_snapshot(session):
                        owner_id = await get_owner_user_id(session)
                        owner = await session.get(User, owner_id) if owner_id else None
                        now_text = datetime.now(ZoneInfo(settings.backup_timezone)).isoformat()
                        try:
                            meta = backup_service.create_snapshot("auto")
                            backup_service.cleanup(await _retention_days(session), validated_snapshot=meta["id"])
                            last_capacity_notice = None
                            logger.info("自动加密备份完成: %s", meta["id"])
                            if owner:
                                await mailer.notify(session, owner, "backup_created", {"time": now_text, "detail": "已验证的自动加密备份"})
                        except backup_service.BackupLimitReached:
                            # Full capacity never triggers delete-before-backup or
                            # minute-by-minute emails. One reminder per hour max.
                            if last_capacity_notice is None or time.monotonic() - last_capacity_notice >= 3600:
                                logger.warning("已有两份备份，自动备份暂停；未删除旧备份")
                                if owner:
                                    await mailer.notify(session, owner, "backup_failed", {"time": now_text, "detail": "已有两份备份，未创建第三份；请验证并管理现有备份"})
                                last_capacity_notice = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("备份任务失败 (%s)", type(exc).__name__)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        os.close(lock)
