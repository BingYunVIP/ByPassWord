"""用户与账号级认证数据。"""

from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UTCDateTime, new_uuid, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)

    # 认证：服务端只存 Argon2id(authKey)
    auth_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    two_factor_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    # KDF 参数（客户端派生主密钥用）
    kdf_algo: Mapped[str] = mapped_column(String(32), default="argon2id", nullable=False)
    kdf_salt: Mapped[str] = mapped_column(Text, nullable=False)
    kdf_memory_kib: Mapped[int] = mapped_column(Integer, default=65536, nullable=False)
    kdf_time: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    kdf_parallel: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # 被 encKey 包裹的 DEK（服务端不可解）
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    dek_nonce: Mapped[str] = mapped_column(Text, nullable=False)

    # 恢复码包裹的 DEK（唯一恢复手段）
    recovery_wrapped_dek: Mapped[str | None] = mapped_column(Text)
    recovery_dek_nonce: Mapped[str | None] = mapped_column(Text)
    recovery_auth_hash: Mapped[str | None] = mapped_column(Text)

    # 账号 2FA（服务端可解，用于校验 TOTP）
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_secret_nonce: Mapped[str | None] = mapped_column(Text)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    totp_last_step: Mapped[int | None] = mapped_column(Integer)

    # 登录保护
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_ip: Mapped[str | None] = mapped_column(String(64))
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36), index=True)
    credential_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class TotpRecoveryCode(Base):
    __tablename__ = "totp_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AuthChallenge(Base):
    """Single-use JWT state; JWT signatures alone do not implement consumption."""

    __tablename__ = "auth_challenges"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, nullable=False)
    two_factor_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class InstallationOwner(Base):
    """The fixed primary key makes first-account ownership a database claim."""

    __tablename__ = "installation_owner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
