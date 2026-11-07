"""验证连续登录失败与备份事件会触发（不发真实邮件）。

用法：.venv/bin/python scripts/smoke_burst_backup.py http://127.0.0.1:8010 ./ev.db
"""

import base64
import json
import os
import secrets as pysecrets
import sqlite3
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
DB = sys.argv[2] if len(sys.argv) > 2 else "./ev.db"
ok_count = 0
fail_count = 0


def check(name, cond, extra=""):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"PASS | {name}" + (f" | {extra}" if extra else ""))
    else:
        fail_count += 1
        print(f"FAIL | {name}" + (f" | {extra}" if extra else ""))


def b64(n=32):
    return base64.b64encode(pysecrets.token_bytes(n)).decode()


def read_secret(user_id: str, key: str):
    """用应用层解密读取 user_secrets（value_enc 是密文）。"""
    import asyncio

    from app.core.db import SessionLocal
    from app.services import secrets as secrets_svc

    async def _run():
        async with SessionLocal() as session:
            return await secrets_svc.get_secret(session, user_id, key)

    return asyncio.run(_run())


with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
    email = f"burst-{os.urandom(4).hex()}@example.com"
    password_hash = b64()
    reg = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 8192, "time": 1, "parallel": 1},
            "authHash": password_hash,
            "wrappedDek": b64(),
            "dekNonce": b64(12),
        },
    )
    check("注册", reg.status_code in (200, 201), str(reg.status_code))
    token = reg.json()["accessToken"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["id"]

    # 3 次错误密码
    for i in range(3):
        client.post(
            "/api/auth/login",
            json={"email": email, "authHash": b64()},
        )

    raw = read_secret(user_id, "login_fail_window")
    check("失败窗口已写入", raw is not None)
    check("3 次失败后窗口被清空（说明 burst 已触发）", raw == "[]", str(raw)[:20])

    # 手动快照
    snap = client.post("/api/backup/snapshot", headers={"Authorization": f"Bearer {token}"})
    check("手动快照成功", snap.status_code == 200, str(snap.status_code))
    check("返回快照 id", bool(snap.json().get("id")))

print(f"\n合计 {ok_count + fail_count} 项，失败 {fail_count} 项")
sys.exit(1 if fail_count else 0)
