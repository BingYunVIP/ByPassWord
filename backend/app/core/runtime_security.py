"""Private runtime files and bounded HTTP input, shared by deployment and tests."""

import os
import stat
import asyncio
from urllib.parse import urlsplit
from pathlib import Path

from .config import settings


def private_file(path: Path, *, required: bool = True) -> None:
    if path.is_symlink():
        raise RuntimeError("runtime files must not be symlinks")
    try:
        info = path.stat()
    except FileNotFoundError:
        if required:
            raise RuntimeError("required runtime file is missing") from None
        return
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("runtime files must be owned by the service account with mode 0600")


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("runtime directories must not be symlinks")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("runtime directories must be owned by the service account with mode 0700")


def sqlite_file() -> Path | None:
    if not settings.database_url.startswith("sqlite") or "///" not in settings.database_url:
        return None
    raw = settings.database_url.split("///", 1)[1]
    return None if raw == ":memory:" else Path(raw).absolute()


def validate_runtime_paths() -> None:
    """Never silently chmod existing deployment data; deployment prepares permissions."""
    os.umask(0o077)
    if settings.app_env not in {"local", "production"}:
        return
    database = sqlite_file()
    if database is not None:
        private_directory(database.parent)
        private_file(database, required=False)
        for suffix in ("-wal", "-shm"):
            private_file(Path(str(database) + suffix), required=False)
    private_directory(Path(settings.backup_dir).absolute())
    from ..services.backup_service import _key
    _key()


class RequestTooLarge(Exception):
    pass


class SecurityMiddleware:
    """Buffer bounded request bodies before dispatch; append headers to every response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                for key, value in [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer")]:
                    headers = [(k, v) for k, v in headers if k.lower() != key]
                    headers.append((key, value))
                headers.append((b"content-security-policy", b"default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"))
                message["headers"] = headers
            await send(message)

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if settings.app_env in {"local", "production"}:
            host_values = [v for k, v in scope.get("headers", []) if k.lower() == b"host"]
            permitted = {"localhost", "127.0.0.1", "::1"} if settings.app_env == "local" else {
                host.strip().lower() for host in settings.allowed_hosts.split(",") if host.strip()
            }
            if settings.app_env == "production" and not permitted:
                permitted = {urlsplit(origin).hostname for origin in settings.cors_origins}
            try:
                parsed = urlsplit("//" + host_values[0].decode("ascii")) if len(host_values) == 1 else None
                if parsed is None or parsed.username or parsed.password or parsed.path or parsed.hostname not in permitted:
                    raise ValueError("untrusted host")
                if parsed.port is not None and not 1 <= parsed.port <= 65535:
                    raise ValueError("invalid port")
            except (UnicodeError, ValueError, IndexError):
                return await JSONResponse({"error": {"code": "invalid_host", "message": "请求Host不受信任", "detail": None}}, status_code=400)(scope, receive, secured_send)
        try:
            if int(headers.get(b"content-length", b"0")) > settings.max_request_bytes:
                raise RequestTooLarge()
        except (ValueError, RequestTooLarge):
            return await JSONResponse({"error": {"code": "request_too_large", "message": "请求超过大小限制", "detail": None}}, status_code=413)(scope, receive, secured_send)
        body = bytearray()
        deadline = asyncio.get_running_loop().time() + settings.request_body_timeout_seconds
        while True:
            if asyncio.get_running_loop().time() >= deadline:
                return await JSONResponse({"error": {"code": "request_timeout", "message": "请求体接收超时", "detail": None}}, status_code=408)(scope, receive, secured_send)
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - asyncio.get_running_loop().time()))
            except asyncio.TimeoutError:
                return await JSONResponse({"error": {"code": "request_timeout", "message": "请求体接收超时", "detail": None}}, status_code=408)(scope, receive, secured_send)
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > settings.max_request_bytes:
                return await JSONResponse({"error": {"code": "request_too_large", "message": "请求超过大小限制", "detail": None}}, status_code=413)(scope, receive, secured_send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, secured_send)
