"""限流：登录、注册、找回密码等敏感接口的爆破防护。"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, headers_enabled=False)


async def rate_limit_handler(_request: Request, _exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "请求过于频繁，请稍后再试",
                "detail": None,
            }
        },
    )
