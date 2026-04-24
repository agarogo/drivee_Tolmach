"""Create production-like PostgreSQL schema.

Revision ID: 20260423_0001
Revises:
Create Date: 2026-04-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS tolmach")

    op.create_table(
        "cities",
        sa.Column("city_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("city_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_cities_country", "cities", ["country"])
    op.create_index("ix_cities_is_active", "cities", ["is_active"])

    op.create_table(
        "drivers",
        sa.Column("driver_id", sa.String(length=32), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Numeric(3, 2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_trips", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.city_id"]),
        sa.PrimaryKeyConstraint("driver_id"),
    )
    op.create_index("ix_drivers_city_id", "drivers", ["city_id"])
    op.create_index("ix_drivers_status", "drivers", ["status"])

    op.create_table(
        "clients",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_orders", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.city_id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_clients_city_id", "clients", ["city_id"])
    op.create_index("ix_clients_is_active", "clients", ["is_active"])

    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("tender_id", sa.String(length=32), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("driver_id", sa.String(length=32), nullable=False),
        sa.Column("offset_hours", sa.Integer(), nullable=False),
        sa.Column("status_order", sa.String(length=32), nullable=False),
        sa.Column("status_tender", sa.String(length=32), nullable=False),
        sa.Column("order_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tender_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("driverdone_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clientcancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drivercancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_modified_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_before_accept_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_in_meters", sa.Integer(), nullable=False),
        sa.Column("duration_in_seconds", sa.Integer(), nullable=False),
        sa.Column("price_order_local", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_tender_local", sa.Numeric(10, 2), nullable=False),
        sa.Column("price_start_local", sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.city_id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.driver_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["clients.user_id"]),
        sa.PrimaryKeyConstraint("order_id", "tender_id"),
    )
    op.create_index("ix_orders_city_id", "orders", ["city_id"])
    op.create_index("ix_orders_driver_id", "orders", ["driver_id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_order_timestamp", "orders", ["order_timestamp"])
    op.create_index("ix_orders_tender_timestamp", "orders", ["tender_timestamp"])
    op.create_index("ix_orders_status_order", "orders", ["status_order"])
    op.create_index("ix_orders_status_tender", "orders", ["status_tender"])

    op.create_table(
        "users",
        sa.Column("id", UUID, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferences", JSONB(), nullable=False),
        sa.Column("notification_settings", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        schema="tolmach",
    )
    op.create_index("ix_users_email", "users", ["email"], schema="tolmach")
    op.create_index("ix_users_role", "users", ["role"], schema="tolmach")
    op.create_index("ix_users_is_active", "users", ["is_active"], schema="tolmach")

    op.create_table(
        "invites",
        sa.Column("id", UUID, nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("used_by", UUID, nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["tolmach.users.id"]),
        sa.ForeignKeyConstraint(["used_by"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        schema="tolmach",
    )
    op.create_index("ix_invites_code", "invites", ["code"], schema="tolmach")
    op.create_index("ix_invites_email", "invites", ["email"], schema="tolmach")
    op.create_index("ix_invites_is_used", "invites", ["is_used"], schema="tolmach")

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("device_hint", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], schema="tolmach")

    op.create_table(
        "chats",
        sa.Column("id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["tolmach.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_chats_user_id", "chats", ["user_id"], schema="tolmach")

    op.create_table(
        "messages",
        sa.Column("id", UUID, nullable=False),
        sa.Column("chat_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["tolmach.chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_messages_chat_id", "messages", ["chat_id"], schema="tolmach")
    op.create_index("ix_messages_created_at", "messages", ["created_at"], schema="tolmach")

    op.create_table(
        "queries",
        sa.Column("id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("chat_id", UUID, nullable=True),
        sa.Column("natural_text", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("corrected_sql", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("confidence_band", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("block_reason", sa.Text(), nullable=False),
        sa.Column("interpretation_json", JSONB(), nullable=False),
        sa.Column("semantic_terms_json", JSONB(), nullable=False),
        sa.Column("sql_plan_json", JSONB(), nullable=False),
        sa.Column("confidence_reasons_json", JSONB(), nullable=False),
        sa.Column("ambiguity_flags_json", JSONB(), nullable=False),
        sa.Column("rows_returned", sa.Integer(), nullable=False),
        sa.Column("execution_ms", sa.Integer(), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("result_snapshot", JSONB(), nullable=False),
        sa.Column("chart_spec", JSONB(), nullable=False),
        sa.Column("ai_answer", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("auto_fix_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["tolmach.chats.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_queries_user_id", "queries", ["user_id"], schema="tolmach")
    op.create_index("ix_queries_chat_id", "queries", ["chat_id"], schema="tolmach")
    op.create_index("ix_queries_status", "queries", ["status"], schema="tolmach")
    op.create_index("ix_queries_confidence_band", "queries", ["confidence_band"], schema="tolmach")
    op.create_index("ix_queries_created_at", "queries", ["created_at"], schema="tolmach")

    op.create_table(
        "query_clarifications",
        sa.Column("id", UUID, nullable=False),
        sa.Column("query_id", UUID, nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options_json", JSONB(), nullable=False),
        sa.Column("chosen_option", sa.Text(), nullable=False),
        sa.Column("freeform_answer", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["query_id"], ["tolmach.queries.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_query_clarifications_query_id", "query_clarifications", ["query_id"], schema="tolmach")

    op.create_table(
        "query_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("query_id", UUID, nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["tolmach.queries.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_query_events_query_id", "query_events", ["query_id"], schema="tolmach")
    op.create_index("ix_query_events_step_name", "query_events", ["step_name"], schema="tolmach")
    op.create_index("ix_query_events_status", "query_events", ["status"], schema="tolmach")

    op.create_table(
        "sql_guardrail_logs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("query_id", UUID, nullable=False),
        sa.Column("check_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["tolmach.queries.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_sql_guardrail_logs_query_id", "sql_guardrail_logs", ["query_id"], schema="tolmach")
    op.create_index("ix_sql_guardrail_logs_check_name", "sql_guardrail_logs", ["check_name"], schema="tolmach")
    op.create_index("ix_sql_guardrail_logs_status", "sql_guardrail_logs", ["status"], schema="tolmach")

    op.create_table(
        "reports",
        sa.Column("id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("query_id", UUID, nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("natural_text", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("chart_spec", JSONB(), nullable=False),
        sa.Column("result_snapshot", JSONB(), nullable=False),
        sa.Column("config_json", JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["tolmach.queries.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"], schema="tolmach")
    op.create_index("ix_reports_query_id", "reports", ["query_id"], schema="tolmach")
    op.create_index("ix_reports_is_active", "reports", ["is_active"], schema="tolmach")

    op.create_table(
        "report_versions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("report_id", UUID, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("config_json", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["tolmach.users.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["tolmach.reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_report_versions_report_id", "report_versions", ["report_id"], schema="tolmach")

    op.create_table(
        "schedules",
        sa.Column("id", UUID, nullable=False),
        sa.Column("report_id", UUID, nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("run_at_time", sa.Time(), nullable=True),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("day_of_month", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["tolmach.reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_schedules_report_id", "schedules", ["report_id"], schema="tolmach")
    op.create_index("ix_schedules_frequency", "schedules", ["frequency"], schema="tolmach")
    op.create_index("ix_schedules_is_active", "schedules", ["is_active"], schema="tolmach")

    op.create_table(
        "schedule_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("schedule_id", UUID, nullable=False),
        sa.Column("report_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("rows_returned", sa.Integer(), nullable=False),
        sa.Column("execution_ms", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["tolmach.reports.id"]),
        sa.ForeignKeyConstraint(["schedule_id"], ["tolmach.schedules.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_schedule_runs_schedule_id", "schedule_runs", ["schedule_id"], schema="tolmach")
    op.create_index("ix_schedule_runs_report_id", "schedule_runs", ["report_id"], schema="tolmach")
    op.create_index("ix_schedule_runs_status", "schedule_runs", ["status"], schema="tolmach")
    op.create_index("ix_schedule_runs_ran_at", "schedule_runs", ["ran_at"], schema="tolmach")

    op.create_table(
        "report_recipients",
        sa.Column("id", UUID, nullable=False),
        sa.Column("report_id", UUID, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["tolmach.reports.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_report_recipients_report_id", "report_recipients", ["report_id"], schema="tolmach")
    op.create_index("ix_report_recipients_email", "report_recipients", ["email"], schema="tolmach")

    op.create_table(
        "templates",
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("natural_text", sa.Text(), nullable=False),
        sa.Column("canonical_intent_json", JSONB(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_templates_created_by", "templates", ["created_by"], schema="tolmach")
    op.create_index("ix_templates_category", "templates", ["category"], schema="tolmach")
    op.create_index("ix_templates_is_public", "templates", ["is_public"], schema="tolmach")

    op.create_table(
        "semantic_layer",
        sa.Column("id", UUID, nullable=False),
        sa.Column("term", sa.String(length=128), nullable=False),
        sa.Column("aliases", JSONB(), nullable=False),
        sa.Column("sql_expression", sa.Text(), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("dimension_type", sa.String(length=64), nullable=False),
        sa.Column("updated_by", UUID, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["tolmach.users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term"),
        schema="tolmach",
    )
    op.create_index("ix_semantic_layer_term", "semantic_layer", ["term"], schema="tolmach")
    op.create_index("ix_semantic_layer_table_name", "semantic_layer", ["table_name"], schema="tolmach")

    op.create_table(
        "semantic_examples",
        sa.Column("id", UUID, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("natural_text", sa.Text(), nullable=False),
        sa.Column("canonical_intent_json", JSONB(), nullable=False),
        sa.Column("sql_example", sa.Text(), nullable=False),
        sa.Column("domain_tag", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_semantic_examples_domain_tag", "semantic_examples", ["domain_tag"], schema="tolmach")

    op.create_table(
        "access_policies",
        sa.Column("id", UUID, nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("table_name", sa.String(length=128), nullable=False),
        sa.Column("allowed_columns_json", JSONB(), nullable=False),
        sa.Column("row_limit", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_access_policies_role", "access_policies", ["role"], schema="tolmach")
    op.create_index("ix_access_policies_table_name", "access_policies", ["table_name"], schema="tolmach")
    op.create_index("ix_access_policies_is_active", "access_policies", ["is_active"], schema="tolmach")

    op.create_table(
        "chart_preferences",
        sa.Column("id", UUID, nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("dimension_type", sa.String(length=64), nullable=False),
        sa.Column("chart_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="tolmach",
    )
    op.create_index("ix_chart_preferences_metric_type", "chart_preferences", ["metric_type"], schema="tolmach")
    op.create_index("ix_chart_preferences_dimension_type", "chart_preferences", ["dimension_type"], schema="tolmach")

    _create_marts()


def _create_marts() -> None:
    op.execute(
        """
        CREATE VIEW mart_orders AS
        SELECT DISTINCT ON (o.order_id)
          o.order_id,
          o.city_id,
          o.user_id,
          o.driver_id,
          o.status_order,
          o.order_timestamp,
          o.driverdone_timestamp,
          o.clientcancel_timestamp,
          o.drivercancel_timestamp,
          o.distance_in_meters,
          o.duration_in_seconds,
          o.price_order_local
        FROM orders o
        ORDER BY o.order_id, o.tender_timestamp DESC
        """
    )
    op.execute(
        """
        CREATE VIEW mart_tenders AS
        SELECT
          order_id,
          tender_id,
          city_id,
          user_id,
          driver_id,
          status_tender,
          tender_timestamp,
          price_tender_local,
          price_start_local
        FROM orders
        """
    )
    op.execute(
        """
        CREATE VIEW mart_city_daily AS
        SELECT
          DATE(order_timestamp) AS day,
          city_id,
          COUNT(DISTINCT order_id) AS orders_count,
          COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done') AS completed_trips,
          COUNT(DISTINCT order_id) FILTER (WHERE clientcancel_timestamp IS NOT NULL) AS client_cancellations,
          COUNT(DISTINCT order_id) FILTER (WHERE drivercancel_timestamp IS NOT NULL) AS driver_cancellations,
          SUM(price_order_local) FILTER (WHERE status_order = 'done') AS revenue,
          AVG(price_order_local) FILTER (WHERE status_order = 'done') AS avg_check,
          AVG(duration_in_seconds) FILTER (WHERE status_order = 'done') AS avg_duration_seconds,
          AVG(distance_in_meters) FILTER (WHERE status_order = 'done') AS avg_distance_meters
        FROM mart_orders
        GROUP BY DATE(order_timestamp), city_id
        """
    )
    op.execute(
        """
        CREATE VIEW mart_driver_daily AS
        SELECT
          DATE(order_timestamp) AS day,
          driver_id,
          city_id,
          COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done') AS completed_trips,
          SUM(price_order_local) FILTER (WHERE status_order = 'done') AS revenue,
          COUNT(DISTINCT order_id) FILTER (WHERE drivercancel_timestamp IS NOT NULL) AS driver_cancellations
        FROM mart_orders
        GROUP BY DATE(order_timestamp), driver_id, city_id
        """
    )
    op.execute(
        """
        CREATE VIEW mart_client_daily AS
        SELECT
          DATE(order_timestamp) AS day,
          user_id,
          city_id,
          COUNT(DISTINCT order_id) AS orders_count,
          COUNT(DISTINCT order_id) FILTER (WHERE status_order = 'done') AS completed_trips,
          COUNT(DISTINCT order_id) FILTER (WHERE clientcancel_timestamp IS NOT NULL) AS client_cancellations
        FROM mart_orders
        GROUP BY DATE(order_timestamp), user_id, city_id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS mart_client_daily")
    op.execute("DROP VIEW IF EXISTS mart_driver_daily")
    op.execute("DROP VIEW IF EXISTS mart_city_daily")
    op.execute("DROP VIEW IF EXISTS mart_tenders")
    op.execute("DROP VIEW IF EXISTS mart_orders")

    for table_name in [
        "chart_preferences",
        "access_policies",
        "semantic_examples",
        "semantic_layer",
        "templates",
        "report_recipients",
        "schedule_runs",
        "schedules",
        "report_versions",
        "reports",
        "sql_guardrail_logs",
        "query_events",
        "query_clarifications",
        "queries",
        "messages",
        "chats",
        "refresh_tokens",
        "invites",
        "users",
    ]:
        op.drop_table(table_name, schema="tolmach")

    op.drop_table("orders")
    op.drop_table("clients")
    op.drop_table("drivers")
    op.drop_table("cities")
    op.execute("DROP SCHEMA IF EXISTS tolmach")
