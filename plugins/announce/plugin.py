"""公告插件：服务端签发公告，客户端逐条验签（防假公告）。

与 update 插件共用签名密钥（OPENHUB_UPDATE_PRIVATE_KEY，未配置回退 cardkey）。
签名字节 = 对稳定字段的规范化 JSON 做 RSA-SHA256，客户端用同法重建验签。
数据库自增 id 不进签名体，仅作客户端已读去重用（改 id 最多导致重复弹窗，非安全问题）。
"""
import json
import time

from fastapi import APIRouter, Request

from core.auth import check_api_key, require_admin
from core.errors import CORE_NOT_FOUND, CORE_VALIDATION, ok
from core.plugin import Plugin
from plugins.cardkey import signing
from plugins.announce.store import AnnounceStore

router = APIRouter()
_store: AnnounceStore | None = None

_LEVELS = {"info", "warn", "urgent"}


def canonical(notice: dict) -> bytes:
    """与 update 插件一致的规范化：sort_keys + 紧凑分隔，默认 ensure_ascii=True。"""
    signed = {k: notice[k] for k in ("product", "title", "content",
                                     "level", "force_popup", "published_at")}
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _get_store() -> AnnounceStore:
    global _store
    if _store is None:
        _store = AnnounceStore()
    return _store


def _private_key() -> str:
    from core.config import settings
    return settings.update_private_key or settings.cardkey_private_key


@router.post("/publish")
async def publish(request: Request):
    require_admin(request)
    body = await request.json()
    for k in ("product", "title", "content"):
        if not body.get(k):
            raise CORE_VALIDATION(f"缺少字段: {k}")
    level = body.get("level", "info")
    if level not in _LEVELS:
        raise CORE_VALIDATION(f"level 必须为 {', '.join(sorted(_LEVELS))}")
    key = _private_key()
    if not key:
        raise CORE_VALIDATION("未配置签名私钥（OPENHUB_UPDATE_PRIVATE_KEY）")
    notice = {
        "product": body["product"],
        "title": body["title"],
        "content": body["content"],
        "level": level,
        "force_popup": bool(body.get("force_popup", False)),
        "published_at": int(body.get("published_at", int(time.time() * 1000))),
    }
    sig = signing.b32encode(signing.sign(canonical(notice), key))
    nid = _get_store().publish(notice["product"], notice["title"], notice["content"],
                               notice["level"], notice["force_popup"],
                               notice["published_at"], sig)
    return ok({"id": nid, "signature": sig}, request)


@router.get("/list")
def list_notices(request: Request, product: str, since: int = 0,
                 limit: int = 100, offset: int = 0):
    check_api_key(request)
    return ok({"notices": _get_store().list(product, since, limit, offset)}, request)


@router.get("/verify/{notice_id}")
def verify_notice(notice_id: int, request: Request, public_key_base64: str = ""):
    require_admin(request)
    row = _get_store().get(notice_id)
    if not row:
        raise CORE_NOT_FOUND("公告不存在")
    from core.config import settings
    pub = public_key_base64 or settings.update_public_key_base64
    if not pub:
        raise CORE_VALIDATION("未提供公钥（public_key_base64）")
    valid = signing.verify_sig(canonical(row), signing.b32decode(row["signature"]), pub)
    return ok({"id": notice_id, "valid": valid}, request)


class AnnouncePlugin(Plugin):
    name = "announce"
    version = "0.2.0"

    def routes(self) -> APIRouter:
        return router

    def on_enable(self):
        global _store
        _store = AnnounceStore()

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version, "implemented": True}
