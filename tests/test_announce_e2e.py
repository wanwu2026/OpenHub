"""announce 插件端到端测试：发布→验签→列表→since 过滤→权限。

隔离策略同 test_update_crash_e2e：不改全局 settings.enabled_plugins，
显式 discover(["announce"])，临时设凭据，tearDown 恢复。
"""
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
from core.registry import discover  # noqa: E402
from plugins.cardkey import signing  # noqa: E402

_TMP = tempfile.TemporaryDirectory()
_PUB = signing.gen_keypair(_TMP.name)
_PRIV = str(Path(_TMP.name) / "private.pem")

ADMIN = {"Authorization": "Bearer announce-admin"}
CLIENT = {"Authorization": "Bearer ohk_announce-key"}


def _build_app() -> FastAPI:
    db.init_db()
    app = FastAPI()

    @app.exception_handler(ApiError)
    async def handler(request, exc: ApiError):
        return exc.response(request)

    for name, plugin in discover(["announce"]).items():
        plugin.on_enable()
        app.include_router(plugin.routes(), prefix=f"/api/v1/{name}")
    return app


class TestAnnouncePlugin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = {}
        for k in ("update_private_key", "update_public_key_base64",
                  "cardkey_private_key", "admin_token", "initial_api_key"):
            cls._saved[k] = getattr(settings, k)
        settings.update_private_key = _PRIV
        settings.update_public_key_base64 = _PUB
        settings.admin_token = "announce-admin"
        settings.initial_api_key = "ohk_announce-key"
        cls.client = TestClient(_build_app())

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            setattr(settings, k, v)

    def test_publish_list_verify_since(self):
        r = self.client.post("/api/v1/announce/publish", json={
            "product": "my_app", "title": "版本公告", "content": "新增更新检测功能",
            "level": "warn", "force_popup": True, "published_at": 1000,
        }, headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        nid = body["data"]["id"]
        sig = body["data"]["signature"]

        notices = self.client.get("/api/v1/announce/list",
                                  params={"product": "my_app"}, headers=CLIENT).json()
        self.assertTrue(notices["ok"])
        row = next(x for x in notices["data"]["notices"] if x["id"] == nid)
        self.assertEqual(row["title"], "版本公告")
        self.assertTrue(row["force_popup"])
        self.assertFalse(row["signature"] != sig)

        # 服务端自检验签（客户端按 canonical 重建字节即可验）
        vf = self.client.get(f"/api/v1/announce/verify/{nid}", headers=ADMIN).json()
        self.assertTrue(vf["data"]["valid"])

        # since 过滤
        later = self.client.get("/api/v1/announce/list",
                                params={"product": "my_app", "since": 1000},
                                headers=CLIENT).json()["data"]["notices"]
        self.assertFalse(any(x["id"] == nid for x in later))

    def test_publish_validates_level(self):
        r = self.client.post("/api/v1/announce/publish", json={
            "product": "my_app", "title": "x", "content": "y", "level": "critical",
        }, headers=ADMIN)
        self.assertEqual(r.status_code, 422)

    def test_list_requires_api_key(self):
        r = self.client.get("/api/v1/announce/list", params={"product": "my_app"})
        self.assertEqual(r.status_code, 401)

    def test_publish_requires_admin(self):
        r = self.client.post("/api/v1/announce/publish", json={
            "product": "my_app", "title": "x", "content": "y",
        }, headers=CLIENT)
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
