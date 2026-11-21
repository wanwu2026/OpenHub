"""崩溃上报存储：只存设备哈希（不存明文设备号），状态 new/resolved。"""
import time

from sqlalchemy import text

from core.db import engine


class CrashStore:
    def __init__(self):
        with engine.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS crash_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                device_hash TEXT NOT NULL,
                stacktrace TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new'
            )"""))

    def add(self, app_id, device_hash, stacktrace):
        with engine.begin() as c:
            cur = c.exec_driver_sql(
                "INSERT INTO crash_reports (app_id,device_hash,stacktrace,created_at,status) "
                "VALUES (?,?,?,?,'new')",
                (app_id, device_hash, stacktrace, int(time.time() * 1000)),
            )
            return cur.lastrowid

    def recent_count(self, device_hash, window_ms):
        with engine.begin() as c:
            row = c.exec_driver_sql(
                "SELECT COUNT(*) FROM crash_reports WHERE device_hash=? AND created_at>?",
                (device_hash, int(time.time() * 1000) - window_ms),
            ).fetchone()
        return row[0]

    def query(self, app_id=None, status=None, limit=100, offset=0):
        clauses, params = [], []
        if app_id:
            clauses.append("app_id=?")
            params.append(app_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT id,app_id,device_hash,substr(stacktrace,1,500),created_at,status "
               f"FROM crash_reports{where} ORDER BY id DESC LIMIT ? OFFSET ?")
        params += [min(limit, 500), offset]
        with engine.begin() as c:
            rows = c.exec_driver_sql(sql, tuple(params)).fetchall()
        return [dict(id=r[0], app_id=r[1], device_hash=r[2], stacktrace=r[3],
                     created_at=r[4], status=r[5]) for r in rows]

    def resolve(self, report_id):
        with engine.begin() as c:
            cur = c.exec_driver_sql(
                "UPDATE crash_reports SET status='resolved' WHERE id=?", (report_id,))
            return cur.rowcount > 0
