"""内核数据模型：API Key 与审计日志。

安全约定：api_keys 只存 token 的 SHA-256 哈希，明文仅在创建时返回一次，
库里任何时刻都查不出原始凭据。审计表不记录 token 明文，只记匹配到的 key_id。
"""
import time

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


def now_ms() -> int:
    return int(time.time() * 1000)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="client")  # admin | client
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)
    revoked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
