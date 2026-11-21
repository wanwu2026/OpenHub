"""审计事件：写入与查询。记录请求方法/路径/状态/key_id，绝不记 token 明文。"""
from sqlalchemy import desc, select

from core.db import SessionLocal
from core.models import AuditEvent, now_ms


def record(request_id: str, method: str, path: str, status: int, key_id: int | None = None) -> None:
    with SessionLocal() as db:
        db.add(AuditEvent(
            request_id=request_id or "req_local",
            method=method,
            path=path[:512],
            status=status,
            key_id=key_id,
            created_at=now_ms(),
        ))
        db.commit()


def query(limit: int = 100, offset: int = 0, path_prefix: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        stmt = select(AuditEvent).order_by(desc(AuditEvent.id))
        if path_prefix:
            stmt = stmt.where(AuditEvent.path.startswith(path_prefix))
        stmt = stmt.limit(min(limit, 500)).offset(offset)
        rows = db.execute(stmt).scalars().all()
        return [{
            "id": r.id,
            "request_id": r.request_id,
            "method": r.method,
            "path": r.path,
            "status": r.status,
            "key_id": r.key_id,
            "created_at": r.created_at,
        } for r in rows]
