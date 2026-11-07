"""开发/运维自检：打印数据库表、索引、外键与行数。

用法（在 backend 目录）：
    .venv/bin/python scripts/check_db.py [db_path]
"""

import sqlite3
import sys
from pathlib import Path


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bypw.db"
    if not Path(db_path).exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")

    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    print(f"数据库: {db_path}")
    print(f"表({len(tables)}): {', '.join(tables)}")

    indexes = con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    print(f"索引({len(indexes)}): {', '.join(i[0] for i in indexes)}")

    for table in tables:
        if table == "alembic_version":
            continue
        fks = con.execute(f"PRAGMA foreign_key_list({table})").fetchall()
        if fks:
            desc = ", ".join(f"{f[3]}->{f[2]}.{f[4]} on delete {f[6]}" for f in fks)
            print(f"外键 {table}: {desc}")

    for table in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"行数 {table:22} = {count}")

    con.close()


if __name__ == "__main__":
    main()
