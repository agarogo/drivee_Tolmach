from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth import get_current_user, require_admin
from app.db import get_db
from app.main import app


def sample_run_payload() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid4()),
        "schedule_id": None,
        "report_id": str(uuid4()),
        "report_version_id": None,
        "requested_by_user_id": None,
        "trigger_type": "manual",
        "status": "succeeded",
        "queued_at": now,
        "started_at": now,
        "finished_at": now,
        "next_retry_at": None,
        "retry_count": 0,
        "max_retries": 0,
        "retry_backoff_seconds": 0,
        "final_sql": "SELECT 1 LIMIT 1",
        "chart_type": "table_only",
        "chart_spec_json": {},
        "semantic_snapshot_json": {},
        "result_snapshot": [{"value": 1}],
        "execution_fingerprint": "abc123",
        "explain_plan_json": {},
        "explain_cost": 1.2,
        "validator_summary_json": {},
        "structured_error_json": {},
        "stack_trace": "",
        "attempts_json": [],
        "artifact_summary_json": [],
        "delivery_summary_json": [],
        "rows_returned": 1,
        "execution_ms": 12,
        "error_message": "",
        "ran_at": now,
        "artifacts": [],
        "deliveries": [],
    }


class ReportsSchedulerApiTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

        class FakeDb:
            async def commit(self):
                return None

            async def refresh(self, _item):
                return None

        async def override_get_db():
            yield FakeDb()

        async def current_user():
            return SimpleNamespace(id=uuid4(), role="user", email="user@drivee.example")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = current_user

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.client.close()

    def test_run_report_now_returns_run_payload(self) -> None:
        report_id = uuid4()
        fake_report = SimpleNamespace(id=report_id, report_id=report_id)
        fake_run = SimpleNamespace(id=uuid4())
        with (
            patch("app.api.require_owned_report", new=AsyncMock(return_value=fake_report)),
            patch("app.api.create_run_record", new=AsyncMock(return_value=fake_run)),
            patch("app.api.execute_report_run", new=AsyncMock(return_value=fake_run)),
            patch("app.api.run_to_out", new=AsyncMock(return_value=sample_run_payload())),
        ):
            response = self.client.post(f"/reports/{report_id}/run-now")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "succeeded")
        self.assertEqual(response.json()["rows_returned"], 1)

    def test_schedule_history_returns_recent_runs(self) -> None:
        schedule_id = uuid4()
        fake_schedule = SimpleNamespace(id=schedule_id, report_id=uuid4())
        with (
            patch("app.api.require_owned_schedule", new=AsyncMock(return_value=fake_schedule)),
            patch("app.api.list_report_runs", new=AsyncMock(return_value=[SimpleNamespace(id=uuid4())])),
            patch("app.api.run_to_out", new=AsyncMock(return_value=sample_run_payload())),
        ):
            response = self.client.get(f"/schedules/{schedule_id}/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["trigger_type"], "manual")

    def test_admin_scheduler_summary_requires_admin(self) -> None:
        async def deny_admin():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

        app.dependency_overrides[require_admin] = deny_admin
        response = self.client.get("/admin/scheduler/summary")
        self.assertEqual(response.status_code, 403)

    def test_admin_scheduler_summary_returns_payload(self) -> None:
        async def allow_admin():
            return SimpleNamespace(id=uuid4(), role="admin")

        app.dependency_overrides[require_admin] = allow_admin
        payload = {
            "worker_enabled": True,
            "queued_runs": 2,
            "running_runs": 1,
            "failed_runs": 0,
            "succeeded_runs_24h": 7,
            "due_schedules": 1,
            "retrying_runs": 1,
        }
        with patch("app.api.get_scheduler_summary", new=AsyncMock(return_value=payload)):
            response = self.client.get("/admin/scheduler/summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["queued_runs"], 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
