"""真实 HTTP 冒烟：对运行中的服务跑一遍认证主流程。

用法：
    .venv/bin/python scripts/smoke_auth.py [base_url]

建议用独立数据库与关闭限流的实例：
    RATE_LIMIT_ENABLED=false DATABASE_URL=sqlite+aiosqlite:///./smoke.db \
        .venv/bin/uvicorn app.main:app --port 8010
"""

import base64
import os
import re
import sys
import uuid

import httpx
import pyotp

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

results: list[bool] = []


def b64(n: int) -> str:
    return base64.b64encode(os.urandom(n)).decode()


def check(name: str, condition: bool, extra: str = "") -> None:
    results.append(condition)
    print(f"{'PASS' if condition else 'FAIL'} | {name}" + (f" | {extra}" if extra else ""))


def main() -> int:
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    auth_hash = b64(32)
    kdf = {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1}

    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
        # 1. 健康检查
        health = client.get("/api/health")
        check("健康检查", health.status_code == 200 and health.json()["db"] == "ok", health.text[:80])

        # 2. 注册
        reg = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "kdf": kdf,
                "authHash": auth_hash,
                "wrappedDek": b64(48),
                "dekNonce": b64(12),
                "recoveryWrappedDek": b64(48),
            },
        )
        check("注册", reg.status_code == 201 and "accessToken" in reg.text, reg.text[:100])
        token = reg.json()["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. 当前用户
        me = client.get("/api/auth/me", headers=headers)
        check("获取当前用户", me.status_code == 200 and me.json()["email"] == email, me.text[:100])

        # 4. 预登录
        pre = client.post("/api/auth/prelogin", json={"email": email})
        check("预登录返回 KDF", pre.status_code == 200 and pre.json()["kdf"]["salt"] == kdf["salt"])

        # 5. 登录
        login = client.post("/api/auth/login", json={"email": email, "authHash": auth_hash})
        check("登录", login.status_code == 200 and "accessToken" in login.text, login.text[:100])

        # 6. 错误主密码
        bad = client.post("/api/auth/login", json={"email": email, "authHash": b64(32)})
        check("错误主密码 401", bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials")

        # 7. 刷新
        refresh = client.post("/api/auth/refresh")
        check("刷新令牌", refresh.status_code == 200 and refresh.json()["accessToken"], refresh.text[:80])

        # 8. 2FA 绑定
        setup = client.post("/api/auth/2fa/setup", headers=headers)
        secret = setup.json().get("secret", "")
        check("2FA 生成密钥", setup.status_code == 200 and bool(secret), setup.text[:80])

        enable = client.post(
            "/api/auth/2fa/enable",
            json={"code": pyotp.TOTP(secret).now()},
            headers=headers,
        )
        codes = enable.json().get("recoveryCodes", []) if enable.status_code == 200 else []
        check("2FA 启用并下发 10 个恢复码", len(codes) == 10, enable.text[:80])

        # 9. 2FA 登录
        step1 = client.post("/api/auth/login", json={"email": email, "authHash": auth_hash})
        challenge = step1.json().get("challenge")
        check("登录需要 2FA", step1.json().get("requires2fa") is True, step1.text[:80])

        step2 = client.post(
            "/api/auth/2fa/verify",
            json={"challenge": challenge, "code": pyotp.TOTP(secret).now()},
        )
        check("2FA 校验通过", step2.status_code == 200 and "accessToken" in step2.text, step2.text[:80])

        # 10. 恢复码登录
        step1b = client.post("/api/auth/login", json={"email": email, "authHash": auth_hash})
        rec = client.post(
            "/api/auth/2fa/verify-recovery",
            json={"challenge": step1b.json()["challenge"], "recoveryCode": codes[0]},
        )
        check("恢复码登录", rec.status_code == 200, rec.text[:80])

        # 11. 忘记密码（未配置 SMTP 时仍返回 202）
        forgot = client.post("/api/auth/forgot", json={"email": email})
        check("发送重置验证码 202", forgot.status_code == 202, forgot.text[:80])

        # 12. 登出
        logout = client.post("/api/auth/logout")
        check("登出", logout.status_code == 200)

        # 13. 未登录访问受保护接口
        anon = client.get("/api/auth/me")
        check("未登录 401", anon.status_code == 401)

    failed = results.count(False)
    print(f"\n合计 {len(results)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
