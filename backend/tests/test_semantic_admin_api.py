from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth import require_admin
from app.db import get_db
from app.main import app


class SemanticAdminApiTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

        async def override_get_db():
            yield None

        app.dependency_overrides[get_db] = override_get_db

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_admin_metrics_endpoint_requires_admin(self) -> None:
        async def deny_admin():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        app.dependency_overrides[require_admin] = deny_admin
        response = self.client.get("/admin/semantic/metrics")
        self.assertEqual(response.status_code, 403)

    def test_admin_metrics_endpoint_lists_catalog(self) -> None:
        async def allow_admin():
            return SimpleNamespace(id=uuid4(), role="admin")

        app.dependency_overrides[require_admin] = allow_admin
        row = SimpleNamespace(
            id=uuid4(),
            metric_key="revenue",
            business_name="Выручка",
            description="Revenue metric.",
            sql_expression_template="SUM({base_alias}.price_order_local)",
            grain="order",
            allowed_dimensions_json=["city", "day"],
            allowed_filters_json=["city", "day"],
            default_chart="bar",
            safety_tags_json=["finance"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with patch("app.api.semantic_repository.list_metric_catalog_entries", new=AsyncMock(return_value=[row])):
            response = self.client.get("/admin/semantic/metrics")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["metric_key"], "revenue")
        self.assertEqual(payload[0]["allowed_dimensions"], ["city", "day"])


if __name__ == "__main__":
    import unittest

    unittest.main()
