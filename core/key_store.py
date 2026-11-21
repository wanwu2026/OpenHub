"""API Key 管理：生成/吊销/列表/校验，只与哈希打交道。"""
import hashlib
import secrets

from sqlalchemy import select

from core.db import SessionLocal
from core.models import ApiKey, now_ms


def hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def generate_key(prefix: str = "ohk") -> str:
    """生成一个随机 key；明文只在调用处返回，不落库。"""
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def create_key(label: str, scope: str = "client") -> tuple[str, int]:
    """创建凭据，返回 (明文, id)。库里只存哈希。"""
    plain = generate_key()
    h = hash_key(plain)
    with SessionLocal() as db:
        row = ApiKey(key_hash=h, label=label or "", scope=scope,
                     created_at=now_ms(), revoked=0)
        db.add(row)
        db.commit()
        db.refresh(row)
        return plain, row.id


def verify_key(plain: str, scope: str | None = None) -> int | None:
    """校验明文 key，返回 key_id；无效返回 None。"""
    if not plain:
        return None
    h = hash_key(plain)
    with SessionLocal() as db:
        stmt = select(ApiKey).where(ApiKey.key_hash == h, ApiKey.revoked == 0)
        if scope:
            stmt = stmt.where(ApiKey.scope == scope)
        row = db.execute(stmt).scalar_one_or_none()
        return row.id if row else None


def list_keys() -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(select(ApiKey).order_by(ApiKey.id)).scalars().all()
        return [{
            "id": r.id,
            "label": r.label,
            "scope": r.scope,
            "created_at": r.created_at,
            "revoked": bool(r.revoked),
            "key_hash_prefix": r.key_hash[:12] + "...",  # 只露前缀，便于辨认
        } for r in rows]


def revoke_key(key_id: int) -> bool:
    with SessionLocal() as db:
        row = db.get(ApiKey, key_id)
        if not row:
            return False
        row.revoked = 1
        db.commit()
        return True
