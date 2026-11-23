"""内核数据存储：Device / AppConfig / Artifact 的 CRUD。
用 SQLAlchemy Core（exec_driver_sql + ? 占位符），与插件 store 风格一致。
"""
import hashlib
import json
import time

from sqlalchemy import text

from core.db import engine
from core.models import now_ms


def _device_hash(device_id: str) -> str:
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()


# ---------- Device ----------
def register_device(device_id: str, product: str = "default", meta: dict | None = None) -> dict:
    dh = _device_hash(device_id)
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    with engine.begin() as c:
        row = c.exec_driver_sql("SELECT id FROM devices WHERE device_hash=?", (dh,)).fetchone()
        now = now_ms()
        if row:
            c.exec_driver_sql("UPDATE devices SET last_seen=?, meta_json=?, product=? WHERE id=?",
                              (now, meta_json, product, row[0]))
            did = row[0]
        else:
            cur = c.exec_driver_sql(
                "INSERT INTO devices (device_hash,product,created_at,last_seen,meta_json) "
                "VALUES (?,?,?,?,?)", (dh, product, now, now, meta_json))
            did = cur.lastrowid
    return {"id": did, "device_hash": dh[:12] + "...", "product": product, "last_seen": now}


def list_devices(limit: int = 100, offset: int = 0, product: str | None = None) -> list[dict]:
    with engine.begin() as c:
        if product:
            rows = c.exec_driver_sql(
                "SELECT device_hash,product,created_at,last_seen,meta_json FROM devices "
                "WHERE product=? ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (product, min(limit, 500), offset)).fetchall()
        else:
            rows = c.exec_driver_sql(
                "SELECT device_hash,product,created_at,last_seen,meta_json FROM devices "
                "ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (min(limit, 500), offset)).fetchall()
    return [dict(device_hash=r[0][:12] + "...", product=r[1], created_at=r[2],
                 last_seen=r[3], meta=r[4]) for r in rows]


def device_count() -> int:
    with engine.begin() as c:
        return c.execute(text("SELECT COUNT(*) FROM devices")).fetchone()[0]


# ---------- AppConfig ----------
def save_config(product: str, enabled: bool, rollout: int, force: bool,
                config: dict, signature: str) -> dict:
    cfg_json = json.dumps(config, ensure_ascii=False)
    now = now_ms()
    with engine.begin() as c:
        row = c.exec_driver_sql("SELECT id FROM app_configs WHERE product=?", (product,)).fetchone()
        if row:
            c.exec_driver_sql(
                "UPDATE app_configs SET enabled=?,rollout_percent=?,force_update=?,"
                "config_json=?,signature=?,updated_at=? WHERE id=?",
                (int(enabled), rollout, int(force), cfg_json, signature, now, row[0]))
        else:
            c.exec_driver_sql(
                "INSERT INTO app_configs (product,enabled,rollout_percent,force_update,"
                "config_json,signature,updated_at) VALUES (?,?,?,?,?,?,?)",
                (product, int(enabled), rollout, int(force), cfg_json, signature, now))
    return {"product": product, "enabled": bool(enabled), "rollout_percent": rollout,
            "force_update": bool(force), "signature": signature,
            "signature_algo": "RSA-SHA256", "updated_at": now}


def get_config(product: str) -> dict | None:
    with engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT enabled,rollout_percent,force_update,config_json,signature,updated_at "
            "FROM app_configs WHERE product=?", (product,)).fetchone()
    if not row:
        return None
    return dict(enabled=bool(row[0]), rollout_percent=row[1], force_update=bool(row[2]),
                config=json.loads(row[3]), signature=row[4], updated_at=row[5])


def list_configs() -> list[dict]:
    with engine.begin() as c:
        rows = c.exec_driver_sql(
            "SELECT product,enabled,rollout_percent,force_update,updated_at "
            "FROM app_configs ORDER BY updated_at DESC").fetchall()
    return [dict(product=r[0], enabled=bool(r[1]), rollout_percent=r[2],
                 force_update=bool(r[3]), updated_at=r[4]) for r in rows]


def config_count() -> int:
    with engine.begin() as c:
        return c.execute(text("SELECT COUNT(*) FROM app_configs")).fetchone()[0]


# ---------- Artifact ----------
def add_artifact(product, version, version_code, channel, signer_fingerprint,
                 sha256, filename, size) -> dict:
    now = now_ms()
    with engine.begin() as c:
        cur = c.exec_driver_sql(
            "INSERT INTO artifacts (product,version,version_code,channel,signer_fingerprint,"
            "sha256,filename,size,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (product, version, version_code, channel, signer_fingerprint,
             sha256, filename, size, now))
    return {"id": cur.lastrowid, "product": product, "version": version}


def latest_artifact(product: str, channel: str = "stable") -> dict | None:
    with engine.begin() as c:
        row = c.exec_driver_sql(
            "SELECT version,version_code,channel,signer_fingerprint,sha256,filename,size,created_at "
            "FROM artifacts WHERE product=? AND channel=? ORDER BY version_code DESC,id DESC LIMIT 1",
            (product, channel)).fetchone()
    if not row:
        return None
    return dict(version=row[0], version_code=row[1], channel=row[2],
                signer_fingerprint=row[3], sha256=row[4], filename=row[5],
                size=row[6], created_at=row[7])


def list_artifacts(product: str | None = None) -> list[dict]:
    with engine.begin() as c:
        if product:
            rows = c.exec_driver_sql(
                "SELECT id,product,version,version_code,channel,signer_fingerprint,sha256,filename,size,created_at "
                "FROM artifacts WHERE product=? ORDER BY id DESC LIMIT 200", (product,)).fetchall()
        else:
            rows = c.exec_driver_sql(
                "SELECT id,product,version,version_code,channel,signer_fingerprint,sha256,filename,size,created_at "
                "FROM artifacts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(id=r[0], product=r[1], version=r[2], version_code=r[3], channel=r[4],
                 signer_fingerprint=r[5], sha256=r[6], filename=r[7], size=r[8],
                 created_at=r[9]) for r in rows]


def artifact_count() -> int:
    with engine.begin() as c:
        return c.execute(text("SELECT COUNT(*) FROM artifacts")).fetchone()[0]
