"""管理看板聚合接口测试。隔离：不改全局 settings，独立 app 显式挂 core_routes。"""
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
from api.core_routes import router as core_router  # noqa: E402

ADMIN = {"Authorization": "Bearer overview-admin"}


class TestOverview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = settings.admin_token
        settings.admin_token = "overview-admin"
        db.init_db()
        app = FastAPI()

        @app.exception_handler(ApiError)
        async def handler(request, exc):
            return exc.response(request)

        app.include_router(core_router, prefix="/api/v1/core")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        settings.admin_token = cls._saved

    def test_overview_requires_admin(self):
        r = self.client.get("/api/v1/core/overview")
        self.assertEqual(r.status_code, 401)  # 无 token

    def test_overview_returns_all_buckets(self):
        r = self.client.get("/api/v1/core/overview", headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertTrue(d["ok"])
        for key in ("cardkey", "update", "announce", "crash", "errors"):
            self.assertIn(key, d["data"])
        self.assertIsInstance(d["data"]["errors"], dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
