"""chat 插件存储：会话、成员、消息。"""
import hashlib
import secrets

from sqlalchemy import text

from core.db import engine
from core.models import now_ms


def _conv_id_direct(uid1: int, uid2: int) -> str:
    """单聊会话 ID 由两用户 id 排序后哈希，保证两人得到同一个 conv_id。"""
    a, b = sorted((uid1, uid2))
    return "d_" + hashlib.sha256(f"{a}:{b}".encode()).hexdigest()[:24]


def ensure_direct(uid1: int, uid2: int) -> str:
    if uid1 == uid2:
        raise ValueError("不能和自己单聊")
    cid = _conv_id_direct(uid1, uid2)
    with engine.begin() as c:
        row = c.exec_driver_sql("SELECT id FROM chat_conversations WHERE id=?", (cid,)).fetchone()
        if not row:
            c.exec_driver_sql(
                "INSERT INTO chat_conversations (id,type,name,owner_id,created_at) "
                "VALUES (?,?,?,?,?)", (cid, "direct", "", 0, now_ms()))
        for uid in (uid1, uid2):
            m = c.exec_driver_sql(
                "SELECT id FROM chat_members WHERE conv_id=? AND user_id=?", (cid, uid)).fetchone()
            if not m:
                c.exec_driver_sql(
                    "INSERT INTO chat_members (conv_id,user_id,last_read_id,joined_at) "
                    "VALUES (?,?,0,?)", (cid, uid, now_ms()))
    return cid


def create_group(owner_id: int, name: str, member_ids: list[int]) -> str:
    name = (name or "").strip()
    if len(name) < 1 or len(name) > 64:
        raise ValueError("群名需 1-64 字符")
    cid = "g_" + secrets.token_hex(12)
    members = set(member_ids) | {owner_id}
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO chat_conversations (id,type,name,owner_id,created_at) VALUES (?,?,?,?,?)",
            (cid, "group", name, owner_id, now_ms()))
        for uid in members:
            c.exec_driver_sql(
                "INSERT INTO chat_members (conv_id,user_id,last_read_id,joined_at) "
                "VALUES (?,?,0,?)", (cid, uid, now_ms()))
    return cid


def add_message(cid: str, sender_id: int, kind: str, content: str) -> int:
    with engine.begin() as c:
        cur = c.exec_driver_sql(
            "INSERT INTO chat_messages (conv_id,sender_id,kind,content,created_at) "
            "VALUES (?,?,?,?,?)", (cid, sender_id, kind, content, now_ms()))
        return cur.lastrowid


def is_member(cid: str, uid: int) -> bool:
    with engine.begin() as c:
        return c.exec_driver_sql(
            "SELECT id FROM chat_members WHERE conv_id=? AND user_id=?", (cid, uid)).fetchone() is not None


def list_conversations(uid: int) -> list[dict]:
    with engine.begin() as c:
        rows = c.exec_driver_sql(
            "SELECT c.id,c.type,c.name,c.owner_id,m.last_read_id "
            "FROM chat_members m JOIN chat_conversations c ON c.id=m.conv_id "
            "WHERE m.user_id=? ORDER BY c.created_at DESC", (uid,)).fetchall()
    out = []
    for r in rows:
        cid, typ, name, owner, last_read = r
        with engine.begin() as c:
            last = c.exec_driver_sql(
                "SELECT id,content,kind,sender_id,created_at FROM chat_messages "
                "WHERE conv_id=? ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
            unread = c.exec_driver_sql(
                "SELECT COUNT(*) FROM chat_messages WHERE conv_id=? AND id>?",
                (cid, last_read)).fetchone()[0]
        out.append(dict(id=cid, type=typ, name=name, owner_id=owner, unread=unread,
                        last_message=dict(id=last[0], content=last[1], kind=last[2],
                                          sender_id=last[3], created_at=last[4]) if last else None))
    return out


def list_messages(cid: str, uid: int, limit: int = 50, before_id: int | None = None) -> list[dict]:
    if not is_member(cid, uid):
        raise PermissionError("不是会话成员")
    with engine.begin() as c:
        if before_id:
            rows = c.exec_driver_sql(
                "SELECT id,sender_id,kind,content,created_at FROM chat_messages "
                "WHERE conv_id=? AND id<? ORDER BY id DESC LIMIT ?",
                (cid, before_id, min(limit, 200))).fetchall()
        else:
            rows = c.exec_driver_sql(
                "SELECT id,sender_id,kind,content,created_at FROM chat_messages "
                "WHERE conv_id=? ORDER BY id DESC LIMIT ?", (cid, min(limit, 200))).fetchall()
    return [dict(id=r[0], sender_id=r[1], kind=r[2], content=r[3], created_at=r[4])
            for r in reversed(rows)]  # 时间正序给客户端


def mark_read(cid: str, uid: int, msg_id: int) -> bool:
    with engine.begin() as c:
        cur = c.exec_driver_sql(
            "UPDATE chat_members SET last_read_id=? WHERE conv_id=? AND user_id=? AND last_read_id<?",
            (msg_id, cid, uid, msg_id))
        return cur.rowcount > 0


def conversation_type(cid: str) -> str | None:
    with engine.begin() as c:
        row = c.exec_driver_sql("SELECT type FROM chat_conversations WHERE id=?", (cid,)).fetchone()
    return row[0] if row else None
