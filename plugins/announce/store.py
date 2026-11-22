"""公告存储：按 product 存公告，单条带服务端签名（客户端可验，防假公告）。

签名本体只含客户端可见的稳定字段（不含数据库自增 id），
客户端按同法重建字节即可验签——见 docs/API_CONTRACT.md §7.3。
"""
import time

from sqlalchemy import text

from core.db import engine


class AnnounceStore:
    def __init__(self):
        with engine.begin() as c:
            c.execute(text("""CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'info',
                force_popup INTEGER NOT NULL DEFAULT 0,
                published_at INTEGER NOT NULL,
                signature TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )"""))

    def publish(self, product, title, content, level, force_popup, published_at, signature):
        with engine.begin() as c:
            cur = c.exec_driver_sql(
                "INSERT INTO announcements "
                "(product,title,content,level,force_popup,published_at,signature,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (product, title, content, level, int(bool(force_popup)), published_at,
                 signature, int(time.time() * 1000)),
            )
            return cur.lastrowid

    def _row_dict(self, r):
        return dict(id=r[0], product=r[1], title=r[2], content=r[3], level=r[4],
                    force_popup=bool(r[5]), published_at=r[6], signature=r[7])

    def list(self, product=None, since=0, limit=100, offset=0):
        clauses, params = [], []
        if product:
            clauses.append("product=?")
            params.append(product)
        if since:
            clauses.append("published_at>?")
            params.append(since)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = ("SELECT id,product,title,content,level,force_popup,published_at,signature "
               f"FROM announcements{where} ORDER BY published_at DESC,id DESC LIMIT ? OFFSET ?")
        params += [min(limit, 500), offset]
        with engine.begin() as c:
            rows = c.exec_driver_sql(sql, tuple(params)).fetchall()
        return [self._row_dict(r) for r in rows]

    def get(self, notice_id):
        with engine.begin() as c:
            r = c.exec_driver_sql(
                "SELECT id,product,title,content,level,force_popup,published_at,signature "
                "FROM announcements WHERE id=?", (notice_id,),
            ).fetchone()
        return self._row_dict(r) if r else None
