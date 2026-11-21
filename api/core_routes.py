"""内核路由：健康、设备、配置、产物、密钥管理、审计。"""
from fastapi import APIRouter, Request

from core import audit, key_store
from core.auth import require_admin
from core.errors import ok, CORE_VALIDATION, CORE_NOT_FOUND

router = APIRouter()


@router.get("/health")
def health(request: Request):
    plugins = sorted(getattr(request.app.state, "plugins", {}).keys())
    return ok({"ok": True, "version": "1.0.0", "plugins": plugins}, request)


@router.post("/devices")
async def register_device(request: Request):
    body = await request.json()
    if not body.get("device_id"):
        raise CORE_VALIDATION("device_id 必填")
    # 骨架：真实实现落库（见 docs/ARCHITECTURE.md）
    return ok({"device_id": body["device_id"], "registered": True}, request)


@router.get("/config/{product}")
def get_config(product: str, request: Request):
    # 骨架：返回签名配置包占位
    return ok({"product": product, "config": None, "signed": False}, request)


@router.post("/artifacts")
async def upload_artifact(request: Request):
    body = await request.json()
    required = ("version", "channel", "signer_fingerprint")
    missing = [k for k in required if not body.get(k)]
    if missing:
        raise CORE_VALIDATION(f"缺少字段: {', '.join(missing)}")
    # 骨架：signer_fingerprint 为必填，供客户端校验 APK 签名（见契约 §7）
    return ok({"artifact": body, "stored": False}, request)


@router.get("/artifacts/latest")
def latest_artifact(request: Request, product: str = "default"):
    return ok({"product": product, "artifact": None}, request)


# ---- 密钥管理（管理接口）----
@router.get("/keys")
def list_keys(request: Request):
    require_admin(request)
    return ok({"keys": key_store.list_keys()}, request)


@router.post("/keys")
async def create_key(request: Request):
    require_admin(request)
    body = await request.json()
    label = body.get("label", "")
    scope = body.get("scope", "client")
    if scope not in ("admin", "client"):
        raise CORE_VALIDATION("scope 只能是 admin 或 client")
    plain, key_id = key_store.create_key(label, scope)
    # 明文只在这里返回一次，之后库里只剩哈希
    return ok({"id": key_id, "key": plain, "scope": scope, "label": label}, request)


@router.post("/keys/{key_id}/revoke")
def revoke_key(key_id: int, request: Request):
    require_admin(request)
    if not key_store.revoke_key(key_id):
        raise CORE_NOT_FOUND("key 不存在")
    return ok({"id": key_id, "revoked": True}, request)


# ---- 审计日志（管理接口）----
@router.get("/audit")
def get_audit(request: Request, limit: int = 100, offset: int = 0, path: str | None = None):
    require_admin(request)
    events = audit.query(limit=limit, offset=offset, path_prefix=path)
    return ok({"events": events, "count": len(events)}, request)
