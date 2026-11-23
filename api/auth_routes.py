"""终端用户认证路由：注册 / 登录 / 当前用户 / 登出 / 管理端用户列表。
与 core 的 API Key（开发者凭据）是两套体系：这里用 session token（用户凭据）。
"""
from fastapi import APIRouter, Request

from core import user_store
from core.auth import require_admin
from core.errors import ok, CORE_VALIDATION, CORE_UNAUTHORIZED, CORE_NOT_FOUND, CORE_RATE_LIMITED

router = APIRouter()


def _bearer(request: Request) -> str:
    h = request.headers.get("Authorization", "")
    return h[7:] if h.startswith("Bearer ") else ""


def _require_user(request: Request) -> dict:
    u = user_store.user_by_token(_bearer(request))
    if not u:
        raise CORE_UNAUTHORIZED("请先登录或会话已过期")
    return u


@router.post("/register")
async def register(request: Request):
    body = await request.json()
    try:
        user = user_store.register(
            body.get("username", ""), body.get("password", ""), body.get("email", ""))
    except ValueError as exc:
        raise CORE_VALIDATION(str(exc))
    return ok(user, request)


@router.post("/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    remaining = user_store.login_lock_remaining(username)
    if remaining:
        raise CORE_RATE_LIMITED(f"尝试过多，请 {remaining} 秒后重试")
    token = user_store.login(username, body.get("password", ""))
    if not token:
        user_store.record_login_fail(username)
        raise CORE_UNAUTHORIZED("用户名或密码错误")
    user_store.record_login_success(username)
    return ok({"token": token, "token_type": "bearer"}, request)


@router.get("/me")
def me(request: Request):
    return ok({"user": _require_user(request)}, request)


@router.get("/user-by-name")
def user_by_name(request: Request, username: str):
    """终端用户按用户名查 id（发起单聊/建群用）。只回 id+用户名，不泄露哈希等。"""
    _require_user(request)  # 需登录
    with __import__("core.db", fromlist=["engine"]).engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT id,username FROM users WHERE username=? AND status=1", (username,)).fetchone()
    if not row:
        raise CORE_NOT_FOUND("用户不存在")
    return ok({"id": row[0], "username": row[1]}, request)


@router.post("/logout")
def logout(request: Request):
    user_store.logout(_bearer(request))
    return ok({"logged_out": True}, request)


# ---- 管理端：用户管理 ----
@router.get("/users")
def list_users(request: Request, limit: int = 100, offset: int = 0):
    require_admin(request)
    return ok({"users": user_store.list_users(limit, offset)}, request)


@router.post("/users/{uid}/disable")
def disable_user(uid: int, request: Request):
    require_admin(request)
    if not user_store.set_user_status(uid, 0):
        raise CORE_NOT_FOUND("用户不存在")
    # 禁用后其所有会话失效
    return ok({"id": uid, "status": 0}, request)


@router.post("/users/{uid}/enable")
def enable_user(uid: int, request: Request):
    require_admin(request)
    if not user_store.set_user_status(uid, 1):
        raise CORE_NOT_FOUND("用户不存在")
    return ok({"id": uid, "status": 1}, request)
