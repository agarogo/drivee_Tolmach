from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.db import get_db
from app.main import app


class QueryExecutionAdminApiTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

        async def override_get_db():
            yield None

        app.dependency_overrides[get_db] = override_get_db

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_query_execution_summary_requires_admin(self) -> None:
        async def deny_admin():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        app.dependency_overrides[require_admin] = deny_admin
        response = self.client.get("/admin/query-execution/summary")
        self.assertEqual(response.status_code, 403)

    def test_query_execution_cache_stats_endpoint_returns_payload(self) -> None:
        async def allow_admin():
            return SimpleNamespace(id=uuid4(), role="admin")

        app.dependency_overrides[require_admin] = allow_admin
        payload = {
            "cache_enabled": True,
            "ttl_seconds": 300,
            "total_entries": 2,
            "active_entries": 2,
            "expired_entries": 0,
            "total_hit_count": 4,
            "avg_row_count": 12.5,
            "recent_entries": [
                {
                    "fingerprint": "abc123",
                    "role": "admin",
                    "row_count": 10,
                    "hit_count": 2,
                    "expires_at": "2026-04-23T10:00:00",
                    "updated_at": "2026-04-23T09:55:00",
                    "sample_explain": {"node_type": "Limit"},
                }
            ],
        }
        with patch("app.api.get_query_cache_stats", new=AsyncMock(return_value=payload)):
            response = self.client.get("/admin/query-execution/cache")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_entries"], 2)
        self.assertEqual(response.json()["recent_entries"][0]["fingerprint"], "abc123")

    def test_query_execution_audits_endpoint_returns_rows(self) -> None:
        async def allow_admin():
            return SimpleNamespace(id=uuid4(), role="admin")

        app.dependency_overrides[require_admin] = allow_admin
        audit_id = uuid4()
        payload = [
            {
                "id": audit_id,
                "query_id": None,
                "fingerprint": "abc123",
                "role": "admin",
                "cache_hit": False,
                "execution_mode": "database",
                "row_count": 10,
                "execution_ms": 140,
                "explain_cost": 123.4,
                "status": "ok",
                "error_message": "",
                "details": {},
                "sample_explain": {"node_type": "Aggregate"},
                "created_at": "2026-04-23T09:55:00",
            }
        ]
        with patch("app.api.list_query_execution_audits", new=AsyncMock(return_value=payload)):
            response = self.client.get("/admin/query-execution/audits")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["fingerprint"], "abc123")


if __name__ == "__main__":
    import unittest

    unittest.main()
