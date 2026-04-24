import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.ai.answer_classifier import AnswerTypeDecision
from app.answer_contracts import AnswerTypeCode, AnswerTypeKey, ViewMode
from app.auth import get_current_user
from app.db import get_db
from app.main import app
from app.schemas import QueryOut


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class ApiDb:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [0])
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if hasattr(obj, "created_at") and getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()
        if hasattr(obj, "updated_at") and getattr(obj, "updated_at", None) is None:
            obj.updated_at = datetime.utcnow()

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = uuid4()

    async def scalar(self, _stmt):
        return self.scalar_values.pop(0) if self.scalar_values else 0

    async def scalars(self, _stmt):
        return FakeScalarResult([])

    async def get(self, _model, _item_id):
        return None


class CleanupDb(ApiDb):
    def __init__(self, query_ids, scalar_values):
        super().__init__(scalar_values=scalar_values)
        self.query_ids = query_ids
        self.executed = []
        self.deleted = []

    async def scalars(self, _stmt):
        return FakeScalarResult(self.query_ids)

    async def execute(self, statement):
        self.executed.append(str(statement))

    async def delete(self, obj):
        self.deleted.append(obj)


def make_query_out(chat_id, query_id=None, question="show revenue") -> QueryOut:
    now = datetime.utcnow()
    return QueryOut(
        id=query_id or uuid4(),
        chat_id=chat_id,
        natural_text=question,
        generated_sql="SELECT 1",
        corrected_sql="SELECT 1",
        confidence_score=95,
        confidence_band="high",
        status="success",
        block_reason="",
        interpretation={},
        resolved_request={},
        semantic_terms=[],
        sql_plan={},
        sql_explain_plan={},
        sql_explain_cost=1.0,
        confidence_reasons=[],
        ambiguity_flags=[],
        rows_returned=1,
        execution_ms=12,
        answer_type_code=5,
        answer_type_key="table",
        primary_view_mode="table",
        answer=None,
        chart_type="table_only",
        chart_spec={},
        result_snapshot=[{"city": "Tokyo"}],
        ai_answer="Tokyo row",
        error_message="",
        auto_fix_attempts=0,
        clarifications=[],
        events=[],
        guardrail_logs=[],
        created_at=now,
        updated_at=now,
    )


