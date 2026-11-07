"""启动时自动应用数据库迁移。

目的：避免「新库没建表 → no such table」这类低级错误。
生产环境建议关闭（AUTO_MIGRATE=false），由部署脚本显式执行并在迁移前备份。
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import settings

logger = logging.getLogger("bypw.migrate")

BACKEND_DIR = Path(__file__).resolve().parents[2]


def run_migrations() -> None:
    # Alembic 默认会打一堆 INFO，启动时太吵，只保留警告以上
    logging.getLogger("alembic").setLevel(logging.WARNING)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    logger.info("数据库已迁移到最新版本: %s", settings.database_url)
