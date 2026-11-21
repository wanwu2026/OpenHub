"""更新清单存储：按 product+channel 保留版本历史，取最新。"""
import time

from sqlalchemy import text

from core.db import engine


class UpdateStore:
    def __init__(self):
        with engine.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS update_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                version TEXT NOT NULL,
                version_code INTEGER NOT NULL,
                channel TEXT NOT NULL DEFAULT 'stable',
                signer_fingerprint TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                signature TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(product, channel, version_code)
            )"""))

    def publish(self, product, version, version_code, channel, signer_fingerprint,
                manifest_json, signature):
        with engine.begin() as c:
            c.exec_driver_sql(
                "INSERT OR REPLACE INTO update_manifests "
                "(product,version,version_code,channel,signer_fingerprint,manifest_json,signature,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (product, version, version_code, channel, signer_fingerprint,
                 manifest_json, signature, int(time.time() * 1000)),
            )

    def latest(self, product, channel="stable"):
        with engine.begin() as c:
            row = c.exec_driver_sql(
                "SELECT version,version_code,manifest_json,signature,signer_fingerprint,created_at "
                "FROM update_manifests WHERE product=? AND channel=? ORDER BY version_code DESC LIMIT 1",
                (product, channel),
            ).fetchone()
        if not row:
            return None
        return dict(version=row[0], version_code=row[1], manifest_json=row[2],
                    signature=row[3], signer_fingerprint=row[4], created_at=row[5])

    def list(self, product=None):
        with engine.begin() as c:
            if product:
                rows = c.exec_driver_sql(
                    "SELECT product,version,version_code,channel,signer_fingerprint,created_at "
                    "FROM update_manifests WHERE product=? ORDER BY version_code DESC",
                    (product,),
                ).fetchall()
            else:
                rows = c.exec_driver_sql(
                    "SELECT product,version,version_code,channel,signer_fingerprint,created_at "
                    "FROM update_manifests ORDER BY id DESC LIMIT 200"
                ).fetchall()
        return [dict(product=r[0], version=r[1], version_code=r[2], channel=r[3],
                     signer_fingerprint=r[4], created_at=r[5]) for r in rows]
