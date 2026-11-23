"""chat 插件：WebSocket 实时消息 + REST（会话列表/历史/发送/建群/已读）。
鉴权：REST 用 session token（Bearer）；WebSocket 用 ?token= 查询参数。
连接管理用内存字典（单进程）；消息落库保证离线可补。
"""
import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from core import user_store
from core.errors import ok, CORE_VALIDATION, CORE_UNAUTHORIZED, CORE_NOT_FOUND
from core.plugin import Plugin
from plugins.chat import store as chat_store

router = APIRouter()

# conv_id -> set[WebSocket]
_connections: dict[str, set] = {}


def _user_from_request(request: Request) -> dict:
    h = request.headers.get("Authorization", "")
    token = h[7:] if h.startswith("Bearer ") else ""
    u = user_store.user_by_token(token)
    if not u:
        raise CORE_UNAUTHORIZED("请先登录或会话已过期")
    return u


async def _broadcast(cid: str, payload: dict):
    """向会话内所有连接广播；发送失败的连接移除。"""
    dead = []
    for ws in list(_connections.get(cid, set())):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.get(cid, set()).discard(ws)


# ---------- REST ----------
@router.get("/conversations")
def conversations(request: Request):
    u = _user_from_request(request)
    return ok({"conversations": chat_store.list_conversations(u["id"])}, request)


@router.post("/direct")
async def direct(request: Request):
    """与某用户开单聊，返回 conv_id（幂等）。"""
    u = _user_from_request(request)
    body = await request.json()
    try:
        other = int(body.get("user_id", 0))
    except (TypeError, ValueError):
        raise CORE_VALIDATION("user_id 需为整数")
    if not user_store.user_by_id(other):
        raise CORE_NOT_FOUND("目标用户不存在")
    try:
        cid = chat_store.ensure_direct(u["id"], other)
    except ValueError as exc:
        raise CORE_VALIDATION(str(exc))
    return ok({"conv_id": cid}, request)


@router.post("/groups")
async def create_group(request: Request):
    u = _user_from_request(request)
    body = await request.json()
    members = body.get("member_ids") or []
    if not isinstance(members, list):
        raise CORE_VALIDATION("member_ids 需为数组")
    try:
        mids = [int(x) for x in members]
    except (TypeError, ValueError):
        raise CORE_VALIDATION("member_ids 元素需为整数")
    try:
        cid = chat_store.create_group(u["id"], body.get("name", ""), mids)
    except ValueError as exc:
        raise CORE_VALIDATION(str(exc))
    return ok({"conv_id": cid}, request)


@router.get("/messages/{cid}")
def messages(cid: str, request: Request, limit: int = 50, before_id: int | None = None):
    u = _user_from_request(request)
    try:
        rows = chat_store.list_messages(cid, u["id"], limit, before_id)
    except PermissionError:
        raise CORE_UNAUTHORIZED("不是会话成员")
    return ok({"messages": rows}, request)


@router.post("/messages/{cid}")
async def send_message(cid: str, request: Request):
    """REST 发送（WebSocket 也走同一落库+广播逻辑）。"""
    u = _user_from_request(request)
    body = await request.json()
    kind = body.get("kind", "text")
    content = str(body.get("content", ""))
    if kind not in ("text", "image", "file") or not content:
        raise CORE_VALIDATION("kind 或 content 非法")
    if not chat_store.is_member(cid, u["id"]):
        raise CORE_UNAUTHORIZED("不是会话成员")
    mid = chat_store.add_message(cid, u["id"], kind, content)
    payload = {"type": "message", "id": mid, "conv_id": cid, "sender_id": u["id"],
               "kind": kind, "content": content}
    await _broadcast(cid, payload)
    return ok({"id": mid}, request)


@router.post("/messages/{cid}/read")
async def mark_read(cid: str, request: Request):
    u = _user_from_request(request)
    body = await request.json()
    try:
        msg_id = int(body.get("message_id", 0))
    except (TypeError, ValueError):
        raise CORE_VALIDATION("message_id 需为整数")
    chat_store.mark_read(cid, u["id"], msg_id)
    return ok({"ok": True}, request)


# ---------- WebSocket ----------
@router.websocket("/ws/{cid}")
async def ws_chat(ws: WebSocket, cid: str, token: str = ""):
    u = user_store.user_by_token(token)
    if not u:
        await ws.close(code=4401)
        return
    if not chat_store.is_member(cid, u["id"]):
        await ws.close(code=4403)
        return
    await ws.accept()
    _connections.setdefault(cid, set()).add(ws)
    try:
        # 连接成功先回填最近消息（离线补发）
        recent = chat_store.list_messages(cid, u["id"], limit=50)
        await ws.send_json({"type": "history", "conv_id": cid, "messages": recent})
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "JSON 格式错误"})
                continue
            kind = data.get("kind", "text")
            content = str(data.get("content", ""))
            if kind not in ("text", "image", "file") or not content:
                await ws.send_json({"type": "error", "message": "kind 或 content 非法"})
                continue
            mid = chat_store.add_message(cid, u["id"], kind, content)
            await _broadcast(cid, {"type": "message", "id": mid, "conv_id": cid,
                                   "sender_id": u["id"], "kind": kind, "content": content})
    except WebSocketDisconnect:
        pass
    finally:
        _connections.get(cid, set()).discard(ws)


class ChatPlugin(Plugin):
    name = "chat"
    version = "0.1.0"

    def routes(self) -> APIRouter:
        return router

    def on_enable(self):
        pass  # 表由 db.init_db() 幂等创建

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version, "implemented": True}
