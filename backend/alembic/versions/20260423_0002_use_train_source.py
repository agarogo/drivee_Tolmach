"""Use public.train as the Drivee fact source when available.

Revision ID: 20260423_0002
Revises: 20260423_0001
Create Date: 2026-04-23 04:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260423_0002"
down_revision: Union[str, Sequence[str], None] = "20260423_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _train_exists() -> bool:
    return bool(op.get_bind().exec_driver_sql("select to_regclass('public.train') is not null").scalar())


def upgrade() -> None:
    if not _train_exists():
        return

    op.execute("DROP VIEW IF EXISTS mart_client_daily")
    op.execute("DROP VIEW IF EXISTS mart_driver_daily")
    op.execute("DROP VIEW IF EXISTS mart_city_daily")
    op.execute("DROP VIEW IF EXISTS mart_tenders")
    op.execute("DROP VIEW IF EXISTS mart_orders")

    op.execute(
        """
        INSERT INTO cities (city_id, name, country, timezone, is_active)
        VALUES (67, 'Город 67', 'Unknown', 'UTC', true)
        ON CONFLICT (city_id) DO UPDATE
        SET name = EXCLUDED.name,
            is_active = true
        """
    )

    op.execute(
        """
        INSERT INTO drivers (driver_id, city_id, rating, status, registered_at, total_trips)
        SELECT
          driver_id::text,
          67,
          4.80,
          'active',
          MIN(NULLIF(NULLIF(BTRIM(order_timestamp), ''), 'EMPTY')::timestamp),
          COUNT(DISTINCT order_id)
        FROM train
        WHERE NULLIF(NULLIF(BTRIM(driver_id), ''), 'EMPTY') IS NOT NULL
        GROUP BY driver_id
        ON CONFLICT (driver_id) DO UPDATE
        SET city_id = EXCLUDED.city_id,
            total_trips = GREATEST(drivers.total_trips, EXCLUDED.total_trips)
        """
    )

    op.execute(
        """
        INSERT INTO clients (user_id, city_id, registered_at, total_orders, is_active)
        SELECT
          user_id::text,
          67,
          MIN(NULLIF(NULLIF(BTRIM(order_timestamp), ''), 'EMPTY')::timestamp),
          COUNT(DISTINCT order_id),
          true
        FROM train
        WHERE NULLIF(NULLIF(BTRIM(user_id), ''), 'EMPTY') IS NOT NULL
        GROUP BY user_id
        ON CONFLICT (user_id) DO UPDATE
        SET city_id = EXCLUDED.city_id,
            total_orders = GREATEST(clients.total_orders, EXCLUDED.total_orders),
            is_active = true
        """
    )

    op.execute(
        """
        CREATE VIEW mart_orders AS
        WITH normalized_train AS (
          SELECT
            order_id::text AS order_id,
            tender_id::text AS tender_id,
            city_id::integer AS city_id,
            user_id::text AS user_id,
            driver_id::text AS driver_id,
            COALESCE(NULLIF(NULLIF(BTRIM(offset_hours::text), ''), 'EMPTY')::integer, 0) AS offset_hours,
            NULLIF(NULLIF(BTRIM(status_order), ''), 'EMPTY') AS status_order,
            NULLIF(NULLIF(BTRIM(status_tender), ''), 'EMPTY') AS status_tender,
            NULLIF(NULLIF(BTRIM(order_timestamp), ''), 'EMPTY')::timestamp AS order_timestamp,
            NULLIF(NULLIF(BTRIM(tender_timestamp), ''), 'EMPTY')::timestamp AS tender_timestamp,
            NULLIF(NULLIF(BTRIM(driverdone_timestamp), ''), 'EMPTY')::timestamp AS driverdone_timestamp,
            NULLIF(NULLIF(BTRIM(clientcancel_timestamp), ''), 'EMPTY')::timestamp AS clientcancel_timestamp,
            NULLIF(NULLIF(BTRIM(drivercancel_timestamp), ''), 'EMPTY')::timestamp AS drivercancel_timestamp,
            NULLIF(NULLIF(BTRIM(order_modified_local), ''), 'EMPTY')::timestamp AS order_modified_local,
            NULLIF(NULLIF(BTRIM(cancel_before_accept_local), ''), 'EMPTY')::timestamp AS cancel_before_accept_local,
            COALESCE(NULLIF(NULLIF(BTRIM(distance_in_meters::text), ''), 'EMPTY')::integer, 0) AS distance_in_meters,
            COALESCE(NULLIF(NULLIF(BTRIM(duration_in_seconds::text), ''), 'EMPTY')::integer, 0) AS duration_in_seconds,
            COALESCE(NULLIF(NULLIF(BTRIM(price_order_local), ''), 'EMPTY')::numeric, 0)::numeric(10, 2) AS price_order_local,
            COALESCE(NULLIF(NULLIF(BTRIM(price_tender_local), ''), 'EMPTY')::numeric, 0)::numeric(10, 2) AS price_tender_local,
            COALESCE(NULLIF(NULLIF(BTRIM(price_start_local), ''), 'EMPTY')::numeric, 0)::numeric(10, 2) AS price_start_local
          FROM train
        )
        SELECT DISTINCT ON (order_id)
          order_id,
          city_id,
          user_id,
          driver_id,
          status_order,
          order_timestamp,
          driverdone_timestamp,
          clientcancel_timestamp,
          drivercancel_timestamp,
          distance_in_meters,
          duration_in_seconds,
          price_order_local
        FROM normalized_train
        ORDER BY order_id, tender_timestamp DESC NULLS LAST
        """
    )

    op.execute(
        """
        CREATE VIEW mart_tenders AS
        SELECT
          order_id::text AS order_id,
          tender_id::text AS tender_id,
          city_id::integer AS city_id,
          user_id::text AS user_id,
          driver_id::text AS driver_id,
          NULLIF(NULLIF(BTRIM(status_tender), ''), 'EMPTY') AS status_tender,
          NULLIF(NULLIF(BTRIM(tender_timestamp), ''), 'EMPTY')::timestamp AS tender_timestamp,
          COALESCE(NULLIF(NULLIF(BTRIM(price_tender_local), ''), 'EMPTY')::numeric, 0)::numeric(10, 2) AS price_tender_local,
          COALESCE(NULLIF(NULLIF(BTRIM(price_start_local), ''), 'EMPTY')::numeric, 0)::numeric(10, 2) AS price_start_local
        FROM train
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
