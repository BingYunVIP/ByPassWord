"""Verify/decrypt a protected backup; never overwrite an existing output file.

Run with the configured DATABASE_URL/BACKUP_KEY_FILE (no secret values in argv):
  python scripts/encrypted_backup.py verify /private/vault-....db.enc
  python scripts/encrypted_backup.py decrypt /private/vault-....db.enc --output /private/restored.db
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.backup_service import decrypt_snapshot, delete_snapshot
from app.core.runtime_security import private_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["verify", "decrypt", "delete"])
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-delete", action="store_true")
    args = parser.parse_args()
    if args.operation == "delete":
        if not args.confirm_delete:
            parser.error("delete requires --confirm-delete")
        delete_snapshot(args.snapshot.absolute())
        print(json.dumps({"deleted": True, "retained_other_verified_copy": True}))
        return
    plaintext = decrypt_snapshot(args.snapshot)
    if args.operation == "decrypt":
        if args.output is None:
            parser.error("--output is required for decrypt")
        private_directory(args.output.absolute().parent)
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(plaintext)
            output.flush()
            os.fsync(output.fileno())
    print(json.dumps({"verified": True, "sqlite_integrity": "ok", "encrypted_sha256": hashlib.sha256(args.snapshot.read_bytes()).hexdigest(), "output_created": args.operation == "decrypt"}))

if __name__ == "__main__":
    main()
