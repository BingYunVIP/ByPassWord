"""认证相关请求/响应模型。"""

import base64
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

AuthHash = Field(min_length=16, max_length=512)


def _ensure_base64(value: str, name: str, max_length: int = 16384) -> str:
    if len(value) > max_length:
        raise ValueError(f"{name} 过长")
    try:
        base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{name} 必须是合法 base64") from exc
    return value


class KdfParams(BaseModel):
    algo: Literal["argon2id", "pbkdf2"] = "argon2id"
    salt: str = Field(min_length=16, max_length=128)
    memoryKib: int = Field(default=65536, ge=8192, le=1048576)
    time: int = Field(default=3, ge=1, le=10)
    parallel: int = Field(default=1, ge=1, le=8)

    @field_validator("salt")
    @classmethod
    def _validate_salt(cls, value: str) -> str:
        return _ensure_base64(value, "salt", 256)


class KdfParamsOut(BaseModel):
    algo: str
    salt: str
    memoryKib: int
    time: int
    parallel: int


class PreloginRequest(BaseModel):
    email: EmailStr


class PreloginResponse(BaseModel):
    kdf: KdfParamsOut


class RegisterRequest(BaseModel):
    email: EmailStr
    kdf: KdfParams
    authHash: str = AuthHash
    wrappedDek: str
    dekNonce: str
    recoveryWrappedDek: str | None = None
    recoveryDekNonce: str | None = None
    recoveryAuthHash: str | None = Field(default=None, min_length=16, max_length=512)

    @field_validator("recoveryAuthHash")
    @classmethod
    def _validate_recovery_auth(cls, value: str | None) -> str | None:
        if value is not None and len(base64.b64decode(_ensure_base64(value, "recoveryAuthHash"))) != 32:
            raise ValueError("recoveryAuthHash 必须为32字节")
        return value

    @model_validator(mode="after")
    def _recovery_material(self):
        if self.recoveryAuthHash and (not self.recoveryWrappedDek or not self.recoveryDekNonce):
            raise ValueError("恢复认证必须同时提供恢复密钥包装和nonce")
        return self

    @field_validator("wrappedDek", "recoveryWrappedDek")
    @classmethod
    def _validate_wrapped(cls, value: str | None) -> str | None:
        return value if value is None else _ensure_base64(value, "wrappedDek")

    @field_validator("dekNonce", "recoveryDekNonce")
    @classmethod
    def _validate_nonce(cls, value: str | None) -> str | None:
        return value if value is None else _ensure_base64(value, "dekNonce", 256)


class LoginRequest(BaseModel):
    email: EmailStr
    authHash: str = AuthHash


class TokenResponse(BaseModel):
    accessToken: str
    expiresIn: int
    wrappedDek: str
    dekNonce: str


class TwoFactorRequiredResponse(BaseModel):
    requires2fa: bool = True
    challenge: str
    expiresIn: int


class VerifyTwoFactorRequest(BaseModel):
    challenge: str = Field(min_length=10, max_length=4096)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyRecoveryRequest(BaseModel):
    challenge: str = Field(min_length=10, max_length=4096)
    recoveryCode: str = Field(min_length=8, max_length=16)


class EnableTwoFactorRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EnableTwoFactorResponse(BaseModel):
    recoveryCodes: list[str]


class DisableTwoFactorRequest(BaseModel):
    authHash: str = AuthHash
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ChangePasswordRequest(BaseModel):
    oldAuthHash: str = AuthHash
    newAuthHash: str = AuthHash
    newKdf: KdfParams
    wrappedDek: str
    dekNonce: str

    @field_validator("wrappedDek")
    @classmethod
    def _validate_wrapped(cls, value: str) -> str:
        return _ensure_base64(value, "wrappedDek")

    @field_validator("dekNonce")
    @classmethod
    def _validate_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "dekNonce", 256)


class ForgotRequest(BaseModel):
    email: EmailStr


class ForgotVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotVerifyResponse(BaseModel):
    resetToken: str
    expiresIn: int
    # 客户端用恢复码解 DEK 需要这两个字段（仅在邮箱验证通过后返回）
    recoveryWrappedDek: str | None = None
    recoveryDekNonce: str | None = None


class ResetPasswordRequest(BaseModel):
    resetToken: str = Field(min_length=10, max_length=4096)
    recoveryAuthHash: str = Field(min_length=16, max_length=512)
    newKdf: KdfParams
    newAuthHash: str = AuthHash
    wrappedDek: str
    dekNonce: str

    @field_validator("recoveryAuthHash")
    @classmethod
    def _validate_recovery_auth(cls, value: str) -> str:
        if len(base64.b64decode(_ensure_base64(value, "recoveryAuthHash"))) != 32:
            raise ValueError("recoveryAuthHash 必须为32字节")
        return value

    @field_validator("wrappedDek")
    @classmethod
    def _validate_wrapped(cls, value: str) -> str:
        return _ensure_base64(value, "wrappedDek")

    @field_validator("dekNonce")
    @classmethod
    def _validate_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "dekNonce", 256)


class MeResponse(BaseModel):
    id: str
    email: str
    twoFactorEnabled: bool
    recoveryConfigured: bool
    isOwner: bool
    createdAt: str
    lastLoginAt: str | None


class RecoveryConfigurationRequest(BaseModel):
    authHash: str = AuthHash
    code: str | None = Field(default=None, min_length=6, max_length=6, pattern=r"^\d{6}$")
    recoveryAuthHash: str = Field(min_length=16, max_length=512)
    recoveryWrappedDek: str
    recoveryDekNonce: str

    @field_validator("recoveryAuthHash", "recoveryWrappedDek", "recoveryDekNonce")
    @classmethod
    def _validate_material(cls, value: str, info) -> str:
        decoded = base64.b64decode(_ensure_base64(value, info.field_name))
        length = {"recoveryAuthHash": 32, "recoveryWrappedDek": 48, "recoveryDekNonce": 12}[info.field_name]
        if len(decoded) != length:
            raise ValueError(f"{info.field_name} 必须为{length}字节")
        return value
