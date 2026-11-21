"""CardKey 发卡插件 —— 从 CardKeySDK/demo-backend/backend/server.py 迁入。

状态机、签发逻辑字节级保留；路由按 OpenHub 契约接鉴权。

兼容例外（见 docs/API_CONTRACT.md §8）：
  /verify 返回扁平格式 {"ok":..,"license"|"reason","message"}，
  因为现有 CardKey SDK 的 HttpRemoteVerifier 只认扁平格式，且用户要求
  "支持之前开发的客户端"。管理接口走统一包络。
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.auth import require_admin
from core.config import settings
from core.errors import ok
from core.plugin import Plugin
from plugins.cardkey import signing
from plugins.cardkey.store import CardStore

router = APIRouter()
_store: CardStore | None = None

MESSAGES = {
    "invalid": "卡密无效",
    "used": "卡密已使用",
    "expired": "卡密已过期",
    "device_mismatch": "设备不匹配",
    "revoked": "卡密已封禁",
}


def _get_store() -> CardStore:
    global _store
    if _store is None:
        _store = CardStore()
    return _store


def _private_key() -> str:
    path = settings.cardkey_private_key
    if not path:
        raise RuntimeError("未配置 OPENHUB_CARDKEY_PRIVATE_KEY（服务器私钥路径）")
    return path


@router.post("/verify")
async def verify(request: Request):
    """验卡：扁平响应，兼容现有 CardKey SDK 的 HttpRemoteVerifier。"""
    body = await request.json()
    code = (body.get("code") or "").strip()
    device_id = body.get("device_id") or ""
    product_id = body.get("product_id") or settings.cardkey_product
    if not code:
        return JSONResponse({"ok": False, "reason": "invalid", "message": "卡密为空"})

    success, reason, state = _get_store().activate(code, device_id)
    if not success:
        return JSONResponse({
            "ok": False,
            "reason": reason,
            "message": MESSAGES.get(reason, "验证失败"),
        })

    lic = signing.make_license(
        product_id, state["device_id"], int(time.time() * 1000),
        state["expires_at"], state["serial"], _private_key(),
    )
    # 扁平格式（兼容既有客户端）
    return JSONResponse({"ok": True, "license": lic})


@router.post("/issue")
async def issue(request: Request):
    """发卡：管理接口，统一包络。"""
    require_admin(request)
    body = await request.json()
    serial = int(body.get("serial") or int(time.time() * 1000))
    expires = 0 if body.get("expires", "never") in ("never", "0", 0, None) else int(body["expires"])
    max_a = int(body.get("max_activations") or 1)
    code = signing.make_license(
        settings.cardkey_product, "", int(time.time() * 1000),
        expires, serial, _private_key(),
    )
    _get_store().add(code, expires, max_a, serial)
    return ok({"code": code, "serial": serial}, request)


@router.post("/revoke")
async def revoke(request: Request):
    """封禁：管理接口，统一包络。"""
    require_admin(request)
    code = (await request.json()).get("code", "").strip()
    if _get_store().revoke(code):
        return ok({"revoked": True}, request)
    return JSONResponse(
        {"ok": False, "error": {"code": "CORE_NOT_FOUND", "message": "卡密不存在", "retryable": False}},
        status_code=404,
    )


@router.get("/codes")
def codes(request: Request):
    """列卡：管理接口，统一包络。"""
    require_admin(request)
    return ok({"codes": _get_store().list_codes()}, request)


class CardKeyPlugin(Plugin):
    name = "cardkey"
    version = "0.2.0"

    def routes(self) -> APIRouter:
        return router

    def on_enable(self):
        global _store
        _store = CardStore()

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version, "migrated": True}
