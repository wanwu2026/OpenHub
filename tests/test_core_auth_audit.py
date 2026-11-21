"""内核鉴权落库 + 审计测试。

注意：与 test_cardkey_e2e.py 共用同一进程内的 app 与数据库，key 列表/审计表
会累积其它测试产生的记录，因此断言只看"包含"与"语义"，不依赖空表。
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402
from core.config import settings  # noqa: E402

ADMIN = {"Authorization": "Bearer " + settings.admin_token}
client = TestClient(app)


class TestKeyManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TestClient(app) as c:
            c.get("/api/v1/core/health")

    def test_keys_require_admin(self):
        r = client.get("/api/v1/core/keys")
        self.assertEqual(r.status_code, 401)
        r = client.get("/api/v1/core/keys", headers={"Authorization": "Bearer wrong"})
        self.assertEqual(r.status_code, 403)

    def test_create_list_revoke_key(self):
        created = client.post("/api/v1/core/keys", json={"label": "sdk-x", "scope": "client"},
                              headers=ADMIN).json()
        self.assertTrue(created["ok"], created)
        key_id = created["data"]["id"]
        plain = created["data"]["key"]
        self.assertTrue(plain.startswith("ohk_"))

        # 明文 key 可用于客户端接口鉴权（库里查哈希命中）
        from core.auth import check_api_key
        from fastapi import Request
        # 直接查库函数验证，避免构造完整 Request
        from core.key_store import verify_key
        self.assertEqual(verify_key(plain, scope="client"), key_id)
        self.assertIsNone(verify_key(plain, scope="admin"))

        # 列表里有它，但不显示明文
        keys = client.get("/api/v1/core/keys", headers=ADMIN).json()["data"]["keys"]
        row = next(k for k in keys if k["id"] == key_id)
        self.assertEqual(row["label"], "sdk-x")
        self.assertNotIn(plain, str(row))
        self.assertTrue(row["key_hash_prefix"].endswith("..."))

        # 吊销后失效
        rv = client.post(f"/api/v1/core/keys/{key_id}/revoke", headers=ADMIN).json()
        self.assertTrue(rv["ok"])
        self.assertIsNone(verify_key(plain, scope="client"))

    def test_revoke_nonexistent(self):
        r = client.post("/api/v1/core/keys/999999/revoke", headers=ADMIN)
        self.assertEqual(r.status_code, 404)


class TestAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TestClient(app) as c:
            c.get("/api/v1/core/health")

    def test_audit_records_requests(self):
        # 制造一条带 request_id 的请求
        rid = "req_audit_test"
        client.get("/api/v1/core/health", headers={"X-Request-ID": rid})
        data = client.get("/api/v1/core/audit", headers=ADMIN).json()
        self.assertTrue(data["ok"], data)
        events = data["data"]["events"]
        self.assertTrue(any(e["request_id"] == rid and e["path"].endswith("/health")
                            for e in events))

    def test_audit_requires_admin(self):
        r = client.get("/api/v1/core/audit")
        self.assertEqual(r.status_code, 401)

    def test_audit_path_filter(self):
        data = client.get("/api/v1/core/audit", params={"path": "/api/v1/cardkey"},
                          headers=ADMIN).json()
        self.assertTrue(data["ok"])
        for e in data["data"]["events"]:
            self.assertTrue(e["path"].startswith("/api/v1/cardkey"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
