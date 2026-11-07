"""P5：邮箱配置、备份策略与快照、审计日志。"""

import base64
import os
import time
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import config
from app.main import app
from app.services import backup_service

BASE = "http://test"
AUTH_KEY = base64.b64encode(os.urandom(32)).decode()


def b64(n: int) -> str:
    return base64.b64encode(os.urandom(n)).decode()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        yield c


@pytest.fixture
async def auth(client: AsyncClient) -> dict:
    email = f"p5-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1},
            "authHash": AUTH_KEY,
            "wrappedDek": b64(48),
            "dekNonce": b64(12),
            "recoveryWrappedDek": b64(48),
            "recoveryDekNonce": b64(12),
        },
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['accessToken']}"}


# ============================================================
# 邮箱配置
# ============================================================


async def test_mail_settings_default_and_update(client: AsyncClient, auth: dict) -> None:
    initial = await client.get("/api/settings/mail", headers=auth)
    assert initial.status_code == 200
    assert initial.json()["host"] == "smtp.qq.com"
    assert initial.json()["hasPassword"] is False

    saved = await client.put(
        "/api/settings/mail",
        json={
            "host": "smtp.qq.com",
            "port": 465,
            "secure": True,
            "user": "me@qq.com",
            "password": "abcd1234abcd1234",
            "from": "me@qq.com",
            "fromName": "密码库",
        },
        headers=auth,
    )
    assert saved.status_code == 200
    assert saved.json()["hasPassword"] is True

    after = (await client.get("/api/settings/mail", headers=auth)).json()
    assert after["user"] == "me@qq.com"
    assert after["fromName"] == "密码库"
    assert after["hasPassword"] is True
    assert "password" not in after  # 授权码绝不下发


async def test_mail_password_kept_when_omitted(client: AsyncClient, auth: dict) -> None:
    payload = {
        "host": "smtp.qq.com",
        "port": 465,
        "secure": True,
        "user": "me@qq.com",
        "password": "abcd1234abcd1234",
        "from": "me@qq.com",
        "fromName": "密码库",
    }
    await client.put("/api/settings/mail", json=payload, headers=auth)

    payload.pop("password")
    payload["fromName"] = "改名了"
    await client.put("/api/settings/mail", json=payload, headers=auth)

    after = (await client.get("/api/settings/mail", headers=auth)).json()
    assert after["fromName"] == "改名了"
    assert after["hasPassword"] is True


async def test_mail_test_fails_without_smtp(client: AsyncClient, auth: dict) -> None:
    response = await client.post("/api/settings/mail/test", headers=auth)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "mail_failed"


# ============================================================
# 备份策略与快照
# ============================================================


async def test_backup_settings_roundtrip(client: AsyncClient, auth: dict) -> None:
    default = (await client.get("/api/settings/backup", headers=auth)).json()
    assert default["retentionDays"] == 30

    saved = await client.put(
        "/api/settings/backup",
        json={"schedule": "weekly-02:00", "retentionDays": 7},
        headers=auth,
    )
    assert saved.status_code == 200

    after = (await client.get("/api/settings/backup", headers=auth)).json()
    assert after["schedule"] == "weekly-02:00"
    assert after["retentionDays"] == 7


async def test_snapshot_created_and_listed(client: AsyncClient, auth: dict, tmp_path, monkeypatch) -> None:
    directory = tmp_path / "backups"
    directory.mkdir(mode=0o700)
    key = tmp_path / "backup.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    monkeypatch.setattr(config.settings, "backup_dir", str(directory))
    monkeypatch.setattr(config.settings, "backup_key_file", str(key))

    created = await client.post("/api/backup/snapshot", headers=auth)
    assert created.status_code == 200, created.text
    meta = created.json()
    assert meta["kind"] == "manual"
    assert (directory / meta["id"]).exists()
    assert meta["encrypted"] and meta["verified"]

    listed = (await client.get("/api/backup/list", headers=auth)).json()
    assert any(item["id"] == meta["id"] for item in listed["items"])


async def test_cleanup_respects_retention(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "backup_dir", str(tmp_path))

    old_auto = tmp_path / "vault-20250101-030000-auto.db"
    old_manual = tmp_path / "vault-20250101-040000-manual.db"
    fresh_auto = tmp_path / "vault-20990101-030000-auto.db"
    for path in (old_auto, old_manual, fresh_auto):
        path.write_bytes(b"x")

    old_time = time.time() - 40 * 86400
    os.utime(old_auto, (old_time, old_time))
    os.utime(old_manual, (old_time, old_time))

    # Expiry cannot remove any old copy before a new verified replacement.
    removed = backup_service.cleanup(30)
    assert removed == 0
    assert old_auto.exists()
    assert old_manual.exists(), "手动快照不应被自动清理"
    assert fresh_auto.exists()

    # retention=0 表示永久保留
    assert backup_service.cleanup(0) == 0


# ============================================================
# 审计日志
# ============================================================


async def test_audit_lists_actions(client: AsyncClient, auth: dict) -> None:
    await client.post("/api/settings/mail/test", headers=auth)  # 产生 mail_test 审计

    response = await client.get("/api/audit?limit=20", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["items"], "应至少有一条审计记录"
    actions = {item["action"] for item in body["items"]}
    assert "register" in actions or "mail_test" in actions
    assert body["nextCursor"] is None or isinstance(body["nextCursor"], str)


async def test_audit_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/audit")).status_code == 401
