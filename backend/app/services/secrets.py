"""服务端可读的按用户凭证（SMTP 授权码、备份策略等）。

这类数据服务端必须能读（否则发不了信、跑不了清理），
因此用 SERVER_SECRET 派生密钥加密后存 user_secrets 表。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import decrypt_server, encrypt_server
from ..models import UserSecret
from ..models.base import utcnow


async def get_secret(session: AsyncSession, user_id: str, key: str) -> str | None:
    row = await session.get(UserSecret, (user_id, key))
    if row is None:
        return None
    try:
        return decrypt_server(row.value_enc, row.value_nonce)
    except Exception:  # noqa: BLE001 - 密钥轮换后旧值解不开，按未设置处理
        return None


async def set_secret(session: AsyncSession, user_id: str, key: str, value: str) -> None:
    ciphertext, nonce = encrypt_server(value)
    row = await session.get(UserSecret, (user_id, key))
    if row is None:
        session.add(
            UserSecret(user_id=user_id, key=key, value_enc=ciphertext, value_nonce=nonce)
        )
    else:
        row.value_enc = ciphertext
        row.value_nonce = nonce
        row.updated_at = utcnow()
    await session.commit()


async def set_secrets(session: AsyncSession, user_id: str, values: dict[str, str]) -> None:
    for key, value in values.items():
        ciphertext, nonce = encrypt_server(value)
        row = await session.get(UserSecret, (user_id, key))
        if row is None:
            session.add(
                UserSecret(user_id=user_id, key=key, value_enc=ciphertext, value_nonce=nonce)
            )
        else:
            row.value_enc = ciphertext
            row.value_nonce = nonce
            row.updated_at = utcnow()
    await session.commit()
