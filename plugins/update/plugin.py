"""更新检查插件：清单签名 + APK 签名证书指纹双校验（契约 §7）。

客户端下载更新必须同时验两件事：
1. 用内置公钥验 manifest 的服务端签名（防清单被篡改）；
2. 下载 APK 后比对 manifest.signer_fingerprint 与实际签名证书指纹（防下载 URL 被换包）。
只做第 1 条 = 可被中间人换成任意 APK —— 这是更新检查类客户端最常见的漏洞。
"""
import json
import re

from fastapi import APIRouter, Request

from core.auth import check_api_key, require_admin
from core.config import settings
from core.errors import CORE_NOT_FOUND, CORE_VALIDATION, ok
from core.plugin import Plugin
from plugins.cardkey import signing
from plugins.update.store import UpdateStore

router = APIRouter()
_store: UpdateStore | None = None
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _get_store() -> UpdateStore:
    global _store
    if _store is None:
        _store = UpdateStore()
    return _store


def _private_key() -> str:
    return settings.update_private_key or settings.cardkey_private_key


def canonical(manifest: dict) -> bytes:
    """签名/验签都用同一套规范化，客户端能照此重建字节。"""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


@router.post("/publish")
async def publish(request: Request):
    """发布版本：服务端用私钥签清单，存库。管理接口。"""
    require_admin(request)
    body = await request.json()
    required = ("product", "version", "signer_fingerprint", "apk_url", "sha256")
    missing = [k for k in required if not body.get(k)]
    if missing:
        raise CORE_VALIDATION(f"缺少字段: {', '.join(missing)}")
    fp = body["signer_fingerprint"]
    if not _HEX64.match(fp):
        raise CORE_VALIDATION("signer_fingerprint 需为 64 位十六进制（APK 签名证书 SHA-256）")
    try:
        vc = int(body.get("version_code", 0))
    except (TypeError, ValueError):
        raise CORE_VALIDATION("version_code 需为整数")
    key = _private_key()
    if not key:
        raise CORE_VALIDATION("未配置私钥（OPENHUB_UPDATE_PRIVATE_KEY）")
    manifest = {
        "product": body["product"],
        "version": body["version"],
        "version_code": vc,
        "channel": body.get("channel", "stable"),
        "signer_fingerprint": fp,
        "apk_url": body["apk_url"],
        "sha256": body["sha256"],
        "notes": body.get("notes", ""),
    }
    sig = signing.b32encode(signing.sign(canonical(manifest), key))
    _get_store().publish(manifest["product"], manifest["version"], vc,
                         manifest["channel"], fp, json.dumps(manifest, ensure_ascii=False), sig)
    return ok({"version": manifest["version"], "version_code": vc,
               "manifest_signature": sig}, request)


@router.get("/check")
def check(request: Request, product: str, current_version_code: int = 0,
          channel: str = "stable"):
    """客户端查更新：返回签名清单，客户端自行验签 + 比对指纹。"""
    check_api_key(request)
    row = _get_store().latest(product, channel)
    if not row:
        return ok({"has_update": False, "manifest": None}, request)
    has_update = row["version_code"] > current_version_code
    return ok({
        "has_update": has_update,
        "manifest": json.loads(row["manifest_json"]) if has_update else None,
        "manifest_signature": row["signature"] if has_update else None,
        "signature_algo": "RSA-SHA256",
        "hint": "先验 manifest 签名，再下载 APK 并比对 signer_fingerprint 与证书实际指纹",
    }, request)


@router.get("/manifest/{product}")
def get_manifest(product: str, request: Request, channel: str = "stable"):
    check_api_key(request)
    row = _get_store().latest(product, channel)
    if not row:
        raise CORE_NOT_FOUND("无该产品的更新清单")
    return ok({"manifest": json.loads(row["manifest_json"]),
               "manifest_signature": row["signature"],
               "signature_algo": "RSA-SHA256"}, request)


@router.get("/verify/{product}")
def verify_manifest(product: str, request: Request, channel: str = "stable"):
    """服务端自检：用公钥验最新清单签名是否有效。"""
    require_admin(request)
    row = _get_store().latest(product, channel)
    if not row:
        raise CORE_NOT_FOUND("无该产品的更新清单")
    pub = request.query_params.get("public_key_base64") or settings.update_public_key_base64
    if not pub:
        raise CORE_VALIDATION("需提供 public_key_base64（查询参数或配置 OPENHUB_UPDATE_PUBLIC_KEY_BASE64）")
    valid = signing.verify_sig(canonical(json.loads(row["manifest_json"])),
                               signing.b32decode(row["signature"]), pub)
    return ok({"valid": valid, "version": row["version"]}, request)


@router.get("/list")
def list_updates(request: Request, product: str | None = None):
    require_admin(request)
    return ok({"updates": _get_store().list(product)}, request)


class UpdatePlugin(Plugin):
    name = "update"
    version = "0.2.0"

    def routes(self) -> APIRouter:
        return router

    def on_enable(self):
        global _store
        _store = UpdateStore()

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version, "implemented": True}
