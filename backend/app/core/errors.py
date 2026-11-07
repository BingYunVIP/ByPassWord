"""统一业务异常：与 docs/API.md 的错误码保持一致。"""

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}


def bad_request(message: str, detail: Any = None) -> ApiError:
    return ApiError(400, "bad_request", message, detail)


def unauthorized(message: str = "未登录或登录已过期", code: str = "unauthorized") -> ApiError:
    return ApiError(401, code, message)


def forbidden(message: str = "无权访问") -> ApiError:
    return ApiError(403, "forbidden", message)


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(404, "not_found", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def locked(message: str) -> ApiError:
    return ApiError(423, "account_locked", message)
