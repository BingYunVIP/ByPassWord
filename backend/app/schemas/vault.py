"""金库同步相关的请求/响应模型（全部内容为客户端密文）。"""

import base64
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _ensure_base64(value: str, name: str, max_length: int = 1_000_000) -> str:
    if len(value) > max_length:
        raise ValueError(f"{name} 过长")
    try:
        base64.b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{name} 必须是合法 base64") from exc
    return value


class FolderIn(BaseModel):
    id: str = Field(min_length=8, max_length=36)
    ciphertext: str
    nonce: str = Field(min_length=8, max_length=64)
    sortOrder: int = 0

    @field_validator("ciphertext")
    @classmethod
    def _v_cipher(cls, value: str) -> str:
        return _ensure_base64(value, "ciphertext")

    @field_validator("nonce")
    @classmethod
    def _v_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "nonce", 128)


class FolderPatch(BaseModel):
    ciphertext: str
    nonce: str = Field(min_length=8, max_length=64)
    sortOrder: int | None = None
    rev: int = Field(ge=1)

    @field_validator("ciphertext")
    @classmethod
    def _v_cipher(cls, value: str) -> str:
        return _ensure_base64(value, "ciphertext")

    @field_validator("nonce")
    @classmethod
    def _v_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "nonce", 128)


class ItemIn(BaseModel):
    id: str = Field(min_length=8, max_length=36)
    ciphertext: str
    nonce: str = Field(min_length=8, max_length=64)

    @field_validator("ciphertext")
    @classmethod
    def _v_cipher(cls, value: str) -> str:
        return _ensure_base64(value, "ciphertext")

    @field_validator("nonce")
    @classmethod
    def _v_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "nonce", 128)


class ItemPatch(BaseModel):
    ciphertext: str
    nonce: str = Field(min_length=8, max_length=64)
    rev: int = Field(ge=1)

    @field_validator("ciphertext")
    @classmethod
    def _v_cipher(cls, value: str) -> str:
        return _ensure_base64(value, "ciphertext")

    @field_validator("nonce")
    @classmethod
    def _v_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "nonce", 128)


class FolderOut(BaseModel):
    id: str
    ciphertext: str
    nonce: str
    sortOrder: int
    rev: int
    updatedAt: str
    deletedAt: str | None


class ItemOut(BaseModel):
    id: str
    ciphertext: str
    nonce: str
    rev: int
    updatedAt: str
    deletedAt: str | None


class VaultOut(BaseModel):
    rev: int
    folders: list[FolderOut]
    items: list[ItemOut]


class ImportRequest(BaseModel):
    folders: list[FolderIn] = Field(default_factory=list)
    items: list[ItemIn] = Field(default_factory=list)
    strategy: Literal["skip", "overwrite", "duplicate"] = "skip"

    @field_validator("folders", "items")
    @classmethod
    def _limit(cls, value: list) -> list:
        if len(value) > 5000:
            raise ValueError("单次导入数量过多（上限 5000）")
        return value


class ImportOut(BaseModel):
    imported: dict[str, int]
    skipped: int
    rev: int


class SettingsIn(BaseModel):
    ciphertext: str
    nonce: str = Field(min_length=8, max_length=64)

    @field_validator("ciphertext")
    @classmethod
    def _v_cipher(cls, value: str) -> str:
        return _ensure_base64(value, "ciphertext")

    @field_validator("nonce")
    @classmethod
    def _v_nonce(cls, value: str) -> str:
        return _ensure_base64(value, "nonce", 128)


class SettingsOut(BaseModel):
    ciphertext: str | None
    nonce: str | None
    updatedAt: str | None
