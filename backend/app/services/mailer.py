"""邮件服务：QQ 邮箱 SMTP（默认 465/SSL），支持按用户覆盖配置。

发信失败一律不抛异常——通知类邮件不能阻塞登录、改密等主流程。
"""

import logging
import asyncio
import ipaddress
import socket
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import User
from . import secrets

logger = logging.getLogger("bypw.mail")

SECRET_KEYS = {
    "host": "smtp_host",
    "port": "smtp_port",
    "secure": "smtp_secure",
    "user": "smtp_user",
    "password": "smtp_password",
    "from": "smtp_from",
    "fromName": "smtp_from_name",
}


async def resolve_config(session: AsyncSession, user_id: str) -> dict:
    """Select a whole user profile or the owner's whole deployment profile."""
    from ..core.ownership import get_owner_user_id

    values = {name: await secrets.get_secret(session, user_id, key) for name, key in SECRET_KEYS.items()}
    if any(value is not None for value in values.values()):
        return {
            "host": values["host"] or "",
            "port": int(values["port"]) if str(values["port"]).isdigit() else 465,
            "secure": str(values["secure"]).lower() in ("1", "true", "yes"),
            "user": values["user"] or "",
            "password": values["password"] or "",
            "from": values["from"] or values["user"] or "",
            "fromName": values["fromName"] or "ByPassWord",
            "source": "user",
        }
    owner = await get_owner_user_id(session)
    permitted = owner == user_id

    return {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "secure": settings.smtp_secure,
        "user": settings.smtp_user if permitted else "",
        "password": settings.smtp_pass if permitted else "",
        "from": (settings.smtp_from or settings.smtp_user) if permitted else "",
        "fromName": settings.smtp_from_name if permitted else "ByPassWord",
        "source": "deployment" if permitted else "disabled",
    }


def masked_config(config: dict) -> dict:
    return {
        "host": config["host"],
        "port": config["port"],
        "secure": config["secure"],
        "user": config["user"],
        "from": config["from"],
        "fromName": config["fromName"],
        "hasPassword": bool(config["password"]),
    }


async def send_email(config: dict, to: str, subject: str, text: str) -> bool:
    if not config.get("user") or not config.get("password"):
        logger.warning("SMTP 未配置，跳过发送")
        return False

    connection = None
    try:
        for value in (config["host"], config["user"], config.get("from", ""), config.get("fromName", ""), to, subject):
            if any(ord(char) < 32 or ord(char) == 127 for char in str(value)):
                raise ValueError("mail headers contain control characters")
        message = EmailMessage()
        sender = config.get("from") or config["user"]
        message["From"] = f"{config.get('fromName') or 'ByPassWord'} <{sender}>"
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)
        connection = await _smtp_socket(config["host"], int(config["port"]))
        test_transport = settings.app_env == "test" and settings.smtp_allow_insecure_test
        await aiosmtplib.send(
            message,
            hostname=config["host"],
            sock=connection,
            username=config["user"],
            password=config["password"],
            use_tls=bool(config.get("secure")),
            start_tls=False if test_transport or config.get("secure") else True,
            validate_certs=True,
            local_hostname="bypw.local",
            timeout=15,
        )
        logger.info("邮件已发送")
        return True
    except Exception as exc:  # noqa: BLE001 - 邮件失败不影响主流程
        logger.warning("邮件发送失败 (%s)", type(exc).__name__)
        return False
    finally:
        if connection is not None:
            connection.close()


async def _smtp_socket(host: str, port: int) -> socket.socket:
    """Resolve once, validate every address, and connect the selected IP directly."""
    loop = asyncio.get_running_loop()
    addresses = await asyncio.wait_for(loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=5)
    allow_private = settings.app_env == "test" and settings.smtp_allow_private_hosts
    if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses) and not allow_private:
        raise ValueError("non-public SMTP endpoints are not allowed")
    last_error = None
    # Bound connection retries even if a hostname returns many public records.
    deadline = loop.time() + 10
    for family, socktype, protocol, _, address in addresses[:4]:
        connected = socket.socket(family, socktype, protocol)
        connected.setblocking(False)
        try:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("SMTP connection deadline reached")
            await asyncio.wait_for(loop.sock_connect(connected, address), timeout=min(5, remaining))
            return connected
        except Exception as exc:
            last_error = exc
            connected.close()
    raise OSError("SMTP connection failed") from last_error


async def send_to_user(
    session: AsyncSession, user: User, subject: str, text: str, to: str | None = None
) -> bool:
    config = await resolve_config(session, user.id)
    return await send_email(config, (to or user.email).strip(), subject, text)


def reset_code_email(code: str) -> tuple[str, str]:
    subject = "【密码库】重置主密码验证码"
    text = (
        "你正在重置密码库的主密码。\n\n"
        f"验证码：{code}\n"
        "有效期：10 分钟，最多尝试 5 次。\n\n"
        "重置时需要同时提供你的恢复码；没有恢复码将无法解密历史数据。\n"
        "如果这不是你本人的操作，请立即登录并修改主密码。\n"
    )
    return subject, text


def password_changed_email(ip: str, user_agent: str) -> tuple[str, str]:
    subject = "【密码库】主密码已修改"
    text = (
        "你的密码库主密码刚刚被修改。\n\n"
        f"IP：{ip}\n设备：{user_agent or '未知'}\n\n"
        "如果这不是你本人的操作，请立即使用恢复码重置主密码，并检查服务器安全。\n"
    )
    return subject, text


def risk_alert_email(action: str, ip: str, user_agent: str) -> tuple[str, str]:
    subject = f"【密码库】安全提醒：{action}"
    text = (
        f"检测到与你账号相关的重要操作：{action}\n\n"
        f"IP：{ip}\n设备：{user_agent or '未知'}\n\n"
        "如果这不是你本人的操作，请立即修改主密码。\n"
    )
    return subject, text


def test_email() -> tuple[str, str]:
    subject = "【密码库】SMTP 配置测试"
    text = "这是一封测试邮件。收到它说明你的 QQ 邮箱 SMTP 配置可用。\n"
    return subject, text


async def notify(
    session: AsyncSession, user: User, event_key: str, ctx: dict[str, str]
) -> bool:
    """按安全事件开关与用户自定义模板发送通知；事件未开启时静默跳过。

    发信失败不抛出，只返回 False，避免阻塞登录/改密等主流程。
    """
    from . import mail_events

    rendered = await mail_events.render(session, user.id, event_key, ctx)
    if not rendered:
        return False
    subject, body = rendered
    try:
        return await send_to_user(session, user, subject, body)
    except Exception:  # noqa: BLE001 - 通知失败不应影响主流程
        logger.warning("安全事件通知发送失败: %s", event_key, exc_info=True)
        return False
