"""回归测试：空数据库启动时应自动建表（防止「no such table」再次出现）。"""

import sqlite3

from app.core import config, migrate


def test_run_migrations_creates_schema_on_empty_db(tmp_path, monkeypatch) -> None:
    db_file = tmp_path / "fresh.db"
    assert not db_file.exists()

    monkeypatch.setattr(config.settings, "database_url", f"sqlite+aiosqlite:///{db_file}")
    migrate.run_migrations()

    assert db_file.exists(), "迁移后应生成数据库文件"
    con = sqlite3.connect(db_file)
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        con.close()

    assert "users" in tables, f"缺少 users 表，实际表: {sorted(tables)}"
    assert "alembic_version" in tables, "应由 Alembic 管理版本，而不是裸 create_all"
    assert "items" in tables and "folders" in tables
