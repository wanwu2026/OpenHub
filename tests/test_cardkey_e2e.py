"""CardKey 插件端到端测试：复用原 demo-backend 测试链，跑在 OpenHub 真实服务上。

覆盖：健康检查 → 鉴权 → 发卡 → 验卡 → 验签 → 一机一码 → 重复激活 → 封禁 → 无效卡密。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 用临时目录隔离数据，避免污染仓库 data/
_TMP = tempfile.TemporaryDirectory()
os.environ["OPENHUB_DATA_DIR"] = _TMP.name
os.environ["OPENHUB_ADMIN_TOKEN"] = "test-admin-token"
os.environ["OPENHUB_INITIAL_API_KEY"] = "ohk_test-key"
os.environ["OPENHUB_ENABLED_PLUGINS"] = "cardkey"

# 必须在导入 app 前设置好私钥路径（generate 到临时目录）
from plugins.cardkey import signing  # noqa: E402

_PUB = signing.gen_keypair(_TMP.name)
_PRIV = str(Path(_TMP.name) / "private.pem")
os.environ["OPENHUB_CARDKEY_PRIVATE_KEY"] = _PRIV
os.environ["OPENHUB_CARDKEY_PRODUCT"] = "demo_app"

from fastapi.testclient import TestClient  # noqa: E402

import core.config as cfg  # noqa: E402
cfg.settings.cardkey_private_key = _PRIV
cfg.settings.cardkey_product = "demo_app"
cfg.settings.admin_token = "test-admin-token"
cfg.settings.initial_api_key = "ohk_test-key"

from app import app  # noqa: E402

ADMIN = "test-admin-token"
client = TestClient(app)


class TestCardKeyPlugin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 触发 startup（建表、加载插件）
        with TestClient(app) as c:
            c.get("/api/v1/core/health")

    def test_health_lists_cardkey(self):
        r = client.get("/api/v1/core/health").json()
        self.assertTrue(r["ok"])
        self.assertIn("cardkey", r["data"]["plugins"])

    def test_issue_requires_admin(self):
        r = client.post("/api/v1/cardkey/issue", json={"serial": 1},
                        headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 403)

    def test_full_flow(self):
        admin = {"Authorization": "Bearer " + ADMIN}

        # 1. 发卡（一机一码）
        issued = client.post("/api/v1/cardkey/issue", json={"serial": 1001, "max_activations": 1},
                             headers=admin).json()
        self.assertTrue(issued["ok"], issued)
        code = issued["data"]["code"]
        self.assertEqual(issued["data"]["serial"], 1001)

        # 2. 验卡成功，返回扁平 license（兼容例外）
        v = client.post("/api/v1/cardkey/verify",
                        json={"code": code, "device_id": "DEV-A", "product_id": "demo_app"}).json()
        self.assertTrue(v["ok"], v)
        lic = v["license"]

        # 3. 验证签名有效、设备绑定正确（用独立 signing 模块）
        parts = lic[5:].split("-")
        payload = signing.b32decode(parts[0])
        sig = signing.b32decode(parts[1])
        self.assertTrue(signing.verify_sig(payload, sig, _PUB))
        info = signing.parse_payload(payload)
        self.assertEqual(info["device"], "DEV-A")
        self.assertEqual(info["serial"], 1001)

        # 4. 换设备被拒（一机一码）
        v2 = client.post("/api/v1/cardkey/verify",
                         json={"code": code, "device_id": "DEV-B"}).json()
        self.assertFalse(v2["ok"])
        self.assertEqual(v2["reason"], "device_mismatch")

        # 5. 原设备可重复激活
        v3 = client.post("/api/v1/cardkey/verify",
                         json={"code": code, "device_id": "DEV-A"}).json()
        self.assertTrue(v3["ok"])

        # 6. 列卡（管理接口，包络格式 + 脱敏）
        codes = client.get("/api/v1/cardkey/codes", headers=admin).json()
        self.assertTrue(codes["ok"])
        self.assertTrue(any(c["code"].endswith("...") for c in codes["data"]["codes"]))

        # 7. 封禁后拒绝
        rv = client.post("/api/v1/cardkey/revoke", json={"code": code}, headers=admin).json()
        self.assertTrue(rv["ok"])
        v4 = client.post("/api/v1/cardkey/verify",
                         json={"code": code, "device_id": "DEV-A"}).json()
        self.assertFalse(v4["ok"])
        self.assertEqual(v4["reason"], "revoked")

    def test_invalid_code(self):
        v = client.post("/api/v1/cardkey/verify",
                        json={"code": "KVL1-BOGUS-BOGUS", "device_id": "X"}).json()
        self.assertFalse(v["ok"])
        self.assertEqual(v["reason"], "invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
