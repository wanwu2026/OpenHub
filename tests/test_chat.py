"""chat 插件端到端测试：单聊/群聊/REST 消息/WebSocket 实时收发/成员鉴权。
隔离：临时 db + 重绑引擎，注册两个测试用户。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import db, user_store  # noqa: E402
from core.config import settings  # noqa: E402
from core.errors import ApiError  # noqa: E402
from api.auth_routes import router as auth_router  # noqa: E402
from plugins.chat.plugin import router as chat_router  # noqa: E402

_TMP = tempfile.TemporaryDirectory()


class TestChat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = {k: getattr(settings, k) for k in ("data_dir", "db_path")}
        settings.data_dir = Path(_TMP.name) / "data"
        settings.db_path = settings.data_dir / "openhub.db"
        from sqlalchemy import create_engine
        new_engine = create_engine(f"sqlite:///{settings.db_path}",
                                   connect_args={"check_same_thread": False})
        db.engine = new_engine
        user_store.engine = new_engine
        import plugins.chat.store as cs
        cs.engine = new_engine
        db.init_db()
        app = FastAPI()

        @app.exception_handler(ApiError)
        async def handler(request, exc):
            return exc.response(request)

        app.include_router(auth_router, prefix="/api/v1/auth")
        app.include_router(chat_router, prefix="/api/v1/chat")
        cls.client = TestClient(app)

        # 注册两个用户并登录
        cls.client.post("/api/v1/auth/register", json={"username": "user1", "password": "pass123"})
        cls.client.post("/api/v1/auth/register", json={"username": "user2", "password": "pass123"})
        cls.t1 = cls.client.post("/api/v1/auth/login", json={
            "username": "user1", "password": "pass123"}).json()["data"]["token"]
        cls.t2 = cls.client.post("/api/v1/auth/login", json={
            "username": "user2", "password": "pass123"}).json()["data"]["token"]
        cls.h1 = {"Authorization": "Bearer " + cls.t1}
        cls.h2 = {"Authorization": "Bearer " + cls.t2}

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            setattr(settings, k, v)

    def test_01_direct_conversation(self):
        # user1 查用户 id
        users = self.client.get("/api/v1/auth/users").json()  # 需 admin，改用 me
        # 用 me 拿 user1 id，user2 id 从注册返回推算（这里用 login 后 me）
        id1 = self.client.get("/api/v1/auth/me", headers=self.h1).json()["data"]["user"]["id"]
        # user2 的 id：从 user1 视角未知，直接查库（测试内）
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        id2 = con.execute("SELECT id FROM users WHERE username='user2'").fetchone()[0]
        con.close()
        r = self.client.post("/api/v1/chat/direct", json={"user_id": id2}, headers=self.h1)
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["data"]["conv_id"]
        self.assertTrue(cid.startswith("d_"))
        # user2 开同一个会话应得到同一 conv_id（幂等）
        r2 = self.client.post("/api/v1/chat/direct", json={"user_id": id1}, headers=self.h2)
        self.assertEqual(r2.json()["data"]["conv_id"], cid)
        # 会话列表双方都有
        self.assertTrue(any(c["id"] == cid for c in
                            self.client.get("/api/v1/chat/conversations", headers=self.h1).json()["data"]["conversations"]))
        self.assertTrue(any(c["id"] == cid for c in
                            self.client.get("/api/v1/chat/conversations", headers=self.h2).json()["data"]["conversations"]))

    def test_02_rest_send_and_history(self):
        id1 = self.client.get("/api/v1/auth/me", headers=self.h1).json()["data"]["user"]["id"]
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        id2 = con.execute("SELECT id FROM users WHERE username='user2'").fetchone()[0]
        con.close()
        cid = self.client.post("/api/v1/chat/direct", json={"user_id": id2}, headers=self.h1).json()["data"]["conv_id"]
        r = self.client.post(f"/api/v1/chat/messages/{cid}", json={
            "kind": "text", "content": "你好 中文"}, headers=self.h1)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["data"]["id"] > 0)
        hist = self.client.get(f"/api/v1/chat/messages/{cid}", headers=self.h2).json()["data"]["messages"]
        self.assertTrue(any(m["content"] == "你好 中文" for m in hist))
        # 未加入会话者看不到（建第三个用户）
        self.client.post("/api/v1/auth/register", json={"username": "user3", "password": "pass123"})
        t3 = self.client.post("/api/v1/auth/login", json={
            "username": "user3", "password": "pass123"}).json()["data"]["token"]
        r3 = self.client.get(f"/api/v1/chat/messages/{cid}",
                             headers={"Authorization": "Bearer " + t3})
        self.assertEqual(r3.status_code, 401)

    def test_03_group_chat(self):
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        ids = dict(con.execute("SELECT username,id FROM users").fetchall())
        con.close()
        r = self.client.post("/api/v1/chat/groups", json={
            "name": "测试群", "member_ids": [ids["user2"]]}, headers=self.h1)
        self.assertEqual(r.status_code, 200, r.text)
        cid = r.json()["data"]["conv_id"]
        self.assertTrue(cid.startswith("g_"))
        # 群成员可发消息
        r2 = self.client.post(f"/api/v1/chat/messages/{cid}", json={
            "content": "群里见"}, headers=self.h2)
        self.assertEqual(r2.status_code, 200)

    def test_04_websocket_realtime(self):
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        id2 = con.execute("SELECT id FROM users WHERE username='user2'").fetchone()[0]
        con.close()
        cid = self.client.post("/api/v1/chat/direct", json={"user_id": id2}, headers=self.h1).json()["data"]["conv_id"]
        # user2 建立 WS 连接
        with self.client.websocket_connect(f"/api/v1/chat/ws/{cid}?token={self.t2}") as ws2:
            history = ws2.receive_json()
            self.assertEqual(history["type"], "history")
            # user1 通过 REST 发消息，user2 应实时收到
            self.client.post(f"/api/v1/chat/messages/{cid}", json={"content": "实时测试"}, headers=self.h1)
            msg = ws2.receive_json()
            self.assertEqual(msg["type"], "message")
            self.assertEqual(msg["content"], "实时测试")

    def test_05_ws_auth_reject(self):
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        id2 = con.execute("SELECT id FROM users WHERE username='user2'").fetchone()[0]
        con.close()
        cid = self.client.post("/api/v1/chat/direct", json={"user_id": id2}, headers=self.h1).json()["data"]["conv_id"]
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect(f"/api/v1/chat/ws/{cid}?token=bad"):
                pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
