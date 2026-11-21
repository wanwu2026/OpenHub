"""统一响应包络与错误码。"""
from fastapi import Request
from fastapi.responses import JSONResponse


def ok(data: dict, request: Request | None = None) -> dict:
    return {
        "ok": True,
        "data": data,
        "meta": {
            "request_id": getattr(request.state, "request_id", "req_local"),
            "api_version": "v1",
        },
    }


class ApiError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400, retryable: bool = False):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        super().__init__(message)

    def response(self, request: Request | None = None) -> JSONResponse:
        return JSONResponse(
            status_code=self.http_status,
            content={
                "ok": False,
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "retryable": self.retryable,
                },
                "meta": {
                    "request_id": getattr(request.state, "request_id", "req_local"),
                    "api_version": "v1",
                },
            },
        )


# 内核保留错误码。全部接受可选 message（默认语义不变），
# 避免"某处想附一句说明就给无参 lambda 传参"的运行时崩溃。
def _err(code: str, default: str, status: int, msg: str | None = None,
         retryable: bool = False) -> ApiError:
    return ApiError(code, msg if msg is not None else default, status, retryable)


CORE_UNAUTHORIZED = lambda msg=None: _err("CORE_UNAUTHORIZED", "凭据缺失或无效", 401, msg)
CORE_FORBIDDEN = lambda msg=None: _err("CORE_FORBIDDEN", "凭据无此权限", 403, msg)
CORE_NOT_FOUND = lambda msg=None: _err("CORE_NOT_FOUND", "资源不存在", 404, msg)
CORE_VALIDATION = lambda msg="参数校验失败": _err("CORE_VALIDATION", msg, 422)
CORE_RATE_LIMITED = lambda msg=None: _err("CORE_RATE_LIMITED", "触发限流", 429, msg, True)
CORE_INTERNAL = lambda msg=None: _err("CORE_INTERNAL", "服务端异常", 500, msg, True)
CORE_PLUGIN_DISABLED = lambda msg=None: _err("CORE_PLUGIN_DISABLED", "插件未启用", 404, msg)
