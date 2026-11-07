"""设置中心：邮箱（SMTP）与备份策略的请求模型。"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MailSettingsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    secure: bool = True
    user: str = Field(min_length=3, max_length=320)
    password: str | None = Field(default=None, max_length=256)
    sender: str = Field(default="", alias="from", max_length=320)
    fromName: str = Field(default="ByPassWord", max_length=64)

    @field_validator("host", "user", "sender", "fromName")
    @classmethod
    def reject_header_controls(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("邮件配置不允许控制字符")
        return value


class MailSettingsOut(BaseModel):
    host: str
    port: int
    secure: bool
    user: str
    from_: str = Field(serialization_alias="from")
    fromName: str
    hasPassword: bool


class MailTestIn(BaseModel):
    """测试发信收件人；留空则发到当前账号邮箱。"""

    to: str | None = Field(default=None, max_length=320)

    @field_validator("to")
    @classmethod
    def reject_controls(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("收件人不允许控制字符")
        return value


class MailEventsIn(BaseModel):
    """安全事件开关：{event_key: bool}，未出现的键保持原值。"""

    events: dict[str, bool] = Field(default_factory=dict)


class MailTemplateIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("subject")
    @classmethod
    def reject_header_controls(cls, value: str) -> str:
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("邮件标题不允许控制字符")
        return value


class BackupSettingsIn(BaseModel):
    schedule: Literal["daily-03:00", "weekly-02:00", "every-change"] = "weekly-02:00"
    retentionDays: int = Field(default=30, ge=0, le=3650)


class BackupSettingsOut(BaseModel):
    schedule: str
    retentionDays: int
