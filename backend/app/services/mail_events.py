"""安全事件通知：事件定义、开关、邮件模板。

存储复用 user_secrets（SERVER_SECRET 加密）：
  key = "mail_events"        -> JSON {event_key: bool}
  key = "mail_tpl:<event>"   -> JSON {"subject": str, "body": str}
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from . import secrets

EVENTS_KEY = "mail_events"
TEMPLATE_PREFIX = "mail_tpl:"

# 变量占位符：{time} {ip} {ua} {action} {detail}
EVENTS: list[dict] = [
    {
        "key": "login_new_device",
        "label": "新设备登录",
        "desc": "首次在该设备登录时通知",
        "defaultOn": True,
        "subject": "【密码库】新设备登录提醒",
        "body": "你的密码库在一台新设备上登录。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n如果不是你本人操作，请立即修改主密码。",
    },
    {
        "key": "login_ip_changed",
        "label": "登录 IP 变化",
        "desc": "登录 IP 与上次不同时通知",
        "defaultOn": True,
        "subject": "【密码库】登录 IP 变化提醒",
        "body": "你的密码库从一个新的 IP 登录。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n如果不是你本人操作，请立即修改主密码。",
    },
    {
        "key": "login_recovery_code",
        "label": "恢复码登录",
        "desc": "使用恢复码代替主密码登录时通知",
        "defaultOn": True,
        "subject": "【密码库】恢复码登录提醒",
        "body": "有人使用恢复码登录了你的密码库。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n如果你没有使用恢复码，请立即修改主密码并重新生成恢复码。",
    },
    {
        "key": "login_failed_burst",
        "label": "连续登录失败",
        "desc": "短时间内多次密码错误时通知",
        "defaultOn": True,
        "subject": "【密码库】连续登录失败告警",
        "body": "你的密码库连续出现多次登录失败。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n可能是他人在尝试猜解，建议检查后修改主密码。",
    },
    {
        "key": "account_locked",
        "label": "账号锁定",
        "desc": "失败次数过多触发临时锁定时通知",
        "defaultOn": True,
        "subject": "【密码库】账号已被临时锁定",
        "body": "由于连续登录失败，你的账号已被临时锁定。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n锁定会在设定时间后自动解除。",
    },
    {
        "key": "password_changed",
        "label": "主密码修改",
        "desc": "主密码被修改时通知",
        "defaultOn": True,
        "subject": "【密码库】主密码已修改",
        "body": "你的密码库主密码已被修改。\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n如果不是你本人操作，请立即使用恢复码重置。",
    },
    {
        "key": "two_factor_changed",
        "label": "2FA 变更",
        "desc": "开启或关闭两步验证时通知",
        "defaultOn": True,
        "subject": "【密码库】两步验证状态变更",
        "body": "你的账号两步验证状态发生变化：{detail}\n\n时间：{time}\nIP：{ip}\n设备：{ua}\n\n如果不是你本人操作，请立即修改主密码。",
    },
    {
        "key": "backup_created",
        "label": "备份完成",
        "desc": "自动或手动备份成功后通知（默认关闭）",
        "defaultOn": False,
        "subject": "【密码库】备份已完成",
        "body": "密码库备份已完成。\n\n时间：{time}\n类型：{detail}\n\n请确认备份文件存放在安全位置。",
    },
    {
        "key": "backup_failed",
        "label": "备份失败",
        "desc": "备份任务失败时通知",
        "defaultOn": True,
        "subject": "【密码库】备份失败告警",
        "body": "密码库备份任务执行失败。\n\n时间：{time}\n详情：{detail}\n\n请检查磁盘空间与服务状态。",
    },
]

EVENT_MAP = {e["key"]: e for e in EVENTS}


def default_switches() -> dict[str, bool]:
    return {e["key"]: bool(e["defaultOn"]) for e in EVENTS}


async def load_switches(session: AsyncSession, user_id: str) -> dict[str, bool]:
    raw = await secrets.get_secret(session, user_id, EVENTS_KEY)
    result = default_switches()
    if raw:
        try:
            saved = json.loads(raw)
            if isinstance(saved, dict):
                for key in result:
                    if key in saved:
                        result[key] = bool(saved[key])
        except (ValueError, TypeError):
            pass
    return result


async def save_switches(session: AsyncSession, user_id: str, values: dict[str, bool]) -> dict[str, bool]:
    current = await load_switches(session, user_id)
    for key in current:
        if key in values:
            current[key] = bool(values[key])
    await secrets.set_secret(session, user_id, EVENTS_KEY, json.dumps(current, ensure_ascii=False))
    return current


async def load_templates(session: AsyncSession, user_id: str) -> dict[str, dict]:
    """返回每个事件的最终模板：用户自定义优先，否则用默认值。"""
    out: dict[str, dict] = {}
    for event in EVENTS:
        subject, body = event["subject"], event["body"]
        raw = await secrets.get_secret(session, user_id, TEMPLATE_PREFIX + event["key"])
        if raw:
            try:
                saved = json.loads(raw)
                if isinstance(saved, dict):
                    subject = (saved.get("subject") or subject).strip() or subject
                    body = (saved.get("body") or body).strip() or body
            except (ValueError, TypeError):
                pass
        out[event["key"]] = {"subject": subject, "body": body}
    return out


async def save_template(
    session: AsyncSession, user_id: str, event_key: str, subject: str, body: str
) -> dict:
    if event_key not in EVENT_MAP:
        raise ValueError("unknown_event")
    payload = {"subject": subject.strip(), "body": body.strip()}
    await secrets.set_secret(
        session, user_id, TEMPLATE_PREFIX + event_key, json.dumps(payload, ensure_ascii=False)
    )
    return payload


async def reset_template(session: AsyncSession, user_id: str, event_key: str) -> dict:
    if event_key not in EVENT_MAP:
        raise ValueError("unknown_event")
    # 删除自定义值，回落到默认模板
    await secrets.set_secret(session, user_id, TEMPLATE_PREFIX + event_key, "")
    event = EVENT_MAP[event_key]
    return {"subject": event["subject"], "body": event["body"]}


async def render(
    session: AsyncSession, user_id: str, event_key: str, ctx: dict[str, str]
) -> tuple[str, str] | None:
    """渲染指定事件的邮件；事件未开启或不存在时返回 None。"""
    if event_key not in EVENT_MAP:
        return None
    switches = await load_switches(session, user_id)
    if not switches.get(event_key, False):
        return None

    templates = await load_templates(session, user_id)
    tpl = templates[event_key]
    subject, body = tpl["subject"], tpl["body"]

    values = {
        "time": ctx.get("time", ""),
        "ip": ctx.get("ip", "—"),
        "ua": ctx.get("ua", "—"),
        "action": ctx.get("action", ""),
        "detail": ctx.get("detail", ""),
    }
    for name, value in values.items():
        subject = subject.replace("{" + name + "}", value)
        body = body.replace("{" + name + "}", value)
    return subject, body
