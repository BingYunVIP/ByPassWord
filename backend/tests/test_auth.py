"""认证接口测试：注册、登录、刷新轮换、2FA、锁定、找回密码。"""

import base64
import os
import re
import time

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services import auth_service

BASE = "http://test"
PASSWORD_KEY = base64.b64encode(os.urandom(32)).decode()
RECOVERY_AUTH_KEY = base64.b64encode(os.urandom(32)).decode()


def b64(n: int) -> str:
    return base64.b64encode(os.urandom(n)).decode()


def register_payload(email: str, auth_hash: str | None = None) -> dict:
    return {
        "email": email,
        "kdf": {
            "algo": "argon2id",
            "salt": b64(16),
            "memoryKib": 65536,
            "time": 3,
            "parallel": 1,
        },
        "authHash": auth_hash or PASSWORD_KEY,
        "wrappedDek": b64(48),
        "dekNonce": b64(12),
        "recoveryWrappedDek": b64(48),
        "recoveryDekNonce": b64(12),
        "recoveryAuthHash": RECOVERY_AUTH_KEY,
    }


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE) as c:
        yield c


async def do_register(client: AsyncClient, email: str) -> dict:
    response = await client.post("/api/auth/register", json=register_payload(email))
    assert response.status_code == 201, response.text
    return response.json()


# ============================================================
# 注册 / 预登录
# ============================================================


async def test_register_returns_tokens(client: AsyncClient) -> None:
    body = await do_register(client, "reg@example.com")
    assert body["accessToken"]
    assert body["expiresIn"] > 0
    assert body["wrappedDek"]
    assert client.cookies.get("bypw_refresh")


