"""真实 HTTP 冒烟：设置中心（邮箱/备份/审计）。

用法：
    .venv/bin/python scripts/smoke_settings.py [base_url]
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
    email = f"p5-{uuid.uuid4().hex[:8]}@example.com"

    with httpx.Client(base_url=BASE, timeout=30, trust_env=False) as client:
        check("未登录访问审计 401", client.get("/api/audit").status_code == 401)

        reg = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "kdf": {"algo": "argon2id", "salt": b64(16), "memoryKib": 65536, "time": 3, "parallel": 1},
                "authHash": b64(32),
                "wrappedDek": b64(48),
                "dekNonce": b64(12),
                "recoveryWrappedDek": b64(48),
                "recoveryDekNonce": b64(12),
            },
        )
        if reg.status_code != 201:
            check("注册（前置）", False, reg.text[:120])
            return 1
        headers = {"Authorization": f"Bearer {reg.json()['accessToken']}"}

        # 邮箱配置
        default = client.get("/api/settings/mail", headers=headers).json()
        check("默认邮箱配置为 QQ SMTP", default["host"] == "smtp.qq.com" and default["hasPassword"] is False, str(default))

        saved = client.put(
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
            headers=headers,
        )
        check("保存邮箱配置", saved.status_code == 200 and saved.json()["hasPassword"] is True, saved.text[:80])

        after = client.get("/api/settings/mail", headers=headers).json()
        check("授权码不回显", "password" not in after and after["hasPassword"] is True, str(after))
        check("发件人名称已保存", after["fromName"] == "密码库")

        mail_test = client.post("/api/settings/mail/test", headers=headers)
        check("未配置真实 SMTP 时返回 502", mail_test.status_code == 502 and mail_test.json()["error"]["code"] == "mail_failed", mail_test.text[:80])

        # 备份策略与快照
        backup_default = client.get("/api/settings/backup", headers=headers).json()
        check("默认保留 30 天", backup_default["retentionDays"] == 30, str(backup_default))

        client.put("/api/settings/backup", json={"schedule": "weekly-02:00", "retentionDays": 7}, headers=headers)
        backup_after = client.get("/api/settings/backup", headers=headers).json()
        check("备份策略已保存", backup_after["retentionDays"] == 7 and backup_after["schedule"] == "weekly-02:00", str(backup_after))

        snapshot = client.post("/api/backup/snapshot", headers=headers)
        check("创建手动快照", snapshot.status_code == 200 and snapshot.json()["kind"] == "manual", snapshot.text[:80])

        listed = client.get("/api/backup/list", headers=headers).json()
        ids = [item["id"] for item in listed["items"]]
        check("快照出现在列表", snapshot.json()["id"] in ids, f"共 {len(ids)} 个")

        # 审计
        audit = client.get("/api/audit?limit=20", headers=headers).json()
        actions = {item["action"] for item in audit["items"]}
        check("审计含注册与邮箱配置", "register" in actions and "mail_settings_updated" in actions, str(sorted(actions)[:6]))
        check("审计含备份事件", "backup_snapshot" in actions)

    failed = results.count(False)
    print(f"\n合计 {len(results)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
