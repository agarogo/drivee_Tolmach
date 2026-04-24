"""Add production-like report runs, artifacts, deliveries, and scheduler fields.

Revision ID: 20260424_0008
Revises: 20260423_0007
Create Date: 2026-04-24 14:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260424_0008"
down_revision: Union[str, Sequence[str], None] = "20260423_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB
UUID = postgresql.UUID


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("semantic_snapshot_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column("reports", sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default="1"), schema="app")
    op.add_column("reports", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.add_column("reports", sa.Column("last_run_status", sa.String(length=32), nullable=False, server_default="never"), schema="app")
    op.create_index("ix_app_reports_last_run_status", "reports", ["last_run_status"], unique=False, schema="app")

    op.add_column(
        "report_versions",
        sa.Column("chart_spec_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column(
        "report_versions",
        sa.Column("semantic_snapshot_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )

    op.add_column("schedules", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"), schema="app")
    op.add_column(
        "schedules",
        sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="300"),
        schema="app",
    )
    op.add_column("schedules", sa.Column("last_error_message", sa.Text(), nullable=False, server_default=""), schema="app")
    op.add_column("schedules", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True), schema="app")

    op.alter_column("report_recipients", "email", existing_type=sa.String(length=255), nullable=True, schema="app")
    op.add_column("report_recipients", sa.Column("channel", sa.String(length=20), nullable=False, server_default="email"), schema="app")
    op.add_column("report_recipients", sa.Column("destination", sa.String(length=255), nullable=False, server_default=""), schema="app")
    op.add_column(
        "report_recipients",
        sa.Column("config_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column("report_recipients", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), schema="app")
    op.add_column("report_recipients", sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.create_index("ix_app_report_recipients_channel", "report_recipients", ["channel"], unique=False, schema="app")
    op.create_index("ix_app_report_recipients_destination", "report_recipients", ["destination"], unique=False, schema="app")
    op.create_index("ix_app_report_recipients_is_active", "report_recipients", ["is_active"], unique=False, schema="app")

    op.alter_column("schedule_runs", "schedule_id", existing_type=UUID(as_uuid=True), nullable=True, schema="app")
    op.add_column("schedule_runs", sa.Column("report_version_id", UUID(as_uuid=True), nullable=True), schema="app")
    op.add_column("schedule_runs", sa.Column("requested_by_user_id", UUID(as_uuid=True), nullable=True), schema="app")
    op.add_column("schedule_runs", sa.Column("trigger_type", sa.String(length=20), nullable=False, server_default="manual"), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        schema="app",
    )
    op.add_column("schedule_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.add_column("schedule_runs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.add_column("schedule_runs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True), schema="app")
    op.add_column("schedule_runs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"), schema="app")
    op.add_column("schedule_runs", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("retry_backoff_seconds", sa.Integer(), nullable=False, server_default="0"),
        schema="app",
    )
    op.add_column("schedule_runs", sa.Column("final_sql", sa.Text(), nullable=False, server_default=""), schema="app")
    op.add_column("schedule_runs", sa.Column("chart_type", sa.String(length=32), nullable=False, server_default="table_only"), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("chart_spec_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column(
        "schedule_runs",
        sa.Column("semantic_snapshot_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column(
        "schedule_runs",
        sa.Column("result_snapshot", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="app",
    )
    op.add_column("schedule_runs", sa.Column("execution_fingerprint", sa.String(length=64), nullable=False, server_default=""), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("explain_plan_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column("schedule_runs", sa.Column("explain_cost", sa.Numeric(14, 2), nullable=False, server_default="0"), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("validator_summary_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column(
        "schedule_runs",
        sa.Column("structured_error_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="app",
    )
    op.add_column("schedule_runs", sa.Column("stack_trace", sa.Text(), nullable=False, server_default=""), schema="app")
    op.add_column(
        "schedule_runs",
        sa.Column("attempts_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="app",
    )
    op.add_column(
        "schedule_runs",
        sa.Column("artifact_summary_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="app",
    )
    op.add_column(
        "schedule_runs",
        sa.Column("delivery_summary_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="app",
    )
    op.create_foreign_key("fk_app_schedule_runs_report_version", "schedule_runs", "report_versions", ["report_version_id"], ["id"], source_schema="app", referent_schema="app")
    op.create_foreign_key("fk_app_schedule_runs_requested_by_user", "schedule_runs", "users", ["requested_by_user_id"], ["id"], source_schema="app", referent_schema="app")
    op.create_index("ix_app_schedule_runs_report_version_id", "schedule_runs", ["report_version_id"], unique=False, schema="app")
    op.create_index("ix_app_schedule_runs_requested_by_user_id", "schedule_runs", ["requested_by_user_id"], unique=False, schema="app")
    op.create_index("ix_app_schedule_runs_trigger_type", "schedule_runs", ["trigger_type"], unique=False, schema="app")
    op.create_index("ix_app_schedule_runs_queued_at", "schedule_runs", ["queued_at"], unique=False, schema="app")
    op.create_index("ix_app_schedule_runs_next_retry_at", "schedule_runs", ["next_retry_at"], unique=False, schema="app")
    op.create_index("ix_app_schedule_runs_execution_fingerprint", "schedule_runs", ["execution_fingerprint"], unique=False, schema="app")

    op.create_table(
        "report_artifacts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False, server_default="application/octet-stream"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("metadata_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["report_id"], ["app.reports.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["app.schedule_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index("ix_app_report_artifacts_report_id", "report_artifacts", ["report_id"], unique=False, schema="app")
    op.create_index("ix_app_report_artifacts_run_id", "report_artifacts", ["run_id"], unique=False, schema="app")
    op.create_index("ix_app_report_artifacts_artifact_type", "report_artifacts", ["artifact_type"], unique=False, schema="app")
    op.create_index("ix_app_report_artifacts_created_at", "report_artifacts", ["created_at"], unique=False, schema="app")

    op.create_table(
        "report_deliveries",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("recipient_id", UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("adapter_key", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_message_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("structured_error_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stack_trace", sa.Text(), nullable=False, server_default=""),
        sa.Column("details_json", JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["report_id"], ["app.reports.id"]),
        sa.ForeignKeyConstraint(["recipient_id"], ["app.report_recipients.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["app.schedule_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="app",
    )
    op.create_index("ix_app_report_deliveries_report_id", "report_deliveries", ["report_id"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_run_id", "report_deliveries", ["run_id"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_recipient_id", "report_deliveries", ["recipient_id"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_channel", "report_deliveries", ["channel"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_destination", "report_deliveries", ["destination"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_status", "report_deliveries", ["status"], unique=False, schema="app")
    op.create_index("ix_app_report_deliveries_created_at", "report_deliveries", ["created_at"], unique=False, schema="app")

    op.execute("UPDATE app.report_recipients SET destination = COALESCE(email, ''), channel = 'email' WHERE destination = ''")
    op.execute(
        """
        UPDATE app.report_versions rv
        SET chart_spec_json = COALESCE(r.chart_spec, '{}'::jsonb),
            semantic_snapshot_json = COALESCE(r.semantic_snapshot_json, '{}'::jsonb)
        FROM app.reports r
        WHERE r.id = rv.report_id
        """
    )
    op.execute(
        """
        UPDATE app.reports r
        SET latest_version_number = COALESCE(v.version_number, 1)
        FROM (
            SELECT report_id, MAX(version_number) AS version_number
            FROM app.report_versions
            GROUP BY report_id
        ) v
        WHERE v.report_id = r.id
        """
    )
    op.execute(
        """
        UPDATE app.schedule_runs sr
        SET status = CASE WHEN sr.status = 'ok' THEN 'succeeded' ELSE sr.status END,
            queued_at = COALESCE(sr.ran_at, CURRENT_TIMESTAMP),
            started_at = COALESCE(sr.ran_at, CURRENT_TIMESTAMP),
            finished_at = COALESCE(sr.ran_at, CURRENT_TIMESTAMP),
            trigger_type = CASE WHEN sr.schedule_id IS NULL THEN 'manual' ELSE 'schedule' END,
            final_sql = COALESCE(r.generated_sql, ''),
            chart_type = COALESCE(r.chart_type, 'table_only'),
            chart_spec_json = COALESCE(r.chart_spec, '{}'::jsonb),
            semantic_snapshot_json = COALESCE(r.semantic_snapshot_json, '{}'::jsonb),
            result_snapshot = COALESCE(r.result_snapshot, '[]'::jsonb),
            report_version_id = rv.id
        FROM app.reports r
        LEFT JOIN app.report_versions rv
          ON rv.report_id = r.id
         AND rv.version_number = (
             SELECT MAX(inner_rv.version_number)
             FROM app.report_versions inner_rv
             WHERE inner_rv.report_id = r.id
         )
        WHERE r.id = sr.report_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_app_report_deliveries_created_at", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_status", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_destination", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_channel", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_recipient_id", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_run_id", table_name="report_deliveries", schema="app")
    op.drop_index("ix_app_report_deliveries_report_id", table_name="report_deliveries", schema="app")
    op.drop_table("report_deliveries", schema="app")

    op.drop_index("ix_app_report_artifacts_created_at", table_name="report_artifacts", schema="app")
    op.drop_index("ix_app_report_artifacts_artifact_type", table_name="report_artifacts", schema="app")
    op.drop_index("ix_app_report_artifacts_run_id", table_name="report_artifacts", schema="app")
    op.drop_index("ix_app_report_artifacts_report_id", table_name="report_artifacts", schema="app")
    op.drop_table("report_artifacts", schema="app")

    op.drop_index("ix_app_schedule_runs_execution_fingerprint", table_name="schedule_runs", schema="app")
    op.drop_index("ix_app_schedule_runs_next_retry_at", table_name="schedule_runs", schema="app")
    op.drop_index("ix_app_schedule_runs_queued_at", table_name="schedule_runs", schema="app")
    op.drop_index("ix_app_schedule_runs_trigger_type", table_name="schedule_runs", schema="app")
    op.drop_index("ix_app_schedule_runs_requested_by_user_id", table_name="schedule_runs", schema="app")
    op.drop_index("ix_app_schedule_runs_report_version_id", table_name="schedule_runs", schema="app")
    op.drop_constraint("fk_app_schedule_runs_requested_by_user", "schedule_runs", schema="app", type_="foreignkey")
    op.drop_constraint("fk_app_schedule_runs_report_version", "schedule_runs", schema="app", type_="foreignkey")
    for column_name in [
        "delivery_summary_json",
        "artifact_summary_json",
        "attempts_json",
        "stack_trace",
        "structured_error_json",
        "validator_summary_json",
        "explain_cost",
        "explain_plan_json",
        "execution_fingerprint",
        "result_snapshot",
        "semantic_snapshot_json",
        "chart_spec_json",
        "chart_type",
        "final_sql",
        "retry_backoff_seconds",
        "max_retries",
        "retry_count",
        "next_retry_at",
        "finished_at",
        "started_at",
        "queued_at",
        "trigger_type",
        "requested_by_user_id",
        "report_version_id",
    ]:
        op.drop_column("schedule_runs", column_name, schema="app")
    op.alter_column("schedule_runs", "schedule_id", existing_type=UUID(as_uuid=True), nullable=False, schema="app")

    op.drop_index("ix_app_report_recipients_is_active", table_name="report_recipients", schema="app")
    op.drop_index("ix_app_report_recipients_destination", table_name="report_recipients", schema="app")
    op.drop_index("ix_app_report_recipients_channel", table_name="report_recipients", schema="app")
    for column_name in ["last_sent_at", "is_active", "config_json", "destination", "channel"]:
        op.drop_column("report_recipients", column_name, schema="app")
    op.alter_column("report_recipients", "email", existing_type=sa.String(length=255), nullable=False, schema="app")

    for column_name in ["last_error_at", "last_error_message", "retry_backoff_seconds", "max_retries"]:
        op.drop_column("schedules", column_name, schema="app")

    for column_name in ["semantic_snapshot_json", "chart_spec_json"]:
        op.drop_column("report_versions", column_name, schema="app")

    op.drop_index("ix_app_reports_last_run_status", table_name="reports", schema="app")
    for column_name in ["last_run_status", "last_run_at", "latest_version_number", "semantic_snapshot_json"]:
        op.drop_column("reports", column_name, schema="app")
