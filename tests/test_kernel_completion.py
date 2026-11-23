"""内核补全接口端到端测试：devices / config / artifacts / latest。
隔离：临时数据目录 + 临时私钥，独立 app 只挂 core_routes。
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
from api.core_routes import router as core_router  # noqa: E402
from plugins.cardkey import signing  # noqa: E402

ADMIN = {"Authorization": "Bearer kernel-admin"}
CLIENT = {"Authorization": "Bearer ohk-kernel-client"}
_TMP = tempfile.TemporaryDirectory()
_PUB = signing.gen_keypair(_TMP.name)
_PRIV = str(Path(_TMP.name) / "private.pem")


class TestKernelCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._saved = {k: getattr(settings, k) for k in
                      ("admin_token", "initial_api_key", "data_dir", "update_private_key")}
        settings.admin_token = "kernel-admin"
        settings.initial_api_key = "ohk-kernel-client"
        settings.data_dir = Path(_TMP.name) / "data"
        settings.update_private_key = _PRIV
        db.init_db()
        app = FastAPI()

        @app.exception_handler(ApiError)
        async def handler(request, exc):
            return exc.response(request)

        app.include_router(core_router, prefix="/api/v1/core")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            setattr(settings, k, v)

    def test_01_device_register_hash_and_upsert(self):
        r = self.client.post("/api/v1/core/devices", json={
            "device_id": "REAL-DEVICE-SECRET", "product": "chat_app",
            "meta": {"os": "android"}}, headers=CLIENT)
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()["data"]
        self.assertNotIn("REAL-DEVICE-SECRET", str(d))  # 明文不回显
        self.assertIn("device_hash", d)
        # 再注册一次不报错（upsert）
        r2 = self.client.post("/api/v1/core/devices", json={
            "device_id": "REAL-DEVICE-SECRET", "product": "chat_app"}, headers=CLIENT)
        self.assertEqual(r2.status_code, 200)
        # 管理列表只有哈希
        rows = self.client.get("/api/v1/core/devices", headers=ADMIN).json()["data"]["devices"]
        self.assertTrue(any(x["product"] == "chat_app" for x in rows))
        self.assertFalse(any("REAL-DEVICE-SECRET" in str(x) for x in rows))

    def test_02_config_sign_and_verify(self):
        body = {"enabled": True, "rollout_percent": 50, "force_update": False,
                "config": {"motd": "欢迎 中文", "feature_x": True}}
        r = self.client.post("/api/v1/core/config/chat_app", json=body, headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        # 客户端拉取（API Key）
        got = self.client.get("/api/v1/core/config/chat_app", headers=CLIENT).json()["data"]
        self.assertTrue(got["signed"])
        self.assertEqual(got["config"]["motd"], "欢迎 中文")
        # 验签：用规范 JSON 重建字节（与 core_routes._config_sign_bytes 同法）
        import json as _json
        from api.core_routes import _config_sign_bytes
        raw = _config_sign_bytes("chat_app", True, 50, False, got["config"])
        self.assertTrue(signing.verify_sig(raw, signing.b32decode(got["signature"]), _PUB))

    def test_03_artifact_upload_latest_download(self):
        payload = b"FAKE-APK-BYTES-" + b"x" * 100
        r = self.client.post("/api/v1/core/artifacts", data={
            "product": "chat_app", "version": "1.2.0", "version_code": "12",
            "channel": "stable", "signer_fingerprint": "a" * 64,
        }, files={"file": ("app.apk", payload, "application/vnd.android.package-archive")},
            headers=ADMIN)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["data"]["sha256"])
        # latest 客户端可读，含指纹
        latest = self.client.get("/api/v1/core/artifacts/latest?product=chat_app",
                                 headers=CLIENT).json()["data"]["artifact"]
        self.assertEqual(latest["version"], "1.2.0")
        self.assertEqual(latest["signer_fingerprint"], "a" * 64)
        # 下载内容一致
        dl = self.client.get(f"/api/v1/core/artifacts/download/{r.json()['data']['id']}",
                             headers=CLIENT)
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(dl.content, payload)

    def test_04_auth_boundaries(self):
        self.assertEqual(self.client.get("/api/v1/core/config/chat_app").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/core/devices", headers=CLIENT).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/core/configs", headers=ADMIN).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/core/artifacts", headers=ADMIN).status_code, 200)

    def test_05_config_rollout_validation(self):
        r = self.client.post("/api/v1/core/config/x", json={
            "rollout_percent": 150}, headers=ADMIN)
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
