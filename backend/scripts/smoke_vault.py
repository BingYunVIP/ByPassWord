"""真实 HTTP 冒烟：金库同步（拉取/增删改/乐观锁/增量墓碑/导入/设置）。

用法：
    .venv/bin/python scripts/smoke_vault.py [base_url]
"""

import base64
import os
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

results: list[bool] = []


def b64(n: int) -> str:
    return base64.b64encode(os.urandom(n)).decode()


def check(name: str, condition: bool, extra: str = "") -> None:
    results.append(condition)
    print(f"{'PASS' if condition else 'FAIL'} | {name}" + (f" | {extra}" if extra else ""))


def main() -> int:
    email = f"vault-{uuid.uuid4().hex[:8]}@example.com"
    kdf = {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1}

    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
        # 未登录应 401
        check("未登录访问金库 401", client.get("/api/vault").status_code == 401)

        reg = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "kdf": kdf,
                "authHash": b64(32),
                "wrappedDek": b64(48),
                "dekNonce": b64(12),
                "recoveryWrappedDek": b64(48),
            },
        )
        if reg.status_code != 201:
            check("注册（前置）", False, reg.text[:120])
            return 1
        headers = {"Authorization": f"Bearer {reg.json()['accessToken']}"}

        # 空库
        empty = client.get("/api/vault", headers=headers).json()
        check("空金库 rev=0 且无数据", empty["rev"] == 0 and not empty["folders"] and not empty["items"])

        # 新建文件夹 / 条目
        folder_id = str(uuid.uuid4())
        folder_payload = {"id": folder_id, "ciphertext": b64(80), "nonce": b64(12), "sortOrder": 0}
        created_folder = client.post("/api/folders", json=folder_payload, headers=headers)
        check("新建文件夹", created_folder.status_code == 201 and created_folder.json()["rev"] == 1, created_folder.text[:80])

        item_id = str(uuid.uuid4())
        item_payload = {"id": item_id, "ciphertext": b64(120), "nonce": b64(12)}
        created_item = client.post("/api/items", json=item_payload, headers=headers)
        check("新建条目", created_item.status_code == 201 and created_item.json()["rev"] == 2, created_item.text[:80])

        vault = client.get("/api/vault", headers=headers).json()
        check("全量拉取命中 1 文件夹 + 1 条目", len(vault["folders"]) == 1 and len(vault["items"]) == 1, f"rev={vault['rev']}")
        check("密文原样返回（服务端未解密）", vault["items"][0]["ciphertext"] == item_payload["ciphertext"])

        # 幂等：同 id 同内容重复创建
        again = client.post("/api/folders", json=folder_payload, headers=headers)
        check("重复创建幂等（rev 不变）", again.status_code == 201 and again.json()["rev"] == 1, again.text[:80])

        # 乐观锁
        stale = client.patch(
            f"/api/items/{item_id}",
            json={"ciphertext": b64(120), "nonce": b64(12), "rev": 999},
            headers=headers,
        )
        check("rev 冲突返回 409", stale.status_code == 409 and stale.json()["error"]["code"] == "rev_conflict", stale.text[:100])
        check("409 带上服务端当前 rev", stale.json()["error"]["detail"]["rev"] == 2)

        patched = client.patch(
            f"/api/items/{item_id}",
            json={"ciphertext": b64(120), "nonce": b64(12), "rev": 2},
            headers=headers,
        )
        check("正确 rev 更新成功", patched.status_code == 200 and patched.json()["rev"] == 3, patched.text[:80])

        # 增量拉取
        incremental = client.get("/api/vault?since=2", headers=headers).json()
        check("增量只返回 rev>2 的记录", len(incremental["items"]) == 1 and incremental["items"][0]["rev"] == 3)

        # 软删除 + 墓碑
        deleted = client.delete(f"/api/items/{item_id}?rev=3", headers=headers)
        check("软删除成功", deleted.status_code == 200 and deleted.json()["deletedAt"], deleted.text[:100])

        full_after = client.get("/api/vault", headers=headers).json()
        check("全量不再包含已删除条目", full_after["items"] == [])

        tomb = client.get("/api/vault?since=3", headers=headers).json()
        check("增量下发删除墓碑", len(tomb["items"]) == 1 and tomb["items"][0]["deletedAt"] is not None)

        # 导入三种策略
        existing = {"id": folder_id, "ciphertext": b64(60), "nonce": b64(12), "sortOrder": 0}
        new_folder = {"id": str(uuid.uuid4()), "ciphertext": b64(60), "nonce": b64(12), "sortOrder": 1}

        skip = client.post(
            "/api/vault/import",
            json={"folders": [existing, new_folder], "items": [], "strategy": "skip"},
            headers=headers,
        ).json()
        check("导入 skip：跳过已存在、写入新的", skip["skipped"] == 1 and skip["imported"]["folders"] == 1, str(skip))

        overwrite = client.post(
            "/api/vault/import",
            json={"folders": [existing], "items": [], "strategy": "overwrite"},
            headers=headers,
        ).json()
        check("导入 overwrite：覆盖同 id", overwrite["imported"]["folders"] == 1, str(overwrite))

        duplicate = client.post(
            "/api/vault/import",
            json={"folders": [existing], "items": [], "strategy": "duplicate"},
            headers=headers,
        ).json()
        check("导入 duplicate：作为新记录写入", duplicate["imported"]["folders"] == 1, str(duplicate))

        final_vault = client.get("/api/vault", headers=headers).json()
        # 1 原始 + 1（skip 新增）+ 0（overwrite 覆盖）+ 1（duplicate 复制）= 3
        check("导入后文件夹总数为 3", len(final_vault["folders"]) == 3, f"实际 {len(final_vault['folders'])}")

        # 设置
        before = client.get("/api/settings", headers=headers).json()
        check("设置初始为空", before["ciphertext"] is None)
        cipher, nonce = b64(160), b64(12)
        client.put("/api/settings", json={"ciphertext": cipher, "nonce": nonce}, headers=headers)
        after = client.get("/api/settings", headers=headers).json()
        check("设置写入后可读回", after["ciphertext"] == cipher and after["nonce"] == nonce)

    failed = results.count(False)
    print(f"\n合计 {len(results)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
