WITH source_rows AS (
    SELECT
        r.ingest_id AS raw_ingest_id,
        r.source_name,
        r.source_loaded_at,
        NULLIF(NULLIF(BTRIM(r.order_id_raw), ''), 'EMPTY') AS order_id_txt,
        NULLIF(NULLIF(BTRIM(r.tender_id_raw), ''), 'EMPTY') AS tender_id_txt,
        NULLIF(NULLIF(BTRIM(r.city_id_raw), ''), 'EMPTY') AS city_id_txt,
        NULLIF(NULLIF(BTRIM(r.user_id_raw), ''), 'EMPTY') AS user_id_txt,
        NULLIF(NULLIF(BTRIM(r.driver_id_raw), ''), 'EMPTY') AS driver_id_txt,
        COALESCE(NULLIF(NULLIF(BTRIM(r.offset_hours_raw), ''), 'EMPTY')::integer, 0) AS offset_hours,
        LOWER(NULLIF(NULLIF(BTRIM(r.status_order_raw), ''), 'EMPTY')) AS status_order_txt,
        LOWER(NULLIF(NULLIF(BTRIM(r.status_tender_raw), ''), 'EMPTY')) AS status_tender_txt,
        NULLIF(NULLIF(BTRIM(r.order_timestamp_raw), ''), 'EMPTY') AS order_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.tender_timestamp_raw), ''), 'EMPTY') AS tender_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.driveraccept_timestamp_raw), ''), 'EMPTY') AS driveraccept_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.driverarrived_timestamp_raw), ''), 'EMPTY') AS driverarrived_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.driverstartride_timestamp_raw), ''), 'EMPTY') AS driverstartride_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.driverdone_timestamp_raw), ''), 'EMPTY') AS driverdone_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.clientcancel_timestamp_raw), ''), 'EMPTY') AS clientcancel_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.drivercancel_timestamp_raw), ''), 'EMPTY') AS drivercancel_timestamp_txt,
        NULLIF(NULLIF(BTRIM(r.order_modified_local_raw), ''), 'EMPTY') AS order_modified_local_txt,
        NULLIF(NULLIF(BTRIM(r.cancel_before_accept_local_raw), ''), 'EMPTY') AS cancel_before_accept_local_txt,
        NULLIF(NULLIF(BTRIM(r.distance_in_meters_raw), ''), 'EMPTY') AS distance_in_meters_txt,
        NULLIF(NULLIF(BTRIM(r.duration_in_seconds_raw), ''), 'EMPTY') AS duration_in_seconds_txt,
        NULLIF(NULLIF(BTRIM(r.price_order_local_raw), ''), 'EMPTY') AS price_order_local_txt,
        NULLIF(NULLIF(BTRIM(r.price_tender_local_raw), ''), 'EMPTY') AS price_tender_local_txt,
        NULLIF(NULLIF(BTRIM(r.price_start_local_raw), ''), 'EMPTY') AS price_start_local_txt
    FROM raw.train_raw r
    LEFT JOIN staging.train_typed st
        ON st.raw_ingest_id = r.ingest_id
    WHERE st.raw_ingest_id IS NULL
),
typed_rows AS (
    SELECT
        raw_ingest_id,
        source_name,
        source_loaded_at,
        order_id_txt AS order_id,
        tender_id_txt AS tender_id,
        CASE WHEN city_id_txt ~ '^-?[0-9]+$' THEN city_id_txt::integer ELSE NULL END AS city_id,
        user_id_txt AS user_id,
        driver_id_txt AS driver_id,
        offset_hours,
        status_order_txt AS status_order,
        status_tender_txt AS status_tender,
        CASE
            WHEN order_timestamp_txt IS NULL OR order_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((order_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS order_timestamp,
        CASE
            WHEN tender_timestamp_txt IS NULL OR tender_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((tender_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS tender_timestamp,
        CASE
            WHEN driveraccept_timestamp_txt IS NULL OR driveraccept_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((driveraccept_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS driveraccept_timestamp,
        CASE
            WHEN driverarrived_timestamp_txt IS NULL OR driverarrived_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((driverarrived_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS driverarrived_timestamp,
        CASE
            WHEN driverstartride_timestamp_txt IS NULL OR driverstartride_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((driverstartride_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS driverstartride_timestamp,
        CASE
            WHEN driverdone_timestamp_txt IS NULL OR driverdone_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((driverdone_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS driverdone_timestamp,
        CASE
            WHEN clientcancel_timestamp_txt IS NULL OR clientcancel_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((clientcancel_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS clientcancel_timestamp,
        CASE
            WHEN drivercancel_timestamp_txt IS NULL OR drivercancel_timestamp_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((drivercancel_timestamp_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS drivercancel_timestamp,
        CASE
            WHEN order_modified_local_txt IS NULL OR order_modified_local_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((order_modified_local_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS order_modified_local,
        CASE
            WHEN cancel_before_accept_local_txt IS NULL OR cancel_before_accept_local_txt !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                THEN NULL
            ELSE ((cancel_before_accept_local_txt::timestamp - make_interval(hours => offset_hours)) AT TIME ZONE 'UTC')
        END AS cancel_before_accept_local,
        CASE WHEN distance_in_meters_txt ~ '^-?[0-9]+$' THEN distance_in_meters_txt::integer ELSE NULL END AS distance_in_meters,
        CASE WHEN duration_in_seconds_txt ~ '^-?[0-9]+$' THEN duration_in_seconds_txt::integer ELSE NULL END AS duration_in_seconds,
        CASE WHEN price_order_local_txt ~ '^-?[0-9]+([.][0-9]+)?$' THEN price_order_local_txt::numeric(14, 2) ELSE NULL END AS price_order_local,
        CASE WHEN price_tender_local_txt ~ '^-?[0-9]+([.][0-9]+)?$' THEN price_tender_local_txt::numeric(14, 2) ELSE NULL END AS price_tender_local,
        CASE WHEN price_start_local_txt ~ '^-?[0-9]+([.][0-9]+)?$' THEN price_start_local_txt::numeric(14, 2) ELSE NULL END AS price_start_local,
        ARRAY_REMOVE(
            ARRAY[
                CASE WHEN order_id_txt IS NULL THEN 'missing_order_id' END,
                CASE WHEN tender_id_txt IS NULL THEN 'missing_tender_id' END,
                CASE WHEN order_timestamp_txt IS NULL THEN 'missing_order_timestamp' END,
                CASE WHEN tender_timestamp_txt IS NULL THEN 'missing_tender_timestamp' END
            ],
            NULL
        ) AS quality_issues
    FROM source_rows
)
INSERT INTO staging.train_typed (
    raw_ingest_id,
    source_name,
    source_loaded_at,
    order_id,
    tender_id,
    city_id,
    user_id,
    driver_id,
    offset_hours,
    status_order,
    status_tender,
    order_timestamp,
    tender_timestamp,
    driveraccept_timestamp,
    driverarrived_timestamp,
    driverstartride_timestamp,
    driverdone_timestamp,
    clientcancel_timestamp,
    drivercancel_timestamp,
    order_modified_local,
    cancel_before_accept_local,
    distance_in_meters,
    duration_in_seconds,
    price_order_local,
    price_tender_local,
    price_start_local,
    is_valid,
    quality_issues_json,
    normalized_at
)
SELECT
    raw_ingest_id,
    source_name,
    source_loaded_at,
    order_id,
    tender_id,
    city_id,
    user_id,
    driver_id,
    offset_hours,
    status_order,
    status_tender,
    order_timestamp,
    tender_timestamp,
    driveraccept_timestamp,
    driverarrived_timestamp,
    driverstartride_timestamp,
    driverdone_timestamp,
    clientcancel_timestamp,
    drivercancel_timestamp,
    order_modified_local,
    cancel_before_accept_local,
    distance_in_meters,
    duration_in_seconds,
    price_order_local,
    price_tender_local,
    price_start_local,
    cardinality(quality_issues) = 0,
    to_jsonb(quality_issues),
    CURRENT_TIMESTAMP
FROM typed_rows;
