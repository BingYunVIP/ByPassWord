"""Additive auth migration preserves synthetic legacy wrappers and ownership."""

import base64
import os
from pathlib import Path
import sqlite3
import asyncio

from alembic import command
from alembic.config import Config

from app.core.config import settings


async def test_legacy_schema_upgrade_preserves_encrypted_material(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    backend = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(settings, "database_url", "sqlite+aiosqlite:///" + str(database))
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    await asyncio.to_thread(command.upgrade, config, "8295d6f562e1")
    wrapped = base64.b64encode(os.urandom(48)).decode()
    recovery = base64.b64encode(os.urandom(48)).decode()
    older = "00000000-0000-4000-8000-000000000001"
    newer = "00000000-0000-4000-8000-000000000002"
    with sqlite3.connect(database) as connection:
        for user_id, created in [(newer, "2026-11-02T00:00:00Z"), (older, "2026-11-01T00:00:00Z")]:
            connection.execute(
                "INSERT INTO users (id,email,auth_hash,kdf_algo,kdf_salt,kdf_memory_kib,kdf_time,kdf_parallel,"
                "wrapped_dek,dek_nonce,recovery_wrapped_dek,recovery_dek_nonce,failed_attempts,created_at)"
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, user_id + "@example.com", "synthetic-unused-auth-hash", "argon2id", "synthetic-salt", 65536, 3, 1,
                 wrapped, "synthetic-nonce", recovery, "synthetic-recovery-nonce", 0, created),
            )
        connection.execute(
            "INSERT INTO refresh_tokens (id,user_id,token_hash,expires_at,created_at) VALUES (?,?,?,?,?)",
            ("legacy-refresh", older, "synthetic-unused-token-hash", "2026-12-01T00:00:00Z", "2026-11-01T00:00:00Z"),
        )
    await asyncio.to_thread(command.upgrade, config, "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = connection.execute("SELECT wrapped_dek,recovery_wrapped_dek,recovery_auth_hash,credential_version,two_factor_version FROM users").fetchall()
        assert len(rows) == 2
        assert all(row == (wrapped, recovery, None, 0, 0) for row in rows)
        assert connection.execute("SELECT owner_user_id FROM installation_owner WHERE id=1").fetchone()[0] == older
        assert connection.execute("SELECT session_id,credential_version FROM refresh_tokens").fetchone() == (None, 0)
