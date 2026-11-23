"""终端用户体系：注册/登录/会话。
密码用 PBKDF2-HMAC-SHA256 + 随机盐（Python 标准库 hashlib，零依赖），绝不存明文。
会话 token 用 secrets.token_urlsafe，只存哈希，带过期。
"""
import hashlib
import hmac
import secrets
import time

from sqlalchemy import text

from core.db import engine
from core.models import now_ms

PBKDF2_ROUNDS = 210_000     # OWASP 2023 建议 SHA256 ≥ 210k
SESSION_TTL_MS = 7 * 24 * 3600 * 1000   # 7 天


def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), dk.hex()


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        _, computed = _hash_password(password, salt)
        return hmac.compare_digest(computed, hash_hex)
    except (ValueError, TypeError):
        return False


def _session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- 注册 / 登录 ----------
def register(username: str, password: str, email: str = "") -> dict:
    username = (username or "").strip()
    if len(username) < 3 or len(username) > 32:
        raise ValueError("用户名需 3-32 字符")
    if len(password) < 6:
        raise ValueError("密码至少 6 位")
    salt_hex, hash_hex = _hash_password(password)
    with engine.begin() as c:
        exists = c.exec_driver_sql("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            raise ValueError("用户名已存在")
        cur = c.exec_driver_sql(
            "INSERT INTO users (username,email,password_salt,password_hash,created_at,status) "
            "VALUES (?,?,?,?,?,1)", (username, email, salt_hex, hash_hex, now_ms()))
        uid = cur.lastrowid
    return {"id": uid, "username": username, "email": email}


def login(username: str, password: str) -> str | None:
    """成功返回 session token（明文，只此一次），失败返回 None。"""
    with engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT id,password_salt,password_hash,status FROM users WHERE username=?",
            (username,)).fetchone()
    if not row or row[3] != 1:
        return None
    if not _verify_password(password, row[1], row[2]):
        return None
    token = secrets.token_urlsafe(32)
    with engine.begin() as c:
        c.exec_driver_sql(
            "INSERT INTO sessions (user_id,token_hash,created_at,expires_at) VALUES (?,?,?,?)",
            (row[0], _session_hash(token), now_ms(), now_ms() + SESSION_TTL_MS))
    return token


def user_by_token(token: str) -> dict | None:
    """按 session token 查用户；同时检查过期与禁用。"""
    if not token:
        return None
    with engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT u.id,u.username,u.email,u.status,s.expires_at "
            "FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
            (_session_hash(token),)).fetchone()
    if not row or row[3] != 1 or row[4] < now_ms():
        return None
    return {"id": row[0], "username": row[1], "email": row[2]}


def logout(token: str) -> bool:
    with engine.begin() as c:
        cur = c.exec_driver_sql("DELETE FROM sessions WHERE token_hash=?", (_session_hash(token),))
        return cur.rowcount > 0


def user_by_id(uid: int) -> dict | None:
    with engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT id,username,email,status FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "email": row[2], "status": row[3]}


def list_users(limit: int = 100, offset: int = 0) -> list[dict]:
    with engine.begin() as c:
        rows = c.exec_driver_sql(
            "SELECT id,username,email,status,created_at FROM users "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (min(limit, 500), offset)).fetchall()
    return [dict(id=r[0], username=r[1], email=r[2], status=r[3], created_at=r[4]) for r in rows]


def set_user_status(uid: int, status: int) -> bool:
    with engine.begin() as c:
        cur = c.exec_driver_sql("UPDATE users SET status=? WHERE id=?", (status, uid))
        return cur.rowcount > 0
