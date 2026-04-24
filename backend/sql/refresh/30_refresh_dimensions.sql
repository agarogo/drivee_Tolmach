TRUNCATE TABLE dim.drivers, dim.clients, dim.cities CASCADE;

WITH city_rollup AS (
    SELECT
        tt.city_id,
        MIN(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS first_seen_at,
        MAX(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS last_seen_at
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.city_id IS NOT NULL
    GROUP BY tt.city_id
)
INSERT INTO dim.cities (
    city_id,
    city_name,
    country,
    timezone,
    is_active,
    first_seen_at,
    last_seen_at,
    refreshed_at
)
SELECT
    cr.city_id,
    COALESCE(pc.name, 'City ' || cr.city_id::text) AS city_name,
    COALESCE(pc.country, 'Unknown') AS country,
    COALESCE(pc.timezone, 'UTC') AS timezone,
    COALESCE(pc.is_active, TRUE) AS is_active,
    cr.first_seen_at,
    cr.last_seen_at,
    CURRENT_TIMESTAMP
FROM city_rollup cr
LEFT JOIN public.cities pc
    ON pc.city_id = cr.city_id;

WITH ranked_drivers AS (
    SELECT
        tt.driver_id,
        tt.city_id,
        COALESCE(tt.order_timestamp, tt.tender_timestamp) AS activity_at,
        ROW_NUMBER() OVER (
            PARTITION BY tt.driver_id
            ORDER BY COALESCE(tt.order_timestamp, tt.tender_timestamp) DESC NULLS LAST, tt.raw_ingest_id DESC
        ) AS row_num
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.driver_id IS NOT NULL
),
driver_rollup AS (
    SELECT
        tt.driver_id,
        MIN(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS first_seen_at,
        MAX(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS last_seen_at,
        COUNT(DISTINCT tt.tender_id)::integer AS tenders_count,
        COUNT(DISTINCT tt.order_id) FILTER (WHERE tt.status_order = 'done')::integer AS completed_orders_count
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.driver_id IS NOT NULL
    GROUP BY tt.driver_id
)
INSERT INTO dim.drivers (
    driver_id,
    city_id,
    first_seen_at,
    last_seen_at,
    tenders_count,
    completed_orders_count,
    refreshed_at
)
SELECT
    dr.driver_id,
    latest.city_id,
    dr.first_seen_at,
    dr.last_seen_at,
    dr.tenders_count,
    dr.completed_orders_count,
    CURRENT_TIMESTAMP
FROM driver_rollup dr
LEFT JOIN ranked_drivers latest
    ON latest.driver_id = dr.driver_id
   AND latest.row_num = 1;

WITH ranked_clients AS (
    SELECT
        tt.user_id,
        tt.city_id,
        COALESCE(tt.order_timestamp, tt.tender_timestamp) AS activity_at,
        ROW_NUMBER() OVER (
            PARTITION BY tt.user_id
            ORDER BY COALESCE(tt.order_timestamp, tt.tender_timestamp) DESC NULLS LAST, tt.raw_ingest_id DESC
        ) AS row_num
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.user_id IS NOT NULL
),
client_rollup AS (
    SELECT
        tt.user_id,
        MIN(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS first_seen_at,
        MAX(COALESCE(tt.order_timestamp, tt.tender_timestamp)) AS last_seen_at,
        COUNT(DISTINCT tt.order_id)::integer AS orders_count,
        COUNT(DISTINCT tt.order_id) FILTER (WHERE tt.status_order = 'done')::integer AS completed_orders_count
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.user_id IS NOT NULL
    GROUP BY tt.user_id
)
INSERT INTO dim.clients (
    user_id,
    city_id,
    first_seen_at,
    last_seen_at,
    orders_count,
    completed_orders_count,
    refreshed_at
)
SELECT
    cr.user_id,
    latest.city_id,
    cr.first_seen_at,
    cr.last_seen_at,
    cr.orders_count,
    cr.completed_orders_count,
    CURRENT_TIMESTAMP
FROM client_rollup cr
LEFT JOIN ranked_clients latest
    ON latest.user_id = cr.user_id
   AND latest.row_num = 1;
