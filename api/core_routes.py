"""内核路由：健康、设备、配置、产物、密钥管理、审计。"""
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File, Form

from core import audit, key_store, kernel_store
from core.auth import require_admin, check_api_key
from core.config import settings
from core.errors import ok, CORE_VALIDATION, CORE_NOT_FOUND
from plugins.cardkey import signing

router = APIRouter()


@router.get("/health")
def health(request: Request):
    plugins = sorted(getattr(request.app.state, "plugins", {}).keys())
    return ok({"ok": True, "version": "1.0.0", "plugins": plugins}, request)


@router.post("/devices")
async def register_device(request: Request):
    """客户端/管理均可：注册设备，device_id 只存 SHA-256 哈希。"""
    check_api_key(request)
    body = await request.json()
    device_id = body.get("device_id", "")
    if not device_id:
        raise CORE_VALIDATION("device_id 必填")
    product = body.get("product", "default")
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    return ok(kernel_store.register_device(device_id, product, meta), request)


@router.get("/devices")
def list_devices(request: Request, limit: int = 100, offset: int = 0, product: str | None = None):
    """管理接口：列出已注册设备（只有哈希，无原始 device_id）。"""
    require_admin(request)
    return ok({"devices": kernel_store.list_devices(limit, offset, product)}, request)


def _config_sign_bytes(product, enabled, rollout, force, config: dict) -> bytes:
    """与客户端约定的规范 JSON（sort_keys + 紧凑分隔，ensure_ascii=True）。"""
    body = {"product": product, "enabled": bool(enabled), "rollout_percent": rollout,
            "force_update": bool(force), "config": config}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


@router.get("/config/{product}")
def get_config(product: str, request: Request):
    """客户端：拉取签名配置包；命中灰度/强制开关，客户端凭内置公钥验签。"""
    check_api_key(request)
    cfg = kernel_store.get_config(product)
    if not cfg or not cfg["enabled"]:
        return ok({"product": product, "config": None, "signed": False}, request)
    body = {"product": product, "enabled": cfg["enabled"],
            "rollout_percent": cfg["rollout_percent"], "force_update": cfg["force_update"],
            "config": cfg["config"]}
    return ok({**body, "signature": cfg["signature"], "signature_algo": "RSA-SHA256",
               "signed": bool(cfg["signature"])}, request)


@router.post("/config/{product}")
async def set_config(product: str, request: Request):
    """管理接口：编辑配置并用私钥签名（私钥只在服务器）。"""
    require_admin(request)
    body = await request.json()
    config = body.get("config") if isinstance(body.get("config"), dict) else {}
    rollout = int(body.get("rollout_percent", 100))
    if rollout < 0 or rollout > 100:
        raise CORE_VALIDATION("rollout_percent 需在 0-100")
    enabled = bool(body.get("enabled", True))
    force = bool(body.get("force_update", False))
    key = settings.update_private_key or settings.cardkey_private_key
    if not key:
        raise CORE_VALIDATION("未配置签名私钥（OPENHUB_UPDATE_PRIVATE_KEY）")
    sig = signing.b32encode(signing.sign(_config_sign_bytes(product, enabled, rollout, force, config), key))
    return ok(kernel_store.save_config(product, enabled, rollout, force, config, sig), request)


@router.get("/configs")
def list_configs(request: Request):
    require_admin(request)
    return ok({"configs": kernel_store.list_configs()}, request)


@router.post("/artifacts")
async def upload_artifact(request: Request):
    """管理接口：上传 APK/产物（multipart），落盘 + 元数据入库。"""
    require_admin(request)
    form = await request.form()
    version = str(form.get("version", "")).strip()
    signer_fp = str(form.get("signer_fingerprint", "")).strip()
    if not version or not signer_fp:
        raise CORE_VALIDATION("version 与 signer_fingerprint 必填")
    upload: UploadFile = form.get("file")  # type: ignore
    if upload is None or not getattr(upload, "filename", None):
        raise CORE_VALIDATION("缺少 file 字段")
    product = str(form.get("product", "default"))
    channel = str(form.get("channel", "stable"))
    try:
        version_code = int(form.get("version_code", 0))
    except (TypeError, ValueError):
        raise CORE_VALIDATION("version_code 需为整数")
    data = await upload.read()
    sha = hashlib.sha256(data).hexdigest()
    art_dir = settings.data_dir / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{product}_{channel}_{version}_{sha[:8]}" + Path(upload.filename).suffix
    (art_dir / safe_name).write_bytes(data)
    rec = kernel_store.add_artifact(product, version, version_code, channel,
                                    signer_fp, sha, safe_name, len(data))
    return ok({**rec, "sha256": sha, "size": len(data)}, request)


@router.get("/artifacts")
def list_artifacts(request: Request, product: str | None = None):
    require_admin(request)
    return ok({"artifacts": kernel_store.list_artifacts(product)}, request)


@router.get("/artifacts/latest")
def latest_artifact(request: Request, product: str = "default", channel: str = "stable"):
    """客户端：查最新版本（含签名指纹，供下载后比对）。"""
    check_api_key(request)
    art = kernel_store.latest_artifact(product, channel)
    return ok({"product": product, "artifact": art}, request)


@router.get("/artifacts/download/{artifact_id}")
def download_artifact(artifact_id: int, request: Request):
    """客户端：下载产物文件本体。"""
    from fastapi.responses import FileResponse
    check_api_key(request)
    arts = kernel_store.list_artifacts()
    rec = next((a for a in arts if a["id"] == artifact_id), None)
    if not rec:
        raise CORE_NOT_FOUND("产物不存在")
    path = settings.data_dir / "artifacts" / rec["filename"]
    if not path.exists():
        raise CORE_NOT_FOUND("产物文件缺失")
    return FileResponse(str(path), filename=rec["filename"])


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


# ---- 管理看板聚合（一次取四插件数据，供 Web UI 渲染）----
@router.get("/overview")
def overview(request: Request):
    """聚合四个插件的只读列表，UI 只需一个 admin token + 一次请求即可渲染看板。
    直接实例化各 Store（其 __init__ 均为幂等 CREATE TABLE IF NOT EXISTS），
    不依赖插件是否已 on_enable，也不触碰插件的私有 _store 变量。"""
    require_admin(request)
    result = {"cardkey": [], "update": [], "announce": [], "crash": [],
              "devices": [], "configs": [], "artifacts": [], "errors": {}}

    def collect(name, fn):
        try:
            return fn()
        except Exception as exc:
            result["errors"][name] = str(exc)
            return []

    from plugins.cardkey.store import CardStore
    from plugins.update.store import UpdateStore
    from plugins.announce.store import AnnounceStore
    from plugins.crash.store import CrashStore

    result["cardkey"] = collect("cardkey", lambda: CardStore().list_codes())
    result["update"] = collect("update", lambda: UpdateStore().list())
    result["announce"] = collect("announce", lambda: AnnounceStore().list(limit=200))
    result["crash"] = collect("crash", lambda: CrashStore().query(limit=200))
    result["devices"] = collect("devices", lambda: kernel_store.list_devices(limit=50))
    result["configs"] = collect("configs", lambda: kernel_store.list_configs())
    result["artifacts"] = collect("artifacts", lambda: kernel_store.list_artifacts())
    return ok(result, request)
