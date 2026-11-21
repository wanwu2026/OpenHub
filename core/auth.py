"""鉴权：Admin Token（管理接口）与 API Key（客户端接口）。

两种凭据来源：
1. bootstrap：install.sh 生成、写在 .env 的初始 token/key（DB 为空时靠它启动）；
2. 数据库：通过 /api/v1/core/keys 管理，只存哈希，可单独吊销。

保留"有 token 但错→403、无 token→401"的既有语义（契约 §4 + 现有测试）。
"""
from fastapi import Request

from core.config import settings
from core.errors import CORE_UNAUTHORIZED, CORE_FORBIDDEN
from core.key_store import verify_key


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):]
    return ""


def require_admin(request: Request):
    """管理接口鉴权：需 Admin Token（bootstrap 或库里 scope=admin 的 key）。"""
    token = _bearer(request)
    if not token:
        raise CORE_UNAUTHORIZED()
    if token == settings.admin_token:
        request.state.key_id = None  # bootstrap 凭据无 key_id
        return True
    key_id = verify_key(token, scope="admin")
    if key_id is not None:
        request.state.key_id = key_id
        return True
    raise CORE_FORBIDDEN()


def check_api_key(request: Request):
    """客户端接口鉴权：需有效 API Key（bootstrap 或库里 scope=client 的 key）。"""
    token = _bearer(request)
    if not token:
        raise CORE_UNAUTHORIZED()
    if token == settings.initial_api_key:
        request.state.key_id = None
        return True
    key_id = verify_key(token, scope="client")
    if key_id is not None:
        request.state.key_id = key_id
        return True
    raise CORE_FORBIDDEN()
