"""安全事件与邮件模板接口冒烟。

用法：.venv/bin/python scripts/smoke_mail_events.py http://127.0.0.1:8010
"""

import base64
import os
import secrets as pysecrets
import sys

import httpx

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
    email = f"events-{os.urandom(4).hex()}@example.com"
    reg = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "kdf": {
                "algo": "argon2id",
                "salt": b64(16),
                "memoryKib": 8192,
                "time": 1,
                "parallel": 1,
            },
            "authHash": b64(),
            "wrappedDek": b64(),
            "dekNonce": b64(12),
        },
    )
    check("注册成功", reg.status_code in (200, 201), str(reg.status_code))
    token = reg.json().get("accessToken")
    h = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/settings/mail/events", headers=h)
    data = r.json()
    events = data.get("events", [])
    check("事件列表返回", r.status_code == 200 and len(events) == 9, f"{len(events)} 个")
    labels = [e["label"] for e in events]
    check(
        "含异常登录相关事件",
        "新设备登录" in labels and "登录 IP 变化" in labels and "连续登录失败" in labels,
        ", ".join(labels[:4]),
    )
    check("默认开启项 > 0", any(e["enabled"] for e in events))

    # 关闭「备份完成」
    payload = {e["key"]: e["enabled"] for e in events}
    payload["backup_created"] = False
    r = client.put("/api/settings/mail/events", headers=h, json={"events": payload})
    check("保存开关", r.status_code == 200, str(r.status_code))
    r = client.get("/api/settings/mail/events", headers=h)
    after = {e["key"]: e["enabled"] for e in r.json()["events"]}
    check("开关已持久化", after.get("backup_created") is False)

    # 模板
    r = client.get("/api/settings/mail/templates", headers=h)
    tpls = r.json().get("templates", [])
    check("模板列表返回", r.status_code == 200 and len(tpls) == 9, f"{len(tpls)} 个")
    first = tpls[0]
    check("模板含默认值", bool(first.get("defaultSubject")) and bool(first.get("defaultBody")))

    new_subject = "【密码库】自定义主题"
    new_body = "自定义正文 {time} {ip}"
    r = client.put(
        f"/api/settings/mail/templates/{first['key']}",
        headers=h,
        json={"subject": new_subject, "body": new_body},
    )
    check("保存模板", r.status_code == 200, str(r.status_code))

    r = client.get("/api/settings/mail/templates", headers=h)
    saved = next(t for t in r.json()["templates"] if t["key"] == first["key"])
    check("模板已持久化", saved["subject"] == new_subject and saved["body"] == new_body)

    r = client.post(f"/api/settings/mail/templates/{first['key']}/reset", headers=h)
    check("重置模板", r.status_code == 200, str(r.status_code))
    r = client.get("/api/settings/mail/templates", headers=h)
    back = next(t for t in r.json()["templates"] if t["key"] == first["key"])
    check("重置后回到默认", back["subject"] == first["defaultSubject"])

    r = client.put(
        "/api/settings/mail/templates/not_exist",
        headers=h,
        json={"subject": "x", "body": "y"},
    )
    check("未知事件返回 404", r.status_code == 404, str(r.status_code))

print(f"\n合计 {ok_count + fail_count} 项，失败 {fail_count} 项")
sys.exit(1 if fail_count else 0)
