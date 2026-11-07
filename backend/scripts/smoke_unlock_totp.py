"""验证锁定解锁的 2FA 校验接口。

用法：.venv/bin/python scripts/smoke_unlock_totp.py http://127.0.0.1:8010
"""

import base64
import os
import secrets as pysecrets
import sys

import httpx
import pyotp

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
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


with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
    email = f"unlock-{os.urandom(4).hex()}@example.com"
    reg = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 8192, "time": 1, "parallel": 1},
            "authHash": b64(),
            "wrappedDek": b64(),
            "dekNonce": b64(12),
        },
    )
    check("注册", reg.status_code in (200, 201), str(reg.status_code))
    h = {"Authorization": f"Bearer {reg.json()['accessToken']}"}

    # 未开启 2FA 时应当拒绝
    r = client.post("/api/auth/unlock/verify-totp", headers=h, json={"code": "123456"})
    check("未开启 2FA 返回 400", r.status_code == 400, str(r.status_code))

    # 开启 2FA
    setup = client.post("/api/auth/2fa/setup", headers=h)
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    enable = client.post("/api/auth/2fa/enable", headers=h, json={"code": code})
    check("启用 2FA", enable.status_code == 200, str(enable.status_code))

    # 正确码
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/unlock/verify-totp", headers=h, json={"code": code})
    check("正确动态码通过", r.status_code == 200 and r.json().get("ok") is True, str(r.status_code))

    # 错误码
    r = client.post("/api/auth/unlock/verify-totp", headers=h, json={"code": "000000"})
    check("错误动态码返回 401", r.status_code == 401, str(r.status_code))

    # 格式非法
    r = client.post("/api/auth/unlock/verify-totp", headers=h, json={"code": "12"})
    check("非 6 位被拒绝", r.status_code in (400, 422), str(r.status_code))

print(f"\n合计 {ok_count + fail_count} 项，失败 {fail_count} 项")
sys.exit(1 if fail_count else 0)