class Stage5ChatApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = ApiDb(scalar_values=[1])
        self.client = TestClient(app)
        self.user = SimpleNamespace(id=uuid4(), role="user", email="user@drivee.example")

        async def override_get_db():
            yield self.db

        async def current_user():
            return self.user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = current_user

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_run_query_endpoint_keeps_existing_chat_id(self) -> None:
        chat_id = uuid4()
        chat = SimpleNamespace(id=chat_id, title="Revenue by city", updated_at=datetime.utcnow())
        query_item = SimpleNamespace(
            id=uuid4(),
            ai_answer="Done.",
            result_snapshot=[{"city": "Tokyo"}],
            corrected_sql="SELECT 1",
            generated_sql="SELECT 1",
            status="success",
        )
        query_out = make_query_out(chat_id=chat_id, query_id=query_item.id, question="and by driver")

        with (
            patch("app.api.ensure_query_chat", new=AsyncMock(return_value=chat)),
            patch("app.api.run_query_workflow", new=AsyncMock(return_value=query_item)) as run_workflow,
            patch("app.api.query_to_out", new=AsyncMock(return_value=query_out)),
        ):
            response = self.client.post(
                "/queries/run",
                json={"question": "and by driver", "chat_id": str(chat_id)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chat_id"], str(chat_id))
        run_workflow.assert_awaited_once()
        self.assertEqual(run_workflow.await_args.args[3], chat_id)

    def test_delete_chat_endpoint_rejects_foreign_chat(self) -> None:
        chat_id = uuid4()

        with patch(
            "app.api.require_owned_chat",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Chat not found")),
        ):
            response = self.client.delete(f"/api/chats/{chat_id}")

        self.assertEqual(response.status_code, 404)


class Stage5ChatOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_require_owned_chat_rejects_foreign_chat(self) -> None:
        from app.api import require_owned_chat

        chat_id = uuid4()
        owner_id = uuid4()
        other_user = SimpleNamespace(id=uuid4())

        class OwnershipDb(ApiDb):
            async def get(self, _model, _item_id):
                return SimpleNamespace(id=chat_id, user_id=owner_id)

        with self.assertRaises(HTTPException) as captured:
            await require_owned_chat(OwnershipDb(), chat_id, other_user)

        self.assertEqual(captured.exception.status_code, 404)

    async def test_delete_chat_with_related_data_detaches_reports_and_audits(self) -> None:
        from app.api import delete_chat_with_related_data

        chat = SimpleNamespace(id=uuid4())
        query_ids = [uuid4(), uuid4()]
        db = CleanupDb(
            query_ids=query_ids,
            scalar_values=[
                6,  # messages
                2,  # clarifications
                4,  # events
                3,  # guardrail logs
                1,  # reports detached
                2,  # query audits detached
            ],
        )

        counts = await delete_chat_with_related_data(db, chat)
        executed = [statement.lower() for statement in db.executed]

        self.assertEqual(counts["messages"], 6)
        self.assertEqual(counts["reports_detached"], 1)
        self.assertEqual(counts["query_audits_detached"], 2)
        self.assertEqual(len(db.executed), 7)
        self.assertTrue(any("update app.reports" in statement for statement in executed))
        self.assertTrue(any("update app.query_execution_audit" in statement for statement in executed))
        self.assertTrue(any("delete from app.queries" in statement for statement in executed))
        self.assertEqual(db.deleted, [chat])


class Stage5ChatContinuityTests(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_uses_chat_history_context_before_classification(self) -> None:
        from app.ai.orchestrator import run_query_workflow

        chat_id = uuid4()
        user = SimpleNamespace(id=uuid4(), role="user", email="user@drivee.example")
        db = ApiDb()

        decision = AnswerTypeDecision(
            answer_type=AnswerTypeCode.CHAT_HELP,
            answer_type_key=AnswerTypeKey.CHAT_HELP,
            answer_type_label="Chat Help",
            reason="Help request",
            explanation="Non-SQL path",
            requires_sql=False,
            primary_view_mode=ViewMode.CHAT,
            confidence_score=99,
        )
        retrieval = SimpleNamespace(
            semantic_terms=[],
            templates=[],
            examples=[],
            planner_candidates=[],
            as_dict=lambda: {},
        )
        catalog = SimpleNamespace(prompt_summary=lambda: {})
        envelope = SimpleNamespace(
            answer_type=0,
            answer_type_key="chat_help",
            primary_view_mode="chat",
            model_dump=lambda mode="json": {
                "answer_type": 0,
                "answer_type_key": "chat_help",
                "primary_view_mode": "chat",
                "render_payload": {"kind": "chat_help", "message": "Help"},
                "switch_options": [],
                "compatibility_info": {
                    "compatible_view_modes": ["chat"],
                    "can_switch_without_requery": False,
                    "requery_required_for_views": ["number", "chart", "table", "report"],
                },
            },
            render_payload=SimpleNamespace(kind="chat_help"),
        )

        with (
            patch(
                "app.ai.orchestrator.build_chat_continuation_context",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        effective_question="what does status_tender mean\n\nConversation context",
                        context_json={"follow_up_applied": True, "anchor_answer_type": "chat_help"},
                    )
                ),
            ) as build_context,
            patch("app.ai.orchestrator.load_semantic_catalog", new=AsyncMock(return_value=catalog)),
            patch("app.ai.orchestrator.retrieve_context", new=AsyncMock(return_value=retrieval)),
            patch("app.ai.orchestrator.classify_answer_type", return_value=decision),
            patch("app.ai.orchestrator.build_answer_envelope", return_value=envelope),
            patch("app.ai.orchestrator.render_answer_text", return_value="Help response"),
            patch("app.ai.orchestrator.explain_interpretation", return_value={"why": "help"}),
            patch("app.ai.orchestrator._apply_answer_contract"),
        ):
            query = await run_query_workflow(db, user, "what does status_tender mean", chat_id)

        build_context.assert_awaited_once_with(
            db,
            user_id=user.id,
            chat_id=chat_id,
            question="what does status_tender mean",
        )
        self.assertEqual(query.chat_id, chat_id)
        self.assertEqual(query.status, "success")


if __name__ == "__main__":
    unittest.main()
