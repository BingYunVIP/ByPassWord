"""Security regressions against real local HTTP and SMTP protocol endpoints.

All accounts, keys and mail are synthetic. Run in the documented network/mount
sandbox; the SMTP peer is an in-process loopback sink, never a real provider.
"""

import asyncio
import base64
from email import policy
from email.parser import BytesParser
import os
import re
import socket
import time

import httpx
import pyotp
import pytest
from sqlalchemy import func, select
import uvicorn

from app.core.config import settings
from app.core.db import SessionLocal
from app.main import app
from app.models import AuthChallenge, InstallationOwner, User


def b64(length=32):
    return base64.b64encode(os.urandom(length)).decode()


def material(email="owner@example.com"):
    return {
        "email": email, "authHash": b64(),
        "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 8192, "time": 1, "parallel": 1},
        "wrappedDek": b64(48), "dekNonce": b64(12),
        "recoveryWrappedDek": b64(48), "recoveryDekNonce": b64(12), "recoveryAuthHash": b64(),
    }


def authorization(body):
    return {"Authorization": "Bearer " + body["accessToken"]}


@pytest.fixture
async def http_client():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off",
                            access_log=False, log_level="error", proxy_headers=False)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.01)
        assert server.started
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                                     follow_redirects=False, timeout=10) as client:
            yield client
    finally:
        server.should_exit = True
        await task
        sock.close()


@pytest.fixture
async def smtp_sink(monkeypatch):
    received = []

    async def connection(reader, writer):
        writer.write(b"220 synthetic-audit ESMTP\r\n")
        await writer.drain()
        data = None
        try:
            while line := await reader.readline():
                upper = line.upper()
                if data is not None:
                    if line == b".\r\n":
                        parsed = BytesParser(policy=policy.default).parsebytes(b"".join(data))
                        body = parsed.get_body(preferencelist=("plain",))
                        received.append(body.get_content() if body else "")
                        data = None
                        writer.write(b"250 accepted\r\n")
                    else:
                        data.append(line)
                        continue
                elif upper.startswith(b"EHLO"):
                    writer.write(b"250-synthetic-audit\r\n250 AUTH PLAIN\r\n")
                elif upper.startswith(b"AUTH PLAIN"):
                    writer.write(b"235 accepted\r\n")
                elif upper.startswith((b"MAIL", b"RCPT")):
                    writer.write(b"250 accepted\r\n")
                elif upper.startswith(b"DATA"):
                    data = []
                    writer.write(b"354 send\r\n")
                elif upper.startswith(b"QUIT"):
                    writer.write(b"221 bye\r\n")
                    await writer.drain()
                    break
                else:
                    writer.write(b"250 accepted\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(connection, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    for name, value in {
        "smtp_host": "127.0.0.1", "smtp_port": port, "smtp_secure": False,
        "smtp_user": "synthetic-sender@example.com", "smtp_pass": b64(),
        "smtp_from": "synthetic-sender@example.com", "smtp_allow_private_hosts": True,
        "smtp_allow_insecure_test": True,
    }.items():
        monkeypatch.setattr(settings, name, value)
    try:
        yield received
    finally:
        server.close()
        await server.wait_closed()


