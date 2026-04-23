TRUNCATE TABLE fact.tenders, fact.orders;

WITH valid_rows AS (
    SELECT *
    FROM staging.train_typed
    WHERE is_valid = TRUE
      AND order_id IS NOT NULL
      AND tender_id IS NOT NULL
      AND order_timestamp IS NOT NULL
),
ranked_orders AS (
    SELECT
        vr.*,
        ROW_NUMBER() OVER (
            PARTITION BY vr.order_id
            ORDER BY
                CASE
                    WHEN vr.status_tender = 'done' THEN 0
                    WHEN vr.status_order = 'done' THEN 1
                    ELSE 2
                END,
                COALESCE(vr.tender_timestamp, vr.order_timestamp) DESC NULLS LAST,
                vr.raw_ingest_id DESC
        ) AS row_num
    FROM valid_rows vr
),
orders_rollup AS (
    SELECT
        ro.order_id,
        MAX(ro.city_id) FILTER (WHERE ro.row_num = 1) AS city_id,
        MAX(ro.user_id) FILTER (WHERE ro.row_num = 1) AS user_id,
        MAX(ro.driver_id) FILTER (WHERE ro.row_num = 1) AS driver_id,
        MAX(ro.tender_id) FILTER (WHERE ro.status_tender = 'done') AS accepted_tender_id,
        MIN(ro.order_timestamp) AS order_timestamp,
        MIN((ro.order_timestamp AT TIME ZONE 'UTC')::date) AS order_day,
        COALESCE(MAX(ro.status_order) FILTER (WHERE ro.row_num = 1), 'unknown') AS status_order,
        COUNT(DISTINCT ro.tender_id)::integer AS tender_count,
        COUNT(DISTINCT ro.tender_id) FILTER (WHERE ro.status_tender = 'decline')::integer AS declined_tenders_count,
        COUNT(DISTINCT ro.tender_id) FILTER (WHERE ro.status_tender = 'timeout')::integer AS timeout_tenders_count,
        MAX(ro.driverdone_timestamp) AS driverdone_timestamp,
        MAX(ro.clientcancel_timestamp) AS clientcancel_timestamp,
        MAX(ro.drivercancel_timestamp) AS drivercancel_timestamp,
        MAX(ro.order_modified_local) AS order_modified_local,
        MAX(ro.cancel_before_accept_local) AS cancel_before_accept_local,
        MAX(ro.distance_in_meters) FILTER (WHERE ro.row_num = 1) AS distance_in_meters,
        MAX(ro.duration_in_seconds) FILTER (WHERE ro.row_num = 1) AS duration_in_seconds,
        MAX(ro.price_order_local) FILTER (WHERE ro.row_num = 1) AS price_order_local,
        MIN(ro.raw_ingest_id) AS first_raw_ingest_id,
        MAX(ro.raw_ingest_id) AS last_raw_ingest_id
    FROM ranked_orders ro
    GROUP BY ro.order_id
)
INSERT INTO fact.orders (
    order_id,
    city_id,
    user_id,
    driver_id,
    accepted_tender_id,
    order_timestamp,
    order_day,
    status_order,
    tender_count,
    declined_tenders_count,
    timeout_tenders_count,
    driverdone_timestamp,
    clientcancel_timestamp,
    drivercancel_timestamp,
    order_modified_local,
    cancel_before_accept_local,
    distance_in_meters,
    duration_in_seconds,
    price_order_local,
    first_raw_ingest_id,
    last_raw_ingest_id,
    refreshed_at
)
SELECT
    oru.order_id,
    oru.city_id,
    oru.user_id,
    oru.driver_id,
    oru.accepted_tender_id,
    oru.order_timestamp,
    oru.order_day,
    oru.status_order,
    oru.tender_count,
    oru.declined_tenders_count,
    oru.timeout_tenders_count,
    oru.driverdone_timestamp,
    oru.clientcancel_timestamp,
    oru.drivercancel_timestamp,
    oru.order_modified_local,
    oru.cancel_before_accept_local,
    oru.distance_in_meters,
    oru.duration_in_seconds,
    oru.price_order_local,
    oru.first_raw_ingest_id,
    oru.last_raw_ingest_id,
    CURRENT_TIMESTAMP
FROM orders_rollup oru;

WITH ranked_tenders AS (
    SELECT
        tt.*,
        ROW_NUMBER() OVER (
            PARTITION BY tt.tender_id
            ORDER BY tt.raw_ingest_id DESC
        ) AS row_num
    FROM staging.train_typed tt
    WHERE tt.is_valid = TRUE
      AND tt.order_id IS NOT NULL
      AND tt.tender_id IS NOT NULL
      AND tt.tender_timestamp IS NOT NULL
)
INSERT INTO fact.tenders (
    tender_id,
    order_id,
    city_id,
    user_id,
    driver_id,
    tender_timestamp,
    tender_day,
    status_tender,
    driveraccept_timestamp,
    driverarrived_timestamp,
    driverstartride_timestamp,
    driverdone_timestamp,
    clientcancel_timestamp,
    drivercancel_timestamp,
    order_modified_local,
    cancel_before_accept_local,
    price_tender_local,
    price_start_local,
    source_raw_ingest_id,
    refreshed_at
)
SELECT
    rt.tender_id,
    rt.order_id,
    rt.city_id,
    rt.user_id,
    rt.driver_id,
    rt.tender_timestamp,
    (rt.tender_timestamp AT TIME ZONE 'UTC')::date AS tender_day,
    COALESCE(rt.status_tender, 'unknown') AS status_tender,
    rt.driveraccept_timestamp,
    rt.driverarrived_timestamp,
    rt.driverstartride_timestamp,
    rt.driverdone_timestamp,
    rt.clientcancel_timestamp,
    rt.drivercancel_timestamp,
    rt.order_modified_local,
    rt.cancel_before_accept_local,
    rt.price_tender_local,
    rt.price_start_local,
    rt.raw_ingest_id,
    CURRENT_TIMESTAMP
FROM ranked_tenders rt
WHERE rt.row_num = 1;
