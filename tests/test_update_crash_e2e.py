"""update / crash 插件端到端测试。

隔离策略：pytest 同进程共享 settings 单例与 app，本文件绝不改全局
settings.enabled_plugins（那是 cardkey 测试 startup 依赖的）。只在各测试的
setUpClass 里临时设置凭据、显式构造独立 app（discover 传显式插件列表），
tearDownClass 恢复，避免污染其它测试模块。
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
_FP = "a" * 64  # 模拟 APK 签名证书 SHA-256


def _build_app() -> FastAPI:
    """独立 app：显式指定插件列表，绝不读全局 settings.enabled_plugins。"""
    db.init_db()
    app = FastAPI()

    @app.exception_handler(ApiError)
    async def handler(request, exc: ApiError):
        return exc.response(request)

    for name, plugin in discover(["update", "crash"]).items():
        plugin.on_enable()
        app.include_router(plugin.routes(), prefix=f"/api/v1/{name}")
    return app


ADMIN = {"Authorization": "Bearer test-admin-token"}
CLIENT = {"Authorization": "Bearer ohk_test-key"}


class _IsolatedApp(unittest.TestCase):
    """公共基类：临时设置凭据、建独立 app、退出时恢复全局 settings。"""

    @classmethod
    def setUpClass(cls):
        cls._saved = {}
        for k in ("update_private_key", "update_public_key_base64",
                  "admin_token", "initial_api_key"):
            cls._saved[k] = getattr(settings, k)
        settings.update_private_key = _PRIV
        settings.update_public_key_base64 = _PUB
        settings.admin_token = "test-admin-token"
        settings.initial_api_key = "ohk_test-key"
        cls.client = TestClient(_build_app())

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._saved.items():
            setattr(settings, k, v)


class TestUpdatePlugin(_IsolatedApp):
    def test_health_and_publish_check_verify(self):
        pub = self.client.post("/api/v1/update/publish", json={
            "product": "my_app", "version": "1.2.0", "version_code": 12,
            "signer_fingerprint": _FP, "apk_url": "https://cdn/app.apk",
            "sha256": "b" * 64, "notes": "修复若干问题",
        }, headers=ADMIN)
        self.assertTrue(pub.status_code == 200, pub.text)
        body = pub.json()
        self.assertTrue(body["ok"])

        # 客户端查更新（API Key）
        chk = self.client.get("/api/v1/update/check", params={"product": "my_app",
                              "current_version_code": 11}, headers=CLIENT).json()
        self.assertTrue(chk["ok"])
        self.assertTrue(chk["data"]["has_update"])
        m = chk["data"]["manifest"]
        self.assertEqual(m["version"], "1.2.0")
        self.assertEqual(m["signer_fingerprint"], _FP)
        # 清单签名可验（密钥是 update 私钥，与 cardkey 分开配置）
        from plugins.update.plugin import canonical
        self.assertTrue(signing.verify_sig(
            canonical(m), signing.b32decode(chk["data"]["manifest_signature"]), _PUB))

        # 无更新时 manifest 为空
        chk2 = self.client.get("/api/v1/update/check", params={"product": "my_app",
                               "current_version_code": 12}, headers=CLIENT).json()
        self.assertFalse(chk2["data"]["has_update"])
        self.assertIsNone(chk2["data"]["manifest"])

        # 服务端自检验签
        vf = self.client.get("/api/v1/update/verify/my_app", headers=ADMIN).json()
        self.assertTrue(vf["data"]["valid"])

    def test_publish_validates_fingerprint(self):
        r = self.client.post("/api/v1/update/publish", json={
            "product": "my_app", "version": "1.3.0", "signer_fingerprint": "short",
            "apk_url": "https://cdn/app.apk", "sha256": "b" * 64,
        }, headers=ADMIN)
        self.assertEqual(r.status_code, 422)

    def test_check_requires_api_key(self):
        r = self.client.get("/api/v1/update/check", params={"product": "my_app"})
        self.assertEqual(r.status_code, 401)


class TestCrashPlugin(_IsolatedApp):
    def test_report_redact_list_resolve(self):
        stack = ("java.lang.RuntimeException: user a@b.com phone 13800138000 "
                 "token Bearer abc123XYZ deadbeefdeadbeefdeadbeefdeadbeef")
        r = self.client.post("/api/v1/crash/report", json={
            "device_id": "DEVICE-SECRET", "app_id": "my_app", "stacktrace": stack,
        }, headers=CLIENT)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["accepted"], 1)

        reports = self.client.get("/api/v1/crash/reports", params={"app_id": "my_app"},
                                  headers=ADMIN).json()["data"]["reports"]
        row = next(x for x in reports if x["id"] == body["data"]["ids"][0])
        self.assertNotIn("a@b.com", row["stacktrace"])
        self.assertNotIn("13800138000", row["stacktrace"])
        self.assertIn("[EMAIL]", row["stacktrace"])
        self.assertIn("[PHONE]", row["stacktrace"])
        self.assertIn("[REDACTED]", row["stacktrace"])
        self.assertNotEqual(row["device_hash"], "DEVICE-SECRET")

        rv = self.client.post(f"/api/v1/crash/{row['id']}/resolve", headers=ADMIN).json()
        self.assertTrue(rv["ok"])
        resolved = self.client.get("/api/v1/crash/reports", params={"status": "resolved"},
                                   headers=ADMIN).json()["data"]["reports"]
        self.assertTrue(any(x["id"] == row["id"] for x in resolved))

    def test_batch_report(self):
        r = self.client.post("/api/v1/crash/report", json={
            "device_id": "DEVICE-BATCH", "app_id": "batch_app",
            "reports": [{"stacktrace": "err one"}, {"stacktrace": "err two"}],
        }, headers=CLIENT).json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["data"]["accepted"], 2)

    def test_rate_limit(self):
        items = [{"stacktrace": f"err {i}"} for i in range(25)]
        r = self.client.post("/api/v1/crash/report", json={
            "device_id": "DEVICE-FLOOD", "app_id": "flood_app", "reports": items,
        }, headers=CLIENT)
        self.assertEqual(r.status_code, 429)

    def test_report_requires_api_key(self):
        r = self.client.post("/api/v1/crash/report", json={"device_id": "X", "stacktrace": "e"})
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main(verbosity=2)
