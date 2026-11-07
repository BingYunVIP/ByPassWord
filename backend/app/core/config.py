"""应用配置：全部来自环境变量 / .env，禁止在代码里硬编码密钥。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    # 应用
    app_name: str = "ByPassWord"
    app_env: Literal["development", "test", "local", "production"] = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./bypw.db"

    # 密钥
    jwt_secret: str = Field(default="dev-insecure-jwt-secret-change-me", repr=False)
    server_secret: str = Field(default="dev-insecure-server-secret-change-me", repr=False)
    allow_registration_after_first: bool = False

    # 令牌有效期
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # 限流开关（本地冒烟测试可临时关闭）
    rate_limit_enabled: bool = True

    # 启动时自动执行数据库迁移（生产建议 false，由部署脚本显式迁移）
    auto_migrate: bool = True

    # 备份快照目录（默认 backend/backups）
    backup_dir: str = "./backups"
    backup_key_file: str = ""
    backup_timezone: str = "Asia/Singapore"
    static_dir: str = ""
    max_request_bytes: int = Field(default=4 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)
    request_body_timeout_seconds: float = Field(default=15, ge=1, le=60)
    allowed_hosts: str = ""
    trusted_proxy_ips: str = ""
    smtp_allow_private_hosts: bool = False
    smtp_allow_insecure_test: bool = False

    @model_validator(mode="after")
    def secure_deployment(self):
        if self.app_env in {"local", "production"}:
            for name in ("jwt_secret", "server_secret"):
                value = getattr(self, name)
                if len(value) < 32 or len(set(value)) < 8 or any(part in value.lower() for part in ("dev-insecure", "change-me", "changeme", "your-secret", "placeholder")):
                    raise ValueError(f"{name} must be a distinct generated secret of at least 32 characters")
            if self.jwt_secret == self.server_secret:
                raise ValueError("JWT_SECRET and SERVER_SECRET must differ")
            if not self.backup_key_file or not Path(self.backup_key_file).is_absolute():
                raise ValueError("BACKUP_KEY_FILE must be an absolute private key-file path")
            if not self.rate_limit_enabled:
                raise ValueError("rate limits cannot be disabled in deployed environments")
            if self.smtp_allow_private_hosts or self.smtp_allow_insecure_test:
                raise ValueError("SMTP test exceptions cannot be enabled in deployed environments")
            if self.app_env == "local":
                for origin in self.cors_origins:
                    parsed = urlsplit(origin)
                    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                        raise ValueError("local deployment only permits loopback origins")
        return self

    # CORS
    allowed_origins: str = "http://localhost:899,http://127.0.0.1:899"

    # 邮件
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_secure: bool = True
    smtp_user: str = ""
    smtp_pass: str = Field(default="", repr=False)
    smtp_from: str = ""
    smtp_from_name: str = "ByPassWord"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
