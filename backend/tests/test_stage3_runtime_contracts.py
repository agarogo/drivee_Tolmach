import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.tests.runtime_stubs import install_runtime_stubs

install_runtime_stubs()

from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.db import get_db
from app.main import app


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class FakeDb:
    def __init__(self, *, query_rows=None):
        self.query_rows = query_rows or []
        self.added = []

    def add(self, obj):
        self.added.append(obj)
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.utcnow()

    async def flush(self):
        for obj in self.added:
            if hasattr(obj, "id") and getattr(obj, "id", None) is None:
                obj.id = uuid4()
            if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.utcnow()
            if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
                obj.updated_at = datetime.utcnow()

    async def scalars(self, _stmt):
        return FakeScalarResult(self.query_rows)

    async def scalar(self, _stmt):
        return 0

    async def commit(self):
        return None

    async def refresh(self, obj):
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.utcnow()

    async def get(self, _model, _item_id):
        return None


class Stage3RuntimeContractsTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_continuity_exposes_anchor_answer_type_for_follow_up(self) -> None:
        from app.chat_context import build_chat_continuation_context

        chat_id = uuid4()
        query = SimpleNamespace(
            id=uuid4(),
            status="success",
            natural_text="show revenue by city",
            resolved_request_json={"metric": "revenue", "dimensions": ["city"], "filters": {}, "period": {"label": "last 30 days"}},
            interpretation_json={},
            semantic_terms_json=[{"term": "revenue"}],
            answer_type_key="comparison_top",
        )

        context = await build_chat_continuation_context(
            FakeDb(query_rows=[query]),
            user_id=uuid4(),
            chat_id=chat_id,
            question="and by driver?",
        )

        self.assertTrue(context.context_json["follow_up_applied"])
        self.assertEqual(context.context_json["anchor_answer_type"], "comparison_top")
        self.assertIn("Previous metric: revenue", context.effective_question)

    async def test_type_zero_help_path_skips_sql_generation_and_execution(self) -> None:
        from app.ai.orchestrator import run_query_workflow
        from app.ai.types import RetrievalResult
        from app.semantic.service import (
            SemanticCatalog,
            SemanticDimensionDefinition,
            SemanticMetricDefinition,
        )

        catalog = SemanticCatalog(
            metrics={
                "revenue": SemanticMetricDefinition(
                    metric_key="revenue",
                    business_name="Revenue",
                    description="Revenue metric",
                    sql_expression_template="SUM({base_alias}.price_order_local)",
                    grain="order",
                    allowed_dimensions=["city", "day"],
                    allowed_filters=["city", "day"],
                    default_chart="bar",
                    safety_tags=["finance"],
                )
            },
            dimensions={
                "city": SemanticDimensionDefinition(
                    dimension_key="city",
                    business_name="City",
                    table_name="dim.cities",
                    column_name="city_name",
                    join_path="JOIN dim.cities {dimension_alias} ON {dimension_alias}.city_id = {base_alias}.city_id",
                    data_type="string",
                )
            },
            filters={},
        )
        retrieval = RetrievalResult(semantic_terms=[], templates=[], examples=[], planner_candidates=[])
        db = FakeDb()
        user = SimpleNamespace(id=uuid4(), role="user", email="user@drivee.example")

        with (
            patch(
                "app.ai.orchestrator.build_chat_continuation_context",
                new=AsyncMock(return_value=SimpleNamespace(effective_question="what does status_tender mean", context_json={})),
            ),
            patch("app.ai.orchestrator.load_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("app.ai.orchestrator.retrieve_context", new=AsyncMock(return_value=retrieval)),
            patch("app.ai.orchestrator.extract_intent_stage", new=AsyncMock()) as extract_intent,
            patch("app.ai.orchestrator.sql_plan_draft_stage", new=AsyncMock()) as sql_plan_draft,
            patch("app.ai.orchestrator.validate_sql", new=AsyncMock()) as validate_sql,
            patch("app.ai.orchestrator.execute_answer_plan", new=AsyncMock()) as execute_answer_plan,
        ):
            query = await run_query_workflow(db, user, "what does status_tender mean", None)

        self.assertEqual(query.status, "success")
        self.assertEqual(query.answer_type_key, "chat_help")
        self.assertEqual(query.generated_sql, "")
        self.assertEqual(query.corrected_sql, "")
        self.assertFalse(query.answer_envelope_json["sql_visibility"]["show_sql_panel"])
        extract_intent.assert_not_called()
        sql_plan_draft.assert_not_called()
        validate_sql.assert_not_called()
        execute_answer_plan.assert_not_called()

    async def test_require_owned_schedule_loads_schedule_once_and_checks_report_ownership(self) -> None:
        from app.api import require_owned_schedule

        schedule_id = uuid4()
        report_id = uuid4()
        fake_schedule = SimpleNamespace(id=schedule_id, report_id=report_id)
        fake_user = SimpleNamespace(id=uuid4())

        class OwnedScheduleDb(FakeDb):
            async def get(self, model, item_id):
                self.loaded = (model.__name__, item_id)
                return fake_schedule

        db = OwnedScheduleDb()
        with patch("app.api.require_owned_report", new=AsyncMock(return_value=SimpleNamespace(id=report_id))) as require_report:
            item = await require_owned_schedule(db, schedule_id, fake_user)

        self.assertEqual(item.id, schedule_id)
        self.assertEqual(db.loaded[1], schedule_id)
        require_report.assert_awaited_once()


class Stage3ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

        async def override_get_db():
            yield FakeDb()

        async def current_user():
            return SimpleNamespace(id=uuid4(), role="user", email="user@drivee.example")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = current_user

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_delete_chat_endpoint_returns_cleanup_counts(self) -> None:
        chat_id = uuid4()
        fake_chat = SimpleNamespace(id=chat_id, user_id=uuid4(), title="Revenue by city")
        with (
            patch("app.api.require_owned_chat", new=AsyncMock(return_value=fake_chat)),
            patch(
                "app.api.delete_chat_with_related_data",
                new=AsyncMock(
                    return_value={
                        "messages": 6,
                        "queries": 2,
                        "clarifications": 1,
                        "events": 5,
                        "guardrail_logs": 3,
                        "reports_detached": 1,
                        "query_audits_detached": 2,
                    }
                ),
            ),
        ):
            response = self.client.delete(f"/api/chats/{chat_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["deleted"])
        self.assertEqual(payload["deleted_related_counts"]["messages"], 6)


if __name__ == "__main__":
    unittest.main()
