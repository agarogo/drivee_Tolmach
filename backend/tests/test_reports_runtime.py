import json
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.reports.artifacts import build_report_artifacts
from app.reports.scheduler import next_run_at, report_summary_from_rows
from app.reports.service import build_semantic_snapshot_from_query, normalize_delivery_targets


class ReportsRuntimeTests(TestCase):
    def test_normalize_delivery_targets_merges_legacy_and_structured_targets(self) -> None:
        payload = normalize_delivery_targets(
            ["ops@drivee.example", "OPS@drivee.example"],
            [
                {"channel": "email", "destination": "ops@drivee.example"},
                {"channel": "slack", "destination": "#analytics"},
            ],
        )

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["channel"], "email")
        self.assertEqual(payload[0]["destination"], "ops@drivee.example")
        self.assertEqual(payload[1]["channel"], "slack")

    def test_build_semantic_snapshot_from_query_uses_query_json_payloads(self) -> None:
        query = SimpleNamespace(
            id=uuid4(),
            interpretation_json={"metric": "revenue"},
            resolved_request_json={"metric": "revenue", "dimensions": ["city"]},
            semantic_terms_json=[{"term": "revenue"}],
            sql_plan_json={"metric": "revenue"},
        )

        snapshot = build_semantic_snapshot_from_query(query)

        self.assertEqual(snapshot["resolved_request"]["metric"], "revenue")
        self.assertEqual(snapshot["semantic_terms"][0]["term"], "revenue")
        self.assertIn("query_id", snapshot)

    def test_build_report_artifacts_writes_csv_json_and_html(self) -> None:
        rows = [
            {"city": "Moscow", "revenue": 1200},
            {"city": "Kazan", "revenue": 900},
        ]
        semantic_snapshot = {"metric": "revenue"}
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.reports.artifacts.settings.report_artifact_dir", temp_dir):
                artifacts = build_report_artifacts(
                    report_id="report-1",
                    run_id="run-1",
                    title="Revenue by city",
                    rows=rows,
                    chart_type="bar",
                    semantic_snapshot=semantic_snapshot,
                )
                self.assertEqual([item.artifact_type for item in artifacts], ["csv", "json", "html"])
                for artifact in artifacts:
                    path = Path(artifact.file_path)
                    self.assertTrue(path.exists())
                    self.assertGreater(artifact.file_size_bytes, 0)
                    self.assertEqual(len(artifact.checksum_sha256), 64)

                json_artifact = next(item for item in artifacts if item.artifact_type == "json")
                payload = json.loads(Path(json_artifact.file_path).read_text(encoding="utf-8"))
                self.assertEqual(payload["row_count"], 2)
                self.assertEqual(payload["semantic_snapshot"]["metric"], "revenue")

    def test_report_summary_from_rows_is_result_based_only(self) -> None:
        no_rows = report_summary_from_rows([])
        one_row = report_summary_from_rows([{"day": "2026-04-24", "orders_count": 42}])
        many_rows = report_summary_from_rows([{"city": "Moscow", "revenue": 1200}, {"city": "Kazan", "revenue": 900}])

        self.assertEqual(no_rows, "Query returned no rows.")
        self.assertEqual(one_row, "Query returned 1 rows across 2 columns.")
        self.assertEqual(many_rows, "Query returned 2 rows across 2 columns.")

    def test_next_run_at_daily_produces_future_timestamp(self) -> None:
        candidate = next_run_at("daily", None, None, None)
        self.assertGreater(candidate, datetime.utcnow())


if __name__ == "__main__":
    import unittest

    unittest.main()