async def signup(client, payload=None):
    payload = payload or material()
    response = await client.post("/api/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return payload, response.json()


async def reset_grant(client, email, messages):
    result = await client.post("/api/auth/forgot", json={"email": email})
    assert result.status_code == 202
    code = next(re.search(r"验证码：(\d{6})", text).group(1)
                for text in reversed(messages) if re.search(r"验证码：(\d{6})", text))
    return await client.post("/api/auth/forgot/verify", json={"email": email, "code": code})


async def test_http_refresh_race_and_immediate_logout(http_client):
    _, body = await signup(http_client)
    access = authorization(body)
    cookie = http_client.cookies.get("bypw_refresh")
    requests = await asyncio.gather(*[
        http_client.post("/api/auth/refresh", headers={"Cookie": "bypw_refresh=" + cookie})
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in requests) == [200, 401]
    assert (await http_client.get("/api/auth/me", headers=access)).status_code == 200
    assert (await http_client.post("/api/auth/logout")).status_code == 200
    assert (await http_client.get("/api/auth/me", headers=access)).status_code == 401


async def test_http_reset_needs_proof_is_single_use_and_revokes_access(http_client, smtp_sink):
    payload, body = await signup(http_client)
    cookie = http_client.cookies.get("bypw_refresh")
    grant = await reset_grant(http_client, payload["email"], smtp_sink)
    assert grant.status_code == 200
    request = {"resetToken": grant.json()["resetToken"], "newKdf": payload["kdf"],
               "newAuthHash": b64(), "wrappedDek": b64(48), "dekNonce": b64(12)}
    assert (await http_client.post("/api/auth/reset", json=request)).status_code == 400
    assert (await http_client.post("/api/auth/reset", json={**request, "recoveryAuthHash": b64()})).status_code == 401
    request["recoveryAuthHash"] = payload["recoveryAuthHash"]
    raced = await asyncio.gather(*[http_client.post("/api/auth/reset", json=request) for _ in range(2)])
    assert sorted(r.status_code for r in raced) == [200, 401]
    assert (await http_client.get("/api/auth/me", headers=authorization(body))).status_code == 401
    stale = await http_client.post("/api/auth/refresh", headers={"Cookie": "bypw_refresh=" + cookie})
    assert stale.status_code == 401
    assert (await http_client.post("/api/auth/login", json={"email": payload["email"], "authHash": payload["authHash"]})).status_code == 401
    assert (await http_client.post("/api/auth/login", json={"email": payload["email"], "authHash": request["newAuthHash"]})).status_code == 200


async def test_http_legacy_recovery_upgrade_preserves_current_session(http_client, smtp_sink):
    payload = material()
    payload.pop("recoveryAuthHash")
    _, body = await signup(http_client, payload)
    headers = authorization(body)
    profile = await http_client.get("/api/auth/me", headers=headers)
    assert profile.json()["recoveryConfigured"] is False
    grant = await reset_grant(http_client, payload["email"], smtp_sink)
    assert grant.status_code == 403
    assert grant.json()["error"]["code"] == "recovery_not_configured"
    upgrade = {"authHash": payload["authHash"], "recoveryAuthHash": b64(),
               "recoveryWrappedDek": b64(48), "recoveryDekNonce": b64(12)}
    wrong = await http_client.put("/api/auth/recovery", headers=headers, json={**upgrade, "authHash": b64()})
    assert wrong.status_code == 401
    success = await http_client.put("/api/auth/recovery", headers=headers, json=upgrade)
    assert success.status_code == 200, success.text
    me = await http_client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["recoveryConfigured"] is True
    grant = await reset_grant(http_client, payload["email"], smtp_sink)
    assert grant.status_code == 200


async def setup_2fa(client):
    payload, body = await signup(client)
    headers = authorization(body)
    setup = await client.post("/api/auth/2fa/setup", headers=headers)
    secret = setup.json()["secret"]
    enabled = await client.post("/api/auth/2fa/enable", headers=headers,
                                json={"code": pyotp.TOTP(secret).now()})
    assert enabled.status_code == 200, enabled.text
    return payload, body, secret, enabled.json()["recoveryCodes"]


async def challenge(client, payload):
    result = await client.post("/api/auth/login", json={"email": payload["email"], "authHash": payload["authHash"]})
    assert result.status_code == 200
    return result.json()["challenge"]


async def test_http_2fa_challenge_and_code_replay_rejected(http_client):
    payload, body, secret, codes = await setup_2fa(http_client)
    current = pyotp.TOTP(secret).at(time.time() + 30)
    duplicate = await http_client.post("/api/auth/2fa/enable", headers=authorization(body), json={"code": current})
    assert duplicate.status_code == 409
    assert (await http_client.get("/api/auth/2fa/recovery-codes", headers=authorization(body))).json()["remaining"] == 10
    token = await challenge(http_client, payload)
    first = await http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": current})
    assert first.status_code == 200
    assert (await http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": current})).status_code == 401
    token = await challenge(http_client, payload)
    assert (await http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": current})).status_code == 401
    token = await challenge(http_client, payload)
    requests = await asyncio.gather(*[
        http_client.post("/api/auth/2fa/verify-recovery", json={"challenge": token, "recoveryCode": codes[0]})
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in requests) == [200, 401]


async def test_http_challenge_failure_count_persisted(http_client):
    payload, _, secret, _ = await setup_2fa(http_client)
    token = await challenge(http_client, payload)
    wrong = "000000" if not pyotp.TOTP(secret).verify("000000", valid_window=1) else "999999"
    for _ in range(5):
        assert (await http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": wrong})).status_code == 401
    correct = await http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": pyotp.TOTP(secret).now()})
    assert correct.status_code == 401
    async with SessionLocal() as session:
        rows = list((await session.scalars(select(AuthChallenge))).all())
    assert len(rows) == 1 and rows[0].attempts == 5 and rows[0].consumed_at is not None


async def test_http_single_owner_claim_and_registration_policy(http_client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration_after_first", False)
    status = await http_client.get("/api/auth/registration-status")
    assert status.json() == {"initialized": False, "allowed": True}
    requests = await asyncio.gather(*[
        http_client.post("/api/auth/register", json=material(f"owner-{i}@example.com")) for i in range(2)
    ])
    assert sum(r.status_code == 201 for r in requests) == 1
    assert all(r.status_code in {201, 403, 409} for r in requests)
    status = await http_client.get("/api/auth/registration-status")
    assert status.json() == {"initialized": True, "allowed": False}
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        assert await session.scalar(select(func.count()).select_from(InstallationOwner)) == 1


async def test_http_prelogin_stable_unknown_salt_and_untrusted_forwarding(http_client, monkeypatch):
    payload, body = await signup(http_client)
    samples = [(await http_client.post("/api/auth/prelogin", json={"email": "absent@example.com"})).json() for _ in range(2)]
    assert samples[0] == samples[1]
    monkeypatch.setattr(settings, "trusted_proxy_ips", "")
    logged = await http_client.post("/api/auth/login", headers={"X-Forwarded-For": "203.0.113.77"},
                                    json={"email": payload["email"], "authHash": payload["authHash"]})
    assert logged.status_code == 200
    logs = await http_client.get("/api/audit", headers=authorization(body))
    assert all(row["ip"] != "203.0.113.77" for row in logs.json()["items"])


async def test_http_mail_code_is_atomically_consumed(http_client, smtp_sink):
    payload, _ = await signup(http_client)
    assert (await http_client.post("/api/auth/forgot", json={"email": payload["email"]})).status_code == 202
    code = next(re.search(r"验证码：(\d{6})", text).group(1)
                for text in reversed(smtp_sink) if re.search(r"验证码：(\d{6})", text))
    requests = await asyncio.gather(*[
        http_client.post("/api/auth/forgot/verify", json={"email": payload["email"], "code": code})
        for _ in range(2)
    ])
    assert sorted(r.status_code for r in requests) == [200, 401]


async def test_http_password_lock_and_trusted_proxy_chain(http_client, monkeypatch):
    payload, body = await signup(http_client)
    monkeypatch.setattr(settings, "trusted_proxy_ips", "127.0.0.1")
    result = await http_client.post("/api/auth/login",
                                    headers={"X-Forwarded-For": "203.0.113.77, 198.51.100.42"},
                                    json={"email": payload["email"], "authHash": payload["authHash"]})
    assert result.status_code == 200
    logs = await http_client.get("/api/audit", headers=authorization(body))
    assert any(row["action"] == "login_success" and row["ip"] == "198.51.100.42"
               for row in logs.json()["items"])
    assert all(row["ip"] != "203.0.113.77" for row in logs.json()["items"])
    for _ in range(10):
        response = await http_client.post("/api/auth/login", json={"email": payload["email"], "authHash": b64()})
        assert response.status_code == 401
    assert (await http_client.post("/api/auth/login", json={"email": payload["email"], "authHash": payload["authHash"]})).status_code == 423


@pytest.mark.parametrize("operation", ["/api/auth/2fa/recovery-codes/regenerate", "/api/auth/recovery"])
async def test_http_totp_is_consumed_across_sensitive_operations(http_client, operation):
    payload, body, secret, _ = await setup_2fa(http_client)
    headers = authorization(body)
    already_used = pyotp.TOTP(secret).now()
    # The code used to enable 2FA cannot authorize another sensitive action.
    refused = await http_client.post("/api/auth/2fa/disable", headers=headers,
                                     json={"authHash": payload["authHash"], "code": already_used})
    assert refused.status_code == 401
    code = pyotp.TOTP(secret).at(time.time() + 30)
    request = {"authHash": payload["authHash"], "code": code}
    if operation.endswith("/recovery"):
        request.update(recoveryAuthHash=b64(), recoveryWrappedDek=b64(48), recoveryDekNonce=b64(12))
        accepted = await http_client.put(operation, headers=headers, json=request)
    else:
        accepted = await http_client.post(operation, headers=headers, json=request)
    assert accepted.status_code == 200, accepted.text
    replayed = await http_client.post("/api/auth/2fa/disable", headers=headers,
                                      json={"authHash": payload["authHash"], "code": code})
    assert replayed.status_code == 401, replayed.text
    assert (await http_client.get("/api/auth/me", headers=headers)).json()["twoFactorEnabled"] is True


async def test_http_two_challenges_cannot_race_same_totp(http_client):
    payload, _, secret, _ = await setup_2fa(http_client)
    tokens = [await challenge(http_client, payload) for _ in range(2)]
    code = pyotp.TOTP(secret).at(time.time() + 30)
    requests = await asyncio.gather(*[
        http_client.post("/api/auth/2fa/verify", json={"challenge": token, "code": code})
        for token in tokens
    ])
    assert sorted(r.status_code for r in requests) == [200, 401]


async def test_http_recovery_proof_attempt_limit_persists(http_client, smtp_sink):
    payload, _ = await signup(http_client)
    grant = await reset_grant(http_client, payload["email"], smtp_sink)
    request = {"resetToken": grant.json()["resetToken"], "newKdf": payload["kdf"],
               "newAuthHash": b64(), "wrappedDek": b64(48), "dekNonce": b64(12),
               "recoveryAuthHash": b64()}
    for _ in range(5):
        refused = await http_client.post("/api/auth/reset", json=request)
        assert refused.status_code == 401
    request["recoveryAuthHash"] = payload["recoveryAuthHash"]
    assert (await http_client.post("/api/auth/reset", json=request)).status_code == 401


async def test_http_logout_old_rotated_cookie_revokes_entire_session(http_client):
    _, body = await signup(http_client)
    old_cookie = http_client.cookies.get("bypw_refresh")
    refreshed = await http_client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert (await http_client.post("/api/auth/logout", headers={"Cookie": "bypw_refresh=" + old_cookie})).status_code == 200
    for issued in [body, refreshed.json()]:
        assert (await http_client.get("/api/auth/me", headers=authorization(issued))).status_code == 401
