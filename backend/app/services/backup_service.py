"""Owner-only verified AES-GCM SQLite snapshots; encryption key stored separately."""
import fcntl
import hashlib
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from ..core.config import settings
from ..core.runtime_security import private_directory, private_file, sqlite_file

MAGIC = b"BYPWBACKUP\x01"
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024

class BackupLimitReached(RuntimeError):
    pass

def backup_dir() -> Path:
    return Path(settings.backup_dir).absolute()

def sqlite_path() -> Path | None:
    return sqlite_file()

def _key() -> bytes:
    if not settings.backup_key_file:
        raise RuntimeError("BACKUP_KEY_FILE is required for encrypted snapshots")
    path = Path(settings.backup_key_file)
    private_file(path)
    key = path.read_bytes()
    if len(key) != 32:
        raise RuntimeError("backup key must contain exactly 32 random bytes")
    if key in {hashlib.sha256(settings.server_secret.encode()).digest(), hashlib.sha256(settings.jwt_secret.encode()).digest()}:
        raise RuntimeError("backup key must be independent of application secrets")
    if path.resolve().is_relative_to(backup_dir().resolve()):
        raise RuntimeError("backup key must be stored outside the snapshot directory")
    return key

@contextmanager
def _lock():
    directory = backup_dir()
    private_directory(directory)
    fd = os.open(directory / ".snapshot.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

def _snapshot_files() -> list[Path]:
    directory = backup_dir()
    if not directory.exists():
        return []
    return [path for path in directory.iterdir() if path.is_file() and not path.is_symlink() and
            ((path.name.startswith("vault-") and (path.name.endswith(".db") or path.name.endswith(".db.enc"))) or path.name.startswith(".pending-"))]

def _kind(path: Path) -> str:
    match = re.search(r"-(pre-import|manual|auto)\.db(?:\.enc)?$", path.name)
    return match.group(1) if match else "unknown"

def _meta(path: Path) -> dict:
    info = path.stat()
    return {"id": path.name, "createdAt": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
            "size": info.st_size, "kind": _kind(path), "encrypted": path.name.endswith(".db.enc")}

def verify_database_bytes(data: bytes) -> None:
    if not data or len(data) > MAX_SNAPSHOT_BYTES or not data.startswith(b"SQLite format 3\x00"):
        raise RuntimeError("invalid SQLite snapshot")
    with sqlite3.connect(":memory:") as check:
        check.deserialize(data)
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity verification failed")

def decrypt_snapshot(path: Path, key: bytes | None = None) -> bytes:
    private_file(path)
    if path.stat().st_size > MAX_SNAPSHOT_BYTES + 1024:
        raise RuntimeError("snapshot exceeds size limit")
    blob = path.read_bytes()
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 12 + 16:
        raise RuntimeError("invalid encrypted snapshot format")
    offset = len(MAGIC)
    plaintext = AESGCM(key or _key()).decrypt(blob[offset:offset + 12], blob[offset + 12:], MAGIC)
    verify_database_bytes(plaintext)
    return plaintext

def create_snapshot(kind: str = "manual") -> dict:
    if kind not in {"manual", "auto", "pre-import"}:
        raise ValueError("invalid snapshot kind")
    source = sqlite_path()
    if source is None or not source.is_file() or source.is_symlink():
        raise RuntimeError("SQLite source database is missing")
    key = _key()
    with _lock():
        # Count legacy/encrypted/unfinished disk backups. Never create a third
        # file or delete an old backup merely to obtain a slot.
        if len(_snapshot_files()) >= 2:
            raise BackupLimitReached("two snapshots already exist")
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src, sqlite3.connect(":memory:") as copy:
            size = src.execute("PRAGMA page_count").fetchone()[0] * src.execute("PRAGMA page_size").fetchone()[0]
            if size > MAX_SNAPSHOT_BYTES:
                raise RuntimeError("database exceeds snapshot size limit")
            src.backup(copy)
            # A WAL source copies WAL header flags. Rebuild the in-memory
            # snapshot in its native journal mode before serialize, so recovery
            # never requires a missing -wal companion file.
            copy.execute("PRAGMA temp_store=MEMORY")
            copy.execute("PRAGMA journal_mode=MEMORY")
            copy.execute("VACUUM")
            plaintext = copy.serialize()
        verify_database_bytes(plaintext)
        nonce = os.urandom(12)
        encrypted = MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)
        verify_database_bytes(AESGCM(key).decrypt(nonce, encrypted[len(MAGIC) + 12:], MAGIC))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        destination = backup_dir() / f"vault-{stamp}-{uuid4().hex[:10]}-{kind}.db.enc"
        temporary = None
        try:
            fd, name = tempfile.mkstemp(prefix=".pending-", dir=backup_dir())
            temporary = Path(name)
            with os.fdopen(fd, "wb") as output:
                output.write(encrypted)
                output.flush()
                os.fsync(output.fileno())
            private_file(temporary)
            if temporary.read_bytes() != encrypted:
                raise RuntimeError("snapshot write verification failed")
            os.rename(temporary, destination)
            temporary = None
            result = _meta(destination)
            result["sha256"] = hashlib.sha256(encrypted).hexdigest()
            result["verified"] = True
            return result
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

def list_snapshots() -> list[dict]:
    items = [_meta(path) for path in _snapshot_files() if not path.name.startswith(".pending-")]
    return sorted(items, key=lambda item: item["createdAt"], reverse=True)

def cleanup(retention_days: int, *, validated_snapshot: str | None = None) -> int:
    """Only expire older snapshots after a new verified replacement exists."""
    if not validated_snapshot:
        return 0
    if Path(validated_snapshot).name != validated_snapshot:
        raise RuntimeError("invalid snapshot identifier")
    marker = backup_dir() / validated_snapshot
    removed = 0
    with _lock():
        decrypt_snapshot(marker)
        now = datetime.now(timezone.utc)
        for path in _snapshot_files():
            if path == marker or path.name.startswith(".pending-"):
                continue
            age = (now - datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)).days
            kind = _kind(path)
            if (kind == "auto" and retention_days > 0 and age >= retention_days) or (kind == "pre-import" and age >= 30):
                path.unlink()
                removed += 1
    return removed


def delete_snapshot(path: Path) -> None:
    """Explicit service-operator CLI action; always keep a verified recovery copy."""
    if path.absolute().parent != backup_dir() or path.is_symlink() or _kind(path) == "unknown":
        raise RuntimeError("only a named snapshot in BACKUP_DIR may be removed")
    with _lock():
        available = _snapshot_files()
        if path.absolute() not in available:
            raise RuntimeError("snapshot does not exist")
        retained = [other for other in available if other != path.absolute() and other.name.endswith(".db.enc")]
        verified = False
        for other in retained:
            try:
                decrypt_snapshot(other)
                verified = True
                break
            except Exception:
                continue
        if not verified:
            raise RuntimeError("a different verified encrypted snapshot must be retained")
        path.unlink()
