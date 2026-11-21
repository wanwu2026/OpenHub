"""崩溃上报插件：PII 脱敏 + 设备限流 + 单条/批量上报 + 处理状态。

隐私：device_id 只存 SHA-256；堆栈里的邮箱/手机号/Bearer token/长十六进制串脱敏。
限流：同一设备 10 分钟内最多 20 条，防日志洪水（返回 CORE_RATE_LIMITED）。
"""
import hashlib
import re

from fastapi import APIRouter, Request

from core.auth import check_api_key, require_admin
from core.errors import CORE_NOT_FOUND, CORE_RATE_LIMITED, CORE_VALIDATION, ok
from core.plugin import Plugin
from plugins.crash.store import CrashStore

router = APIRouter()
_store: CrashStore | None = None

_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[HEX]"),
]
_WINDOW_MS = 10 * 60 * 1000
_MAX_PER_WINDOW = 20


def _get_store() -> CrashStore:
    global _store
    if _store is None:
        _store = CrashStore()
    return _store


def redact(text: str) -> str:
    for pattern, repl in _PII:
        text = pattern.sub(repl, text)
    return text


def _device_hash(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


@router.post("/report")
async def report(request: Request):
    check_api_key(request)
    body = await request.json()
    device_id = body.get("device_id", "")
    app_id = body.get("app_id") or body.get("product") or "default"
    items = body.get("reports") or [body]
    if not device_id:
        raise CORE_VALIDATION("device_id 必填")
    dh = _device_hash(device_id)
    if _get_store().recent_count(dh, _WINDOW_MS) + len(items) > _MAX_PER_WINDOW:
        raise CORE_RATE_LIMITED("上报过于频繁，请稍后重试")
    ids = []
    for it in items:
        stack = it.get("stacktrace") or it.get("message") or ""
        if not stack:
            continue
        ids.append(_get_store().add(app_id, dh, redact(str(stack))))
    return ok({"accepted": len(ids), "ids": ids}, request)


@router.get("/reports")
def reports(request: Request, app_id: str | None = None, status: str | None = None,
            limit: int = 100, offset: int = 0):
    require_admin(request)
    return ok({"reports": _get_store().query(app_id, status, limit, offset)}, request)


@router.post("/{report_id}/resolve")
def resolve(report_id: int, request: Request):
    require_admin(request)
    if not _get_store().resolve(report_id):
        raise CORE_NOT_FOUND("上报记录不存在")
    return ok({"id": report_id, "status": "resolved"}, request)


class CrashPlugin(Plugin):
    name = "crash"
    version = "0.2.0"

    def routes(self) -> APIRouter:
        return router

    def on_enable(self):
        global _store
        _store = CrashStore()

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version, "implemented": True}
