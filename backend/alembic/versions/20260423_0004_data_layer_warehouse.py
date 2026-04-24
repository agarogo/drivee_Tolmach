"""Introduce warehouse schemas and governed data marts.

Revision ID: 20260423_0004
Revises: 20260423_0003
Create Date: 2026-04-23 21:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260423_0004"
down_revision: Union[str, Sequence[str], None] = "20260423_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    _ensure_application_schema()
    for schema_name in ("raw", "staging", "dim", "fact", "mart"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

    op.create_table(
        "train_raw",
        sa.Column("ingest_id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_row_hash", sa.String(length=32), nullable=False),
        sa.Column(
            "source_loaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("order_id_raw", sa.String(length=64), nullable=True),
        sa.Column("tender_id_raw", sa.String(length=64), nullable=True),
        sa.Column("city_id_raw", sa.String(length=64), nullable=True),
        sa.Column("user_id_raw", sa.String(length=64), nullable=True),
        sa.Column("driver_id_raw", sa.String(length=64), nullable=True),
        sa.Column("offset_hours_raw", sa.String(length=32), nullable=True),
        sa.Column("status_order_raw", sa.String(length=64), nullable=True),
        sa.Column("status_tender_raw", sa.String(length=64), nullable=True),
        sa.Column("order_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("tender_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("driveraccept_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("driverarrived_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("driverstartride_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("driverdone_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("clientcancel_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("drivercancel_timestamp_raw", sa.Text(), nullable=True),
        sa.Column("order_modified_local_raw", sa.Text(), nullable=True),
        sa.Column("cancel_before_accept_local_raw", sa.Text(), nullable=True),
        sa.Column("distance_in_meters_raw", sa.String(length=64), nullable=True),
        sa.Column("duration_in_seconds_raw", sa.String(length=64), nullable=True),
        sa.Column("price_order_local_raw", sa.String(length=64), nullable=True),
        sa.Column("price_tender_local_raw", sa.String(length=64), nullable=True),
        sa.Column("price_start_local_raw", sa.String(length=64), nullable=True),
        sa.Column(
            "payload_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("ingest_id"),
        schema="raw",
    )
    op.create_index(
        "uq_train_raw_source_row_hash",
        "train_raw",
        ["source_row_hash"],
        unique=True,
        schema="raw",
    )
    op.create_index(
        "ix_train_raw_source_loaded_at_brin",
        "train_raw",
        ["source_loaded_at"],
        unique=False,
        schema="raw",
        postgresql_using="brin",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION raw.prevent_train_raw_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'raw.train_raw is append-only; % is not allowed', TG_OP;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_train_raw_prevent_mutation
        BEFORE UPDATE OR DELETE ON raw.train_raw
        FOR EACH ROW
        EXECUTE FUNCTION raw.prevent_train_raw_mutation();
        """
    )

    op.create_table(
        "train_typed",
        sa.Column("raw_ingest_id", sa.BigInteger(), nullable=False),
        sa.Column("source_name", sa.String(length=128), nullable=False),
        sa.Column("source_loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=True),
        sa.Column("tender_id", sa.String(length=64), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("driver_id", sa.String(length=64), nullable=True),
        sa.Column("offset_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status_order", sa.String(length=64), nullable=True),
        sa.Column("status_tender", sa.String(length=64), nullable=True),
        sa.Column("order_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tender_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driveraccept_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverarrived_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverstartride_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverdone_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clientcancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drivercancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_modified_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_before_accept_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_in_meters", sa.Integer(), nullable=True),
        sa.Column("duration_in_seconds", sa.Integer(), nullable=True),
        sa.Column("price_order_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_tender_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_start_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "quality_issues_json",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["raw_ingest_id"], ["raw.train_raw.ingest_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("raw_ingest_id"),
        schema="staging",
    )
    op.create_index("ix_train_typed_order_id", "train_typed", ["order_id"], schema="staging")
    op.create_index("ix_train_typed_tender_id", "train_typed", ["tender_id"], schema="staging")
    op.create_index("ix_train_typed_city_id", "train_typed", ["city_id"], schema="staging")
    op.create_index("ix_train_typed_user_id", "train_typed", ["user_id"], schema="staging")
    op.create_index("ix_train_typed_driver_id", "train_typed", ["driver_id"], schema="staging")
    op.create_index(
        "ix_train_typed_order_timestamp_brin",
        "train_typed",
        ["order_timestamp"],
        unique=False,
        schema="staging",
        postgresql_using="brin",
    )
    op.create_index(
        "ix_train_typed_tender_timestamp_brin",
        "train_typed",
        ["tender_timestamp"],
        unique=False,
        schema="staging",
        postgresql_using="brin",
    )

    op.create_table(
        "cities",
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("city_name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False, server_default="Unknown"),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("city_id"),
        schema="dim",
    )
    op.create_index("uq_dim_cities_city_name", "cities", ["city_name"], unique=True, schema="dim")

    op.create_table(
        "drivers",
        sa.Column("driver_id", sa.String(length=64), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["city_id"], ["dim.cities.city_id"]),
        sa.PrimaryKeyConstraint("driver_id"),
        schema="dim",
    )
    op.create_index("ix_dim_drivers_city_id", "drivers", ["city_id"], schema="dim")

    op.create_table(
        "clients",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_orders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["city_id"], ["dim.cities.city_id"]),
        sa.PrimaryKeyConstraint("user_id"),
        schema="dim",
    )
    op.create_index("ix_dim_clients_city_id", "clients", ["city_id"], schema="dim")

    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("driver_id", sa.String(length=64), nullable=True),
        sa.Column("accepted_tender_id", sa.String(length=64), nullable=True),
        sa.Column("order_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_day", sa.Date(), nullable=False),
        sa.Column("status_order", sa.String(length=64), nullable=False),
        sa.Column("tender_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("declined_tenders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_tenders_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("driverdone_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clientcancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drivercancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_modified_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_before_accept_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distance_in_meters", sa.Integer(), nullable=True),
        sa.Column("duration_in_seconds", sa.Integer(), nullable=True),
        sa.Column("price_order_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("first_raw_ingest_id", sa.BigInteger(), nullable=True),
        sa.Column("last_raw_ingest_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("order_day = (order_timestamp AT TIME ZONE 'UTC')::date", name="ck_fact_orders_order_day"),
        sa.ForeignKeyConstraint(["city_id"], ["dim.cities.city_id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["dim.drivers.driver_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["dim.clients.user_id"]),
        sa.PrimaryKeyConstraint("order_id"),
        schema="fact",
    )
    op.create_index("ix_fact_orders_city_day", "orders", ["city_id", "order_day"], schema="fact")
    op.create_index("ix_fact_orders_user_day", "orders", ["user_id", "order_day"], schema="fact")
    op.create_index("ix_fact_orders_driver_day", "orders", ["driver_id", "order_day"], schema="fact")
    op.create_index(
        "ix_fact_orders_done_city_day",
        "orders",
        ["city_id", "order_day"],
        unique=False,
        schema="fact",
        postgresql_where=sa.text("status_order = 'done'"),
    )
    op.create_index(
        "ix_fact_orders_order_timestamp_brin",
        "orders",
        ["order_timestamp"],
        unique=False,
        schema="fact",
        postgresql_using="brin",
    )

    op.create_table(
        "tenders",
        sa.Column("tender_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("driver_id", sa.String(length=64), nullable=True),
        sa.Column("tender_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tender_day", sa.Date(), nullable=False),
        sa.Column("status_tender", sa.String(length=64), nullable=False),
        sa.Column("driveraccept_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverarrived_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverstartride_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driverdone_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clientcancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("drivercancel_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_modified_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_before_accept_local", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_tender_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_start_local", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_raw_ingest_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "tender_day = (tender_timestamp AT TIME ZONE 'UTC')::date",
            name="ck_fact_tenders_tender_day",
        ),
        sa.ForeignKeyConstraint(["city_id"], ["dim.cities.city_id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["dim.drivers.driver_id"]),
        sa.ForeignKeyConstraint(["order_id"], ["fact.orders.order_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_raw_ingest_id"], ["raw.train_raw.ingest_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["dim.clients.user_id"]),
        sa.PrimaryKeyConstraint("tender_id"),
        schema="fact",
    )
    op.create_index("ix_fact_tenders_order_id", "tenders", ["order_id"], schema="fact")
    op.create_index("ix_fact_tenders_city_day", "tenders", ["city_id", "tender_day"], schema="fact")
    op.create_index("ix_fact_tenders_driver_day", "tenders", ["driver_id", "tender_day"], schema="fact")
    op.create_index(
        "ix_fact_tenders_decline_city_day",
        "tenders",
        ["city_id", "tender_day"],
        unique=False,
        schema="fact",
        postgresql_where=sa.text("status_tender = 'decline'"),
    )
    op.create_index(
        "ix_fact_tenders_tender_timestamp_brin",
        "tenders",
        ["tender_timestamp"],
        unique=False,
        schema="fact",
        postgresql_using="brin",
    )

    _create_materialized_views()
    _migrate_existing_app_contracts()


def downgrade() -> None:
    for view_name in (
        "orders_kpi_daily",
        "client_daily",
        "driver_daily",
        "city_daily",
    ):
        op.execute(f"DROP MATERIALIZED VIEW IF EXISTS mart.{view_name}")

    op.drop_table("tenders", schema="fact")
    op.drop_table("orders", schema="fact")
    op.drop_table("clients", schema="dim")
    op.drop_table("drivers", schema="dim")
    op.drop_table("cities", schema="dim")
    op.drop_table("train_typed", schema="staging")
    op.execute("DROP TRIGGER IF EXISTS trg_train_raw_prevent_mutation ON raw.train_raw")
    op.execute("DROP FUNCTION IF EXISTS raw.prevent_train_raw_mutation()")
    op.drop_table("train_raw", schema="raw")

    for schema_name in ("mart", "fact", "dim", "staging", "raw"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema_name}")

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app')
               AND NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'tolmach') THEN
                EXECUTE 'ALTER SCHEMA app RENAME TO tolmach';
            END IF;
        END
        $$;
        """
    )


def _ensure_application_schema() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'tolmach')
               AND NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app') THEN
                EXECUTE 'ALTER SCHEMA tolmach RENAME TO app';
            ELSIF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'app') THEN
                EXECUTE 'CREATE SCHEMA IF NOT EXISTS app';
            END IF;
        END
        $$;
        """
    )


def _create_materialized_views() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW mart.city_daily AS
        SELECT
            fo.order_day AS day,
            fo.city_id,
            COUNT(*)::bigint AS orders_count,
            COUNT(*) FILTER (WHERE fo.status_order = 'done')::bigint AS completed_trips,
            COUNT(*) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL)::bigint AS client_cancellations,
            COUNT(*) FILTER (WHERE fo.drivercancel_timestamp IS NOT NULL)::bigint AS driver_cancellations,
            COUNT(DISTINCT fo.driver_id) FILTER (
                WHERE fo.status_order = 'done' AND fo.driver_id IS NOT NULL
            )::bigint AS active_drivers,
            COALESCE(SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 0)::numeric(14, 2) AS revenue,
            ROUND(AVG(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_check,
            ROUND(AVG(fo.duration_in_seconds) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_duration_seconds,
            ROUND(AVG(fo.distance_in_meters) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_distance_meters,
            COALESCE(SUM(fo.tender_count), 0)::bigint AS tenders_count,
            COALESCE(SUM(fo.declined_tenders_count), 0)::bigint AS declined_tenders_count,
            ROUND(
                100 * COALESCE(SUM(fo.declined_tenders_count), 0)::numeric
                / NULLIF(COALESCE(SUM(fo.tender_count), 0), 0),
                2
            )::numeric(7, 2) AS tender_decline_rate
        FROM fact.orders fo
        GROUP BY fo.order_day, fo.city_id
        WITH NO DATA
        """
    )
    op.create_index("uq_mart_city_daily_day_city", "city_daily", ["day", "city_id"], unique=True, schema="mart")
    op.create_index("ix_mart_city_daily_city_day", "city_daily", ["city_id", "day"], schema="mart")

    op.execute(
        """
        CREATE MATERIALIZED VIEW mart.driver_daily AS
        SELECT
            fo.order_day AS day,
            fo.driver_id,
            fo.city_id,
            COUNT(*)::bigint AS orders_count,
            COUNT(*) FILTER (WHERE fo.status_order = 'done')::bigint AS completed_trips,
            COUNT(*) FILTER (WHERE fo.drivercancel_timestamp IS NOT NULL)::bigint AS driver_cancellations,
            COALESCE(SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 0)::numeric(14, 2) AS revenue
        FROM fact.orders fo
        WHERE fo.driver_id IS NOT NULL
        GROUP BY fo.order_day, fo.driver_id, fo.city_id
        WITH NO DATA
        """
    )
    op.create_index(
        "uq_mart_driver_daily_day_driver",
        "driver_daily",
        ["day", "driver_id"],
        unique=True,
        schema="mart",
    )
    op.create_index("ix_mart_driver_daily_city_day", "driver_daily", ["city_id", "day"], schema="mart")

    op.execute(
        """
        CREATE MATERIALIZED VIEW mart.client_daily AS
        SELECT
            fo.order_day AS day,
            fo.user_id,
            fo.city_id,
            COUNT(*)::bigint AS orders_count,
            COUNT(*) FILTER (WHERE fo.status_order = 'done')::bigint AS completed_trips,
            COUNT(*) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL)::bigint AS client_cancellations,
            COALESCE(SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 0)::numeric(14, 2) AS revenue
        FROM fact.orders fo
        WHERE fo.user_id IS NOT NULL
        GROUP BY fo.order_day, fo.user_id, fo.city_id
        WITH NO DATA
        """
    )
    op.create_index(
        "uq_mart_client_daily_day_user",
        "client_daily",
        ["day", "user_id"],
        unique=True,
        schema="mart",
    )
    op.create_index("ix_mart_client_daily_city_day", "client_daily", ["city_id", "day"], schema="mart")

    op.execute(
        """
        CREATE MATERIALIZED VIEW mart.orders_kpi_daily AS
        SELECT
            fo.order_day AS day,
            COUNT(*)::bigint AS orders_count,
            COUNT(*) FILTER (WHERE fo.status_order = 'done')::bigint AS completed_trips,
            COUNT(*) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL)::bigint AS client_cancellations,
            COUNT(*) FILTER (WHERE fo.drivercancel_timestamp IS NOT NULL)::bigint AS driver_cancellations,
            COUNT(DISTINCT fo.driver_id) FILTER (
                WHERE fo.status_order = 'done' AND fo.driver_id IS NOT NULL
            )::bigint AS active_drivers,
            COUNT(DISTINCT fo.city_id) FILTER (WHERE fo.city_id IS NOT NULL)::bigint AS active_cities,
            COALESCE(SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 0)::numeric(14, 2) AS revenue,
            ROUND(AVG(fo.price_order_local) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_check,
            ROUND(AVG(fo.duration_in_seconds) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_duration_seconds,
            ROUND(AVG(fo.distance_in_meters) FILTER (WHERE fo.status_order = 'done'), 2)::numeric(14, 2) AS avg_distance_meters,
            COALESCE(SUM(fo.tender_count), 0)::bigint AS tenders_count,
            COALESCE(SUM(fo.declined_tenders_count), 0)::bigint AS declined_tenders_count,
            ROUND(
                100 * COALESCE(SUM(fo.declined_tenders_count), 0)::numeric
                / NULLIF(COALESCE(SUM(fo.tender_count), 0), 0),
                2
            )::numeric(7, 2) AS tender_decline_rate
        FROM fact.orders fo
        GROUP BY fo.order_day
        WITH NO DATA
        """
    )
    op.create_index("uq_mart_orders_kpi_daily_day", "orders_kpi_daily", ["day"], unique=True, schema="mart")


def _migrate_existing_app_contracts() -> None:
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'SUM(fact.orders.price_order_local) FILTER (WHERE fact.orders.status_order = ''done'')',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'SUM(fo.price_order_local) FILTER (WHERE fo.status_order = ''done'')'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'money'
            )
        WHERE semantic_key = 'revenue'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'COUNT(DISTINCT fact.orders.order_id)',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object('fact.orders fo', 'COUNT(DISTINCT fo.order_id)'),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'count'
            )
        WHERE semantic_key = 'orders_count'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.status_order = ''done'')',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.status_order = ''done'')'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'count'
            )
        WHERE semantic_key = 'completed_trips'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.clientcancel_timestamp IS NOT NULL)',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL)'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'count'
            )
        WHERE semantic_key = 'client_cancellations'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'COUNT(DISTINCT fact.orders.order_id) FILTER (WHERE fact.orders.drivercancel_timestamp IS NOT NULL)',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.drivercancel_timestamp IS NOT NULL)'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'count'
            )
        WHERE semantic_key = 'driver_cancellations'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'AVG(fact.orders.price_order_local) FILTER (WHERE fact.orders.status_order = ''done'')',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'ROUND(AVG(fo.price_order_local) FILTER (WHERE fo.status_order = ''done''), 2)'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'money'
            )
        WHERE semantic_key = 'avg_check'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'COUNT(DISTINCT fact.orders.driver_id) FILTER (WHERE fact.orders.status_order = ''done'')',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.orders fo',
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'COUNT(DISTINCT fo.driver_id) FILTER (WHERE fo.status_order = ''done'')'
                ),
                'time_field_by_base', jsonb_build_object('fact.orders fo', 'fo.order_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'count'
            )
        WHERE semantic_key = 'active_drivers'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.tenders',
            sql_expression = 'AVG(CASE WHEN fact.tenders.status_tender = ''decline'' THEN 1 ELSE 0 END)',
            semantic_config_json = jsonb_build_object(
                'base_table', 'fact.tenders ft',
                'expression_by_base', jsonb_build_object(
                    'fact.tenders ft', 'ROUND(100 * AVG(CASE WHEN ft.status_tender = ''decline'' THEN 1 ELSE 0 END), 2)'
                ),
                'time_field_by_base', jsonb_build_object('fact.tenders ft', 'ft.tender_timestamp'),
                'supported_dimensions', to_jsonb(ARRAY['city', 'day']),
                'default_chart_type', 'bar',
                'default_order_direction', 'desc',
                'value_type', 'ratio'
            )
        WHERE semantic_key = 'tender_decline_rate'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'dim.cities',
            sql_expression = 'dim.cities.city_name',
            semantic_config_json = jsonb_build_object(
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'c.city_name',
                    'fact.tenders ft', 'c.city_name'
                ),
                'group_expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'c.city_name',
                    'fact.tenders ft', 'c.city_name'
                ),
                'joins_by_base', jsonb_build_object(
                    'fact.orders fo', 'JOIN dim.cities c ON c.city_id = fo.city_id',
                    'fact.tenders ft', 'JOIN dim.cities c ON c.city_id = ft.city_id'
                ),
                'select_alias', 'city',
                'value_type', 'string',
                'allowed_operators', to_jsonb(ARRAY['eq', 'in'])
            )
        WHERE semantic_key = 'city'
        """
    )
    op.execute(
        """
        UPDATE app.semantic_layer
        SET table_name = 'fact.orders',
            sql_expression = 'DATE(fact.orders.order_timestamp)',
            semantic_config_json = jsonb_build_object(
                'expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'DATE(fo.order_timestamp)',
                    'fact.tenders ft', 'DATE(ft.tender_timestamp)'
                ),
                'group_expression_by_base', jsonb_build_object(
                    'fact.orders fo', 'DATE(fo.order_timestamp)',
                    'fact.tenders ft', 'DATE(ft.tender_timestamp)'
                ),
                'select_alias', 'day',
                'value_type', 'date',
                'allowed_operators', to_jsonb(ARRAY['eq', 'between'])
            )
        WHERE semantic_key = 'day'
        """
    )

    op.execute(
        """
        UPDATE app.access_policies
        SET is_active = FALSE
        WHERE table_name IN (
            'orders',
            'train',
            'cities',
            'drivers',
            'clients',
            'mart_orders',
            'mart_tenders',
            'mart_city_daily',
            'mart_driver_daily',
            'mart_client_daily'
        )
        """
    )
    op.execute(
        """
        INSERT INTO app.access_policies (id, role, table_name, allowed_columns_json, row_limit, is_active, created_at)
        SELECT
            (
                substr(md5(role_name || ':' || table_name), 1, 8)
                || '-'
                || substr(md5(role_name || ':' || table_name), 9, 4)
                || '-'
                || substr(md5(role_name || ':' || table_name), 13, 4)
                || '-'
                || substr(md5(role_name || ':' || table_name), 17, 4)
                || '-'
                || substr(md5(role_name || ':' || table_name), 21, 12)
            )::uuid,
            role_name,
            table_name,
            columns_json,
            1000,
            TRUE,
            CURRENT_TIMESTAMP
        FROM (
            VALUES
                ('user', 'dim.cities', '["city_id","city_name","country","timezone","is_active","first_seen_at","last_seen_at"]'::jsonb),
                ('user', 'dim.drivers', '["driver_id","city_id","first_seen_at","last_seen_at","tenders_count","completed_orders_count"]'::jsonb),
                ('user', 'dim.clients', '["user_id","city_id","first_seen_at","last_seen_at","orders_count","completed_orders_count"]'::jsonb),
                ('user', 'fact.orders', '["order_id","city_id","user_id","driver_id","accepted_tender_id","status_order","order_timestamp","order_day","tender_count","declined_tenders_count","timeout_tenders_count","driverdone_timestamp","clientcancel_timestamp","drivercancel_timestamp","order_modified_local","cancel_before_accept_local","distance_in_meters","duration_in_seconds","price_order_local"]'::jsonb),
                ('user', 'fact.tenders', '["order_id","tender_id","city_id","user_id","driver_id","status_tender","tender_timestamp","tender_day","driveraccept_timestamp","driverarrived_timestamp","driverstartride_timestamp","driverdone_timestamp","clientcancel_timestamp","drivercancel_timestamp","order_modified_local","cancel_before_accept_local","price_tender_local","price_start_local"]'::jsonb),
                ('user', 'mart.city_daily', '["day","city_id","orders_count","completed_trips","client_cancellations","driver_cancellations","active_drivers","revenue","avg_check","avg_duration_seconds","avg_distance_meters","tenders_count","declined_tenders_count","tender_decline_rate"]'::jsonb),
                ('user', 'mart.driver_daily', '["day","driver_id","city_id","orders_count","completed_trips","driver_cancellations","revenue"]'::jsonb),
                ('user', 'mart.client_daily', '["day","user_id","city_id","orders_count","completed_trips","client_cancellations","revenue"]'::jsonb),
                ('user', 'mart.orders_kpi_daily', '["day","orders_count","completed_trips","client_cancellations","driver_cancellations","active_drivers","active_cities","revenue","avg_check","avg_duration_seconds","avg_distance_meters","tenders_count","declined_tenders_count","tender_decline_rate"]'::jsonb),
                ('admin', 'dim.cities', '["city_id","city_name","country","timezone","is_active","first_seen_at","last_seen_at"]'::jsonb),
                ('admin', 'dim.drivers', '["driver_id","city_id","first_seen_at","last_seen_at","tenders_count","completed_orders_count"]'::jsonb),
                ('admin', 'dim.clients', '["user_id","city_id","first_seen_at","last_seen_at","orders_count","completed_orders_count"]'::jsonb),
                ('admin', 'fact.orders', '["order_id","city_id","user_id","driver_id","accepted_tender_id","status_order","order_timestamp","order_day","tender_count","declined_tenders_count","timeout_tenders_count","driverdone_timestamp","clientcancel_timestamp","drivercancel_timestamp","order_modified_local","cancel_before_accept_local","distance_in_meters","duration_in_seconds","price_order_local"]'::jsonb),
                ('admin', 'fact.tenders', '["order_id","tender_id","city_id","user_id","driver_id","status_tender","tender_timestamp","tender_day","driveraccept_timestamp","driverarrived_timestamp","driverstartride_timestamp","driverdone_timestamp","clientcancel_timestamp","drivercancel_timestamp","order_modified_local","cancel_before_accept_local","price_tender_local","price_start_local"]'::jsonb),
                ('admin', 'mart.city_daily', '["day","city_id","orders_count","completed_trips","client_cancellations","driver_cancellations","active_drivers","revenue","avg_check","avg_duration_seconds","avg_distance_meters","tenders_count","declined_tenders_count","tender_decline_rate"]'::jsonb),
                ('admin', 'mart.driver_daily', '["day","driver_id","city_id","orders_count","completed_trips","driver_cancellations","revenue"]'::jsonb),
                ('admin', 'mart.client_daily', '["day","user_id","city_id","orders_count","completed_trips","client_cancellations","revenue"]'::jsonb),
                ('admin', 'mart.orders_kpi_daily', '["day","orders_count","completed_trips","client_cancellations","driver_cancellations","active_drivers","active_cities","revenue","avg_check","avg_duration_seconds","avg_distance_meters","tenders_count","declined_tenders_count","tender_decline_rate"]'::jsonb)
        ) AS policies(role_name, table_name, columns_json)
        WHERE NOT EXISTS (
            SELECT 1
            FROM app.access_policies existing
            WHERE existing.role = role_name
              AND existing.table_name = table_name
              AND existing.is_active = TRUE
        )
        """
    )

    op.execute(
        """
        UPDATE app.semantic_examples
        SET sql_example = replace(
            replace(
                replace(
                    replace(
                        replace(sql_example, 'mart_orders mo', 'fact.orders fo'),
                        'mart_tenders mt', 'fact.tenders ft'
                    ),
                    'JOIN cities c', 'JOIN dim.cities c'
                ),
                'c.name', 'c.city_name'
            ),
            'mo.', 'fo.'
        )
        WHERE position('mart_orders' in sql_example) > 0 OR position('mart_tenders' in sql_example) > 0
        """
    )
    op.execute(
        """
        UPDATE app.semantic_examples
        SET sql_example = replace(sql_example, 'mt.', 'ft.')
        WHERE position('fact.tenders ft' in sql_example) > 0
        """
    )
    op.execute(
        """
        UPDATE app.reports
        SET generated_sql = replace(
            replace(
                replace(
                    replace(
                        replace(generated_sql, 'mart_orders mo', 'fact.orders fo'),
                        'JOIN cities c', 'JOIN dim.cities c'
                    ),
                    'c.name', 'c.city_name'
                ),
                'mo.', 'fo.'
            ),
            'GROUP BY c.name', 'GROUP BY c.city_name'
        )
        WHERE position('mart_orders' in generated_sql) > 0
        """
    )
    op.execute(
        """
        UPDATE app.report_versions
        SET generated_sql = replace(
            replace(
                replace(
                    replace(
                        replace(generated_sql, 'mart_orders mo', 'fact.orders fo'),
                        'JOIN cities c', 'JOIN dim.cities c'
                    ),
                    'c.name', 'c.city_name'
                ),
                'mo.', 'fo.'
            ),
            'GROUP BY c.name', 'GROUP BY c.city_name'
        )
        WHERE position('mart_orders' in generated_sql) > 0
        """
    )