async def test_register_duplicate_email_conflict(client: AsyncClient) -> None:
    await do_register(client, "dup@example.com")
    response = await client.post("/api/auth/register", json=register_payload("dup@example.com"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_exists"


async def test_register_rejects_bad_base64(client: AsyncClient) -> None:
    payload = register_payload("bad@example.com")
    payload["wrappedDek"] = "not-base64!!"
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


async def test_prelogin_hides_unknown_email(client: AsyncClient) -> None:
    await do_register(client, "known@example.com")

    known = await client.post("/api/auth/prelogin", json={"email": "known@example.com"})
    unknown = await client.post("/api/auth/prelogin", json={"email": "nobody@example.com"})

    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json()["kdf"]["salt"] != unknown.json()["kdf"]["salt"]
    assert unknown.json()["kdf"]["salt"]


# ============================================================
# 登录 / 锁定
# ============================================================


async def test_login_success_and_wrong_password(client: AsyncClient) -> None:
    await do_register(client, "login@example.com")

    ok = await client.post(
        "/api/auth/login", json={"email": "login@example.com", "authHash": PASSWORD_KEY}
    )
    assert ok.status_code == 200
    assert ok.json()["accessToken"]

    bad = await client.post(
        "/api/auth/login", json={"email": "login@example.com", "authHash": b64(32)}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"


async def test_account_locks_after_ten_failures(client: AsyncClient) -> None:
    await do_register(client, "lock@example.com")

    for _ in range(10):
        response = await client.post(
            "/api/auth/login", json={"email": "lock@example.com", "authHash": b64(32)}
        )
        assert response.status_code == 401

    locked = await client.post(
        "/api/auth/login", json={"email": "lock@example.com", "authHash": PASSWORD_KEY}
    )
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "account_locked"


# ============================================================
# 刷新轮换 / 登出
# ============================================================


async def test_refresh_rotates_token(client: AsyncClient) -> None:
    await do_register(client, "refresh@example.com")
    first_cookie = client.cookies.get("bypw_refresh")
    assert first_cookie

    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["accessToken"]
    second_cookie = client.cookies.get("bypw_refresh")
    assert second_cookie and second_cookie != first_cookie

    # 旧 token 已作废：用带旧 cookie 的独立客户端再刷新应 401
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, cookies={"bypw_refresh": first_cookie}
    ) as stale_client:
        stale = await stale_client.post("/api/auth/refresh")
    assert stale.status_code == 401


async def test_logout_revokes_refresh(client: AsyncClient) -> None:
    await do_register(client, "logout@example.com")
    cookie = client.cookies.get("bypw_refresh")

    assert (await client.post("/api/auth/logout")).status_code == 200

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, cookies={"bypw_refresh": cookie}
    ) as stale_client:
        after = await stale_client.post("/api/auth/refresh")
    assert after.status_code == 401


# ============================================================
# 账号 2FA
# ============================================================


async def test_two_factor_full_flow(client: AsyncClient) -> None:
    body = await do_register(client, "tfa@example.com")
    token = body["accessToken"]

    setup = await client.post("/api/auth/2fa/setup", headers=auth_header(token))
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["otpauthUrl"].startswith("otpauth://totp/")

    enable = await client.post(
        "/api/auth/2fa/enable",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_header(token),
    )
    assert enable.status_code == 200
    codes = enable.json()["recoveryCodes"]
    assert len(codes) == 10

    login = await client.post(
        "/api/auth/login", json={"email": "tfa@example.com", "authHash": PASSWORD_KEY}
    )
    assert login.status_code == 200
    assert login.json()["requires2fa"] is True
    challenge = login.json()["challenge"]

    verified = await client.post(
        "/api/auth/2fa/verify",
        json={"challenge": challenge, "code": pyotp.TOTP(secret).at(time.time() + 30)},
    )
    assert verified.status_code == 200
    assert verified.json()["accessToken"]

    # 恢复码登录
    login2 = await client.post(
        "/api/auth/login", json={"email": "tfa@example.com", "authHash": PASSWORD_KEY}
    )
    challenge2 = login2.json()["challenge"]
    recovery = await client.post(
        "/api/auth/2fa/verify-recovery",
        json={"challenge": challenge2, "recoveryCode": codes[0]},
    )
    assert recovery.status_code == 200

    # 同一恢复码不能重复使用
    login3 = await client.post(
        "/api/auth/login", json={"email": "tfa@example.com", "authHash": PASSWORD_KEY}
    )
    reused = await client.post(
        "/api/auth/2fa/verify-recovery",
        json={"challenge": login3.json()["challenge"], "recoveryCode": codes[0]},
    )
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "invalid_recovery_code"


async def test_two_factor_wrong_code_rejected(client: AsyncClient) -> None:
    body = await do_register(client, "tfa2@example.com")
    token = body["accessToken"]
    setup = await client.post("/api/auth/2fa/setup", headers=auth_header(token))
    secret = setup.json()["secret"]
    await client.post(
        "/api/auth/2fa/enable",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_header(token),
    )

    login = await client.post(
        "/api/auth/login", json={"email": "tfa2@example.com", "authHash": PASSWORD_KEY}
    )
    challenge = login.json()["challenge"]
    bad = await client.post(
        "/api/auth/2fa/verify", json={"challenge": challenge, "code": "000000"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_code"


# ============================================================
# 忘记主密码
# ============================================================


async def test_forgot_password_full_flow(client: AsyncClient, monkeypatch) -> None:
    await do_register(client, "forgot@example.com")

    sent: list[tuple[str, str]] = []

    async def fake_send(_session, _user, subject: str, text: str) -> bool:
        sent.append((subject, text))
        return True

    monkeypatch.setattr(auth_service.mailer, "send_to_user", fake_send)

    forgot = await client.post("/api/auth/forgot", json={"email": "forgot@example.com"})
    assert forgot.status_code == 202
    assert sent, "应当发送验证码邮件"

    code = re.search(r"验证码：(\d{6})", sent[0][1]).group(1)
    verify = await client.post(
        "/api/auth/forgot/verify", json={"email": "forgot@example.com", "code": code}
    )
    assert verify.status_code == 200
    reset_token = verify.json()["resetToken"]

    new_auth = b64(32)
    payload = {
        "resetToken": reset_token,
        "recoveryAuthHash": RECOVERY_AUTH_KEY,
        "newKdf": {
            "algo": "argon2id",
            "salt": b64(16),
            "memoryKib": 65536,
            "time": 3,
            "parallel": 1,
        },
        "newAuthHash": new_auth,
        "wrappedDek": b64(48),
        "dekNonce": b64(12),
    }
    reset = await client.post("/api/auth/reset", json=payload)
    assert reset.status_code == 200

    old_login = await client.post(
        "/api/auth/login", json={"email": "forgot@example.com", "authHash": PASSWORD_KEY}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "forgot@example.com", "authHash": new_auth}
    )
    assert new_login.status_code == 200


async def test_forgot_unknown_email_still_202(client: AsyncClient) -> None:
    response = await client.post("/api/auth/forgot", json={"email": "ghost@example.com"})
    assert response.status_code == 202


# ============================================================
# 修改主密码 / 关闭 2FA / 恢复码管理
# ============================================================


def new_kdf() -> dict:
    return {
        "algo": "argon2id",
        "salt": b64(16),
        "memoryKib": 65536,
        "time": 3,
        "parallel": 1,
    }


async def test_change_password_invalidates_old(client: AsyncClient) -> None:
    body = await do_register(client, "chg@example.com")
    new_auth = b64(32)

    changed = await client.post(
        "/api/auth/change-password",
        json={
            "oldAuthHash": PASSWORD_KEY,
            "newAuthHash": new_auth,
            "newKdf": new_kdf(),
            "wrappedDek": b64(48),
            "dekNonce": b64(12),
        },
        headers=auth_header(body["accessToken"]),
    )
    assert changed.status_code == 200, changed.text

    old_login = await client.post(
        "/api/auth/login", json={"email": "chg@example.com", "authHash": PASSWORD_KEY}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/auth/login", json={"email": "chg@example.com", "authHash": new_auth}
    )
    assert new_login.status_code == 200


async def test_change_password_wrong_old_rejected(client: AsyncClient) -> None:
    body = await do_register(client, "chg2@example.com")
    response = await client.post(
        "/api/auth/change-password",
        json={
            "oldAuthHash": b64(32),
            "newAuthHash": b64(32),
            "newKdf": new_kdf(),
            "wrappedDek": b64(48),
            "dekNonce": b64(12),
        },
        headers=auth_header(body["accessToken"]),
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_disable_two_factor(client: AsyncClient) -> None:
    body = await do_register(client, "disable2fa@example.com")
    token = body["accessToken"]

    setup = await client.post("/api/auth/2fa/setup", headers=auth_header(token))
    secret = setup.json()["secret"]
    await client.post(
        "/api/auth/2fa/enable",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_header(token),
    )

    disabled = await client.post(
        "/api/auth/2fa/disable",
        json={"authHash": PASSWORD_KEY, "code": pyotp.TOTP(secret).at(time.time() + 30)},
        headers=auth_header(token),
    )
    assert disabled.status_code == 200, disabled.text

    login = await client.post(
        "/api/auth/login", json={"email": "disable2fa@example.com", "authHash": PASSWORD_KEY}
    )
    assert login.status_code == 200
    assert "accessToken" in login.json()


async def test_recovery_codes_count_and_regenerate(client: AsyncClient) -> None:
    body = await do_register(client, "codes@example.com")
    token = body["accessToken"]
    setup = await client.post("/api/auth/2fa/setup", headers=auth_header(token))
    secret = setup.json()["secret"]
    first = await client.post(
        "/api/auth/2fa/enable",
        json={"code": pyotp.TOTP(secret).now()},
        headers=auth_header(token),
    )
    assert len(first.json()["recoveryCodes"]) == 10

    remaining = await client.get("/api/auth/2fa/recovery-codes", headers=auth_header(token))
    assert remaining.json()["remaining"] == 10

    regenerated = await client.post(
        "/api/auth/2fa/recovery-codes/regenerate",
        json={"authHash": PASSWORD_KEY, "code": pyotp.TOTP(secret).at(time.time() + 30)},
        headers=auth_header(token),
    )
    assert regenerated.status_code == 200
    assert len(regenerated.json()["recoveryCodes"]) == 10
    assert set(regenerated.json()["recoveryCodes"]) != set(first.json()["recoveryCodes"])

    # 旧恢复码作废
    login = await client.post(
        "/api/auth/login", json={"email": "codes@example.com", "authHash": PASSWORD_KEY}
    )
    stale = await client.post(
        "/api/auth/2fa/verify-recovery",
        json={"challenge": login.json()["challenge"], "recoveryCode": first.json()["recoveryCodes"][0]},
    )
    assert stale.status_code == 401
