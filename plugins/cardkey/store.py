"""CardKey 状态机：从 demo-backend/backend/server.py 迁入。

状态机逻辑字节级保留（一机一码 / 激活次数 / 封禁 / 到期）；
存储改用 SQLAlchemy 内核引擎，但表结构字段与原 SQLite 一致，便于迁移旧库。
"""
import threading
import time

from sqlalchemy import text

from core.db import engine


class CardStore:
    """cards 表状态机，线程安全（锁 + 独立连接，沿用原实现的并发口径）。"""

    def __init__(self):
        self.lock = threading.Lock()
        self._init_table()

    def _init_table(self):
        with engine.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS cards (
                code TEXT PRIMARY KEY,
                device_id TEXT,
                max_activations INTEGER DEFAULT 1,
                activations INTEGER DEFAULT 0,
                expires_at INTEGER DEFAULT 0,
                serial INTEGER DEFAULT 1,
                revoked INTEGER DEFAULT 0,
                created_at INTEGER
            )"""))

    def add(self, code, expires_at, max_activations, serial):
        with self.lock, engine.begin() as c:
            c.exec_driver_sql("INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?)",
                      (code, "", max_activations, 0, expires_at, serial, 0,
                       int(time.time() * 1000)))

    def get(self, code):
        with engine.begin() as c:
            row = c.exec_driver_sql("SELECT device_id,max_activations,activations,expires_at,serial,revoked FROM cards WHERE code=?",
                            (code,)).fetchone()
        if not row:
            return None
        return dict(device_id=row[0], max_activations=row[1], activations=row[2],
                    expires_at=row[3], serial=row[4], revoked=row[5])

    def activate(self, code, device_id):
        """尝试激活：返回 (ok, reason, card_state)。逻辑与原实现一致。"""
        with self.lock, engine.begin() as c:
            row = c.exec_driver_sql("SELECT device_id,max_activations,activations,expires_at,serial,revoked FROM cards WHERE code=?",
                            (code,)).fetchone()
            if not row:
                return False, "invalid", None
            dev, max_a, acts, expires, serial, revoked = row
            if revoked:
                return False, "revoked", dict(device_id=dev, max_activations=max_a,
                    activations=acts, expires_at=expires, serial=serial, revoked=revoked)
            if expires and expires < int(time.time() * 1000):
                return False, "expired", None
            if dev and dev != device_id:
                return False, "device_mismatch", None
            if acts >= max_a and dev != device_id:
                return False, "used", None
            new_dev = dev or device_id
            c.exec_driver_sql("UPDATE cards SET device_id=?, activations=activations+1 WHERE code=?",
                      (new_dev, code))
            state = dict(device_id=new_dev, max_activations=max_a, activations=acts + 1,
                         expires_at=expires, serial=serial, revoked=0)
            return True, None, state

    def revoke(self, code):
        with self.lock, engine.begin() as c:
            cur = c.exec_driver_sql("UPDATE cards SET revoked=1 WHERE code=?", (code,))
            # SQLAlchemy CursorResult.rowcount 反映受影响行数
            return cur.rowcount > 0

    def list_codes(self):
        with engine.begin() as c:
            rows = c.execute(text("SELECT code,device_id,activations,max_activations,revoked FROM cards")).fetchall()
        return [dict(code=r[0][:16] + "...", device_id=r[1], activations=r[2],
                     max_activations=r[3], revoked=bool(r[4])) for r in rows]
