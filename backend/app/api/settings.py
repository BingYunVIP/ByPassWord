"""设置中心路由：加密设置、邮箱配置、备份策略。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..core.deps import get_current_user, require_owner_user
from ..core.errors import ApiError
from ..core.rate_limit import limiter
from ..models import User
from ..schemas.settings import (
    BackupSettingsIn,
    BackupSettingsOut,
    MailEventsIn,
    MailSettingsIn,
    MailTemplateIn,
    MailTestIn,
)
from ..schemas.vault import SettingsIn, SettingsOut
from ..services import auth_service, mail_events, mailer, secrets, vault_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut, summary="读取加密设置（整块密文）")
async def read_settings(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.get_settings(session, user.id)


@router.put("", summary="写入加密设置（整体覆盖）")
async def write_settings(
    payload: SettingsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.put_settings(session, user.id, payload)


# ============================================================
# 邮箱配置（服务端需要能读，因此单独加密存 user_secrets）
# ============================================================


@router.get("/mail", summary="读取 SMTP 配置（授权码只回布尔）")
async def read_mail_settings(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    config = await mailer.resolve_config(session, user.id)
    masked = mailer.masked_config(config)
    return {
        "host": masked["host"],
        "port": masked["port"],
        "secure": masked["secure"],
        "user": masked["user"],
        "from": masked["from"],
        "fromName": masked["fromName"],
        "hasPassword": masked["hasPassword"],
    }


@router.put("/mail", summary="保存 SMTP 配置（password 省略则保留原值）")
async def write_mail_settings(
    payload: MailSettingsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    previous = await mailer.resolve_config(session, user.id)
    endpoint_changed = previous.get("source") != "user" or any((
        previous["host"].lower() != payload.host.strip().lower(),
        previous["port"] != payload.port,
        previous["user"] != payload.user.strip(),
        previous["secure"] != payload.secure,
    ))
    if not payload.password and (endpoint_changed or not previous.get("password")):
        raise ApiError(400, "smtp_password_required", "新增或修改邮件服务器/账号时必须重新输入授权码")
    values = {
        "smtp_host": payload.host.strip(),
        "smtp_port": str(payload.port),
        "smtp_secure": "true" if payload.secure else "false",
        "smtp_user": payload.user.strip(),
        "smtp_from": (payload.sender or payload.user).strip(),
        "smtp_from_name": payload.fromName.strip() or "ByPassWord",
    }
    if payload.password:
        values["smtp_password"] = payload.password

    await secrets.set_secrets(session, user.id, values)
    await auth_service.write_audit(session, user.id, "mail_settings_updated")

    config = await mailer.resolve_config(session, user.id)
    masked = mailer.masked_config(config)
    return {"ok": True, "hasPassword": masked["hasPassword"]}


@router.post("/mail/test", summary="发送测试邮件（可指定收件人）")
@limiter.limit("3/minute")
async def send_test_mail(
    request: Request,
    payload: MailTestIn | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    target = ((payload.to if payload else None) or user.email).strip()
    subject, text = mailer.test_email()
    sent = await mailer.send_to_user(session, user, subject, text, to=target)
    await auth_service.write_audit(
        session,
        user.id,
        "mail_test",
        meta="sent" if sent else "mail_failed",
    )
    if not sent:
        raise ApiError(502, "mail_failed", "邮件发送失败，请检查 SMTP 配置或网络")
    return {"ok": True, "to": target}


# ============================================================
# 安全事件通知与邮件模板
# ============================================================


@router.get("/mail/events", summary="安全事件开关与事件清单")
async def get_mail_events(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    switches = await mail_events.load_switches(session, user.id)
    return {
        "events": [
            {
                "key": e["key"],
                "label": e["label"],
                "desc": e["desc"],
                "enabled": switches.get(e["key"], False),
            }
            for e in mail_events.EVENTS
        ]
    }


@router.put("/mail/events", summary="保存安全事件开关")
async def put_mail_events(
    payload: MailEventsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    switches = await mail_events.save_switches(session, user.id, payload.events)
    await auth_service.write_audit(session, user.id, "mail_events_updated")
    return {"events": switches}


@router.get("/mail/templates", summary="邮件模板列表（含默认值）")
async def get_mail_templates(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    templates = await mail_events.load_templates(session, user.id)
    return {
        "templates": [
            {
                "key": e["key"],
                "label": e["label"],
                "subject": templates[e["key"]]["subject"],
                "body": templates[e["key"]]["body"],
                "defaultSubject": e["subject"],
                "defaultBody": e["body"],
            }
            for e in mail_events.EVENTS
        ]
    }


@router.put("/mail/templates/{event_key}", summary="保存某个事件的邮件模板")
async def put_mail_template(
    event_key: str,
    payload: MailTemplateIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        saved = await mail_events.save_template(
            session, user.id, event_key, payload.subject, payload.body
        )
    except ValueError:
        raise ApiError(404, "unknown_event", "事件不存在") from None
    await auth_service.write_audit(session, user.id, "mail_template_updated")
    return {"ok": True, "template": saved}


@router.post("/mail/templates/{event_key}/reset", summary="恢复默认模板")
async def reset_mail_template(
    event_key: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    try:
        saved = await mail_events.reset_template(session, user.id, event_key)
    except ValueError:
        raise ApiError(404, "unknown_event", "事件不存在") from None
    return {"ok": True, "template": saved}


# ============================================================
# 备份策略
# ============================================================


@router.get("/backup", response_model=BackupSettingsOut, summary="读取备份策略")
async def read_backup_settings(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_owner_user),
) -> dict:
    schedule = await secrets.get_secret(session, user.id, "backup_schedule")
    retention = await secrets.get_secret(session, user.id, "backup_retention_days")
    return {
        "schedule": schedule or "weekly-02:00",
        "retentionDays": int(retention) if retention and retention.isdigit() else 30,
    }


@router.put("/backup", response_model=BackupSettingsOut, summary="保存备份策略")
async def write_backup_settings(
    payload: BackupSettingsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_owner_user),
) -> dict:
    await secrets.set_secrets(
        session,
        user.id,
        {
            "backup_schedule": payload.schedule,
            "backup_retention_days": str(payload.retentionDays),
        },
    )
    await auth_service.write_audit(
        session,
        user.id,
        "backup_settings_updated",
        meta=f"retention={payload.retentionDays}",
    )
    return {"schedule": payload.schedule, "retentionDays": payload.retentionDays}
