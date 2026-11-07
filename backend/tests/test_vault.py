"""金库同步接口测试：拉取、增删改、乐观锁、增量墓碑、导入策略、设置。"""

import base64
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

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
    email = f"vault-{uuid.uuid4().hex[:8]}@example.com"
    response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1},
            "authHash": AUTH_KEY,
            "wrappedDek": b64(48),
            "dekNonce": b64(12),
            "recoveryWrappedDek": b64(48),
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['accessToken']}"}


def folder_payload(folder_id: str | None = None, sort_order: int = 0) -> dict:
    return {
        "id": folder_id or str(uuid.uuid4()),
        "ciphertext": b64(64),
        "nonce": b64(12),
        "sortOrder": sort_order,
    }


def item_payload(item_id: str | None = None) -> dict:
    return {
        "id": item_id or str(uuid.uuid4()),
        "ciphertext": b64(96),
        "nonce": b64(12),
    }


# ============================================================
# 鉴权与空态
# ============================================================


async def test_vault_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/vault")).status_code == 401
    assert (await client.post("/api/folders", json=folder_payload())).status_code == 401


async def test_empty_vault(client: AsyncClient, auth: dict) -> None:
    response = await client.get("/api/vault", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["rev"] == 0
    assert body["folders"] == []
    assert body["items"] == []


# ============================================================
# 增删改与乐观锁
# ============================================================


async def test_create_folder_and_item_bumps_rev(client: AsyncClient, auth: dict) -> None:
    folder = folder_payload()
    created = await client.post("/api/folders", json=folder, headers=auth)
    assert created.status_code == 201
    assert created.json()["rev"] == 1

    item = item_payload()
    created_item = await client.post("/api/items", json=item, headers=auth)
    assert created_item.status_code == 201
    assert created_item.json()["rev"] == 2

    vault = (await client.get("/api/vault", headers=auth)).json()
    assert vault["rev"] == 2
    assert len(vault["folders"]) == 1
    assert len(vault["items"]) == 1
    assert vault["folders"][0]["ciphertext"] == folder["ciphertext"]


async def test_create_is_idempotent(client: AsyncClient, auth: dict) -> None:
    payload = folder_payload()
    first = await client.post("/api/folders", json=payload, headers=auth)
    second = await client.post("/api/folders", json=payload, headers=auth)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["rev"] == second.json()["rev"]

    vault = (await client.get("/api/vault", headers=auth)).json()
    assert len(vault["folders"]) == 1


async def test_patch_conflict_returns_409(client: AsyncClient, auth: dict) -> None:
    created = await client.post("/api/folders", json=folder_payload(), headers=auth)
    folder_id = created.json()["id"]
    rev = created.json()["rev"]

    ok = await client.patch(
        f"/api/folders/{folder_id}",
        json={"ciphertext": b64(64), "nonce": b64(12), "sortOrder": 2, "rev": rev},
        headers=auth,
    )
    assert ok.status_code == 200
    new_rev = ok.json()["rev"]
    assert new_rev > rev

    stale = await client.patch(
        f"/api/folders/{folder_id}",
        json={"ciphertext": b64(64), "nonce": b64(12), "rev": rev},
        headers=auth,
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "rev_conflict"
    assert stale.json()["error"]["detail"]["rev"] == new_rev


async def test_soft_delete_and_incremental_tombstone(client: AsyncClient, auth: dict) -> None:
    created = await client.post("/api/items", json=item_payload(), headers=auth)
    item_id = created.json()["id"]
    rev = created.json()["rev"]

    deleted = await client.delete(f"/api/items/{item_id}?rev={rev}", headers=auth)
    assert deleted.status_code == 200
    tombstone_rev = deleted.json()["rev"]

    full = (await client.get("/api/vault", headers=auth)).json()
    assert full["items"] == []  # 全量不含已删除

    incremental = (await client.get(f"/api/vault?since={rev}", headers=auth)).json()
    assert len(incremental["items"]) == 1
    assert incremental["items"][0]["deletedAt"] is not None
    assert incremental["items"][0]["rev"] == tombstone_rev


async def test_delete_with_stale_rev_conflicts(client: AsyncClient, auth: dict) -> None:
    created = await client.post("/api/items", json=item_payload(), headers=auth)
    item_id = created.json()["id"]

    conflict = await client.delete(f"/api/items/{item_id}?rev=999", headers=auth)
    assert conflict.status_code == 409


async def test_cannot_touch_other_users_data(client: AsyncClient, auth: dict) -> None:
    created = await client.post("/api/items", json=item_payload(), headers=auth)
    item_id = created.json()["id"]

    other = await client.post(
        "/api/auth/register",
        json={
            "email": f"other-{uuid.uuid4().hex[:8]}@example.com",
            "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1},
            "authHash": b64(32),
            "wrappedDek": b64(48),
            "dekNonce": b64(12),
        },
    )
    other_auth = {"Authorization": f"Bearer {other.json()['accessToken']}"}

    response = await client.patch(
        f"/api/items/{item_id}",
        json={"ciphertext": b64(32), "nonce": b64(12), "rev": 1},
        headers=other_auth,
    )
    assert response.status_code == 404


# ============================================================
# 导入策略
# ============================================================


async def test_import_skip_strategy(client: AsyncClient, auth: dict) -> None:
    existing = folder_payload()
    await client.post("/api/folders", json=existing, headers=auth)

    response = await client.post(
        "/api/vault/import",
        json={"folders": [existing, folder_payload()], "items": [item_payload()], "strategy": "skip"},
        headers=auth,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == {"folders": 1, "items": 1}
    assert body["skipped"] == 1

    vault = (await client.get("/api/vault", headers=auth)).json()
    assert len(vault["folders"]) == 2
    assert len(vault["items"]) == 1


async def test_import_overwrite_strategy(client: AsyncClient, auth: dict) -> None:
    existing = folder_payload()
    await client.post("/api/folders", json=existing, headers=auth)

    replacement = dict(existing)
    replacement["ciphertext"] = b64(48)
    response = await client.post(
        "/api/vault/import",
        json={"folders": [replacement], "items": [], "strategy": "overwrite"},
        headers=auth,
    )
    assert response.json()["imported"]["folders"] == 1

    vault = (await client.get("/api/vault", headers=auth)).json()
    assert len(vault["folders"]) == 1
    assert vault["folders"][0]["ciphertext"] == replacement["ciphertext"]


async def test_import_duplicate_strategy(client: AsyncClient, auth: dict) -> None:
    existing = folder_payload()
    await client.post("/api/folders", json=existing, headers=auth)

    response = await client.post(
        "/api/vault/import",
        json={"folders": [existing], "items": [], "strategy": "duplicate"},
        headers=auth,
    )
    assert response.json()["imported"]["folders"] == 1

    vault = (await client.get("/api/vault", headers=auth)).json()
    assert len(vault["folders"]) == 2
    ids = {f["id"] for f in vault["folders"]}
    assert existing["id"] in ids


# ============================================================
# 设置
# ============================================================


async def test_settings_roundtrip(client: AsyncClient, auth: dict) -> None:
    empty = await client.get("/api/settings", headers=auth)
    assert empty.status_code == 200
    assert empty.json()["ciphertext"] is None

    cipher = b64(120)
    nonce = b64(12)
    put = await client.put(
        "/api/settings", json={"ciphertext": cipher, "nonce": nonce}, headers=auth
    )
    assert put.status_code == 200

    got = (await client.get("/api/settings", headers=auth)).json()
    assert got["ciphertext"] == cipher
    assert got["nonce"] == nonce
    assert got["updatedAt"]
