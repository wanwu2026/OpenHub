"""终端用户体系端到端测试：注册/登录/me/登出/管理端禁用。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import db  # noqa: E402
from core.config import settings  # noqa: E402
from core.errors import ApiError  # noqa: E402
from api.auth_routes import router as auth_router  # noqa: E402
from core import user_store  # noqa: E402

ADMIN = {"Authorization": "Bearer auth-admin"}
_TMP = tempfile.TemporaryDirectory()


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = {k: getattr(settings, k) for k in ("admin_token", "data_dir", "db_path")}
        settings.admin_token = "auth-admin"
        settings.data_dir = Path(_TMP.name) / "data"
        settings.db_path = settings.data_dir / "openhub.db"
        # 重新绑定引擎到新 db_path（db 模块在 import 时已建引擎）
        import importlib
        from core import db as dbmod
        from sqlalchemy import create_engine
        dbmod.engine = create_engine(f"sqlite:///{settings.db_path}",
                                     connect_args={"check_same_thread": False})
        # 让 user_store/kernel_store 等引用新引擎
        import core.user_store as us
        us.engine = dbmod.engine
        db.init_db()
        app = FastAPI()

        @app.exception_handler(ApiError)
        async def handler(request, exc):
            return exc.response(request)

        app.include_router(auth_router, prefix="/api/v1/auth")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            setattr(settings, k, v)

    def test_01_register_login_me(self):
        r = self.client.post("/api/v1/auth/register", json={
            "username": "alice", "password": "secret123", "email": "a@x.com"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("password", str(r.json()))  # 不回传密码哈希
        # 重复注册被拒
        r2 = self.client.post("/api/v1/auth/register", json={
            "username": "alice", "password": "secret123"})
        self.assertEqual(r2.status_code, 422)
        # 错误密码
        bad = self.client.post("/api/v1/auth/login", json={
            "username": "alice", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        # 正确登录
        good = self.client.post("/api/v1/auth/login", json={
            "username": "alice", "password": "secret123"})
        self.assertEqual(good.status_code, 200)
        token = good.json()["data"]["token"]
        self.assertTrue(token)
        # me
        me = self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"]["user"]["username"], "alice")
        # 登出后 me 失效
        self.client.post("/api/v1/auth/logout", headers={"Authorization": "Bearer " + token})
        me2 = self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
        self.assertEqual(me2.status_code, 401)

    def test_02_no_plaintext_password_in_db(self):
        import sqlite3
        con = sqlite3.connect(str(settings.db_path))
        row = con.execute("SELECT password_salt,password_hash FROM users WHERE username='alice'").fetchone()
        con.close()
        self.assertIsNotNone(row)
        self.assertNotEqual(row[1], "secret123")
        self.assertEqual(len(row[0]), 32)   # salt hex 16 bytes
        self.assertEqual(len(row[1]), 64)   # sha256 hex

    def test_03_admin_user_management(self):
        self.assertEqual(self.client.get("/api/v1/auth/users").status_code, 401)
        users = self.client.get("/api/v1/auth/users", headers=ADMIN).json()["data"]["users"]
        self.assertTrue(any(u["username"] == "alice" for u in users))
        uid = next(u["id"] for u in users if u["username"] == "alice")
        r = self.client.post(f"/api/v1/auth/users/{uid}/disable", headers=ADMIN)
        self.assertEqual(r.status_code, 200)
        # 禁用后登录失败
        bad = self.client.post("/api/v1/auth/login", json={
            "username": "alice", "password": "secret123"})
        self.assertEqual(bad.status_code, 401)
        self.client.post(f"/api/v1/auth/users/{uid}/enable", headers=ADMIN)

    def test_04_short_password_rejected(self):
        r = self.client.post("/api/v1/auth/register", json={
            "username": "bob", "password": "123"})
        self.assertEqual(r.status_code, 422)

    def test_05_login_rate_limit(self):
        # 连续 5 次错误密码后锁定
        for _ in range(5):
            r = self.client.post("/api/v1/auth/login", json={
                "username": "bob", "password": "wrong"})
            self.assertEqual(r.status_code, 401)
        locked = self.client.post("/api/v1/auth/login", json={
            "username": "bob", "password": "wrong"})
        self.assertEqual(locked.status_code, 429)
        user_store.record_login_success("bob")  # 清理，避免影响其他测试


if __name__ == "__main__":
    unittest.main(verbosity=2)
