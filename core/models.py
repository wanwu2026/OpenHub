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


class Device(Base):
    """设备注册：存 device_id 哈希（明文不落库）+ 产品 + 活跃时间。"""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    product: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="default")
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)
    last_seen: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)
    meta_json: Mapped[str] = mapped_column(String(2048), nullable=False, default="{}")


class AppConfig(Base):
    """配置下发：product 一份配置，含灰度/强制开关/配置 JSON 及服务端签名。"""
    __tablename__ = "app_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=100)  # 0-100 灰度
    force_update: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config_json: Mapped[str] = mapped_column(String(8192), nullable=False, default="{}")
    signature: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)


class Artifact(Base):
    """产物托管：APK/文件的版本、渠道、签名指纹与落盘路径。"""
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="default")
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="stable")
    signer_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    filename: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, default=now_ms)
