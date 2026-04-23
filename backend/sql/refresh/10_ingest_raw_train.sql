DO $$
BEGIN
    IF to_regclass('public.train') IS NOT NULL THEN
        EXECUTE $sql$
            INSERT INTO raw.train_raw (
                source_name,
                source_row_hash,
                order_id_raw,
                tender_id_raw,
                city_id_raw,
                user_id_raw,
                driver_id_raw,
                offset_hours_raw,
                status_order_raw,
                status_tender_raw,
                order_timestamp_raw,
                tender_timestamp_raw,
                driveraccept_timestamp_raw,
                driverarrived_timestamp_raw,
                driverstartride_timestamp_raw,
                driverdone_timestamp_raw,
                clientcancel_timestamp_raw,
                drivercancel_timestamp_raw,
                order_modified_local_raw,
                cancel_before_accept_local_raw,
                distance_in_meters_raw,
                duration_in_seconds_raw,
                price_order_local_raw,
                price_tender_local_raw,
                price_start_local_raw,
                payload_json
            )
            SELECT
                'public.train',
                md5(
                    concat_ws(
                        '||',
                        coalesce(t.order_id::text, ''),
                        coalesce(t.tender_id::text, ''),
                        coalesce(t.city_id::text, ''),
                        coalesce(t.user_id::text, ''),
                        coalesce(t.driver_id::text, ''),
                        coalesce(t.order_timestamp::text, ''),
                        coalesce(t.tender_timestamp::text, '')
                    )
                ),
                t.order_id::text,
                t.tender_id::text,
                t.city_id::text,
                t.user_id::text,
                t.driver_id::text,
                t.offset_hours::text,
                t.status_order::text,
                t.status_tender::text,
                t.order_timestamp::text,
                t.tender_timestamp::text,
                t.driveraccept_timestamp::text,
                t.driverarrived_timestamp::text,
                t.driverstartride_timestamp::text,
                t.driverdone_timestamp::text,
                t.clientcancel_timestamp::text,
                t.drivercancel_timestamp::text,
                t.order_modified_local::text,
                t.cancel_before_accept_local::text,
                t.distance_in_meters::text,
                t.duration_in_seconds::text,
                t.price_order_local::text,
                t.price_tender_local::text,
                t.price_start_local::text,
                jsonb_build_object(
                    'source', 'public.train',
                    'order_id', t.order_id::text,
                    'tender_id', t.tender_id::text,
                    'city_id', t.city_id::text,
                    'user_id', t.user_id::text,
                    'driver_id', t.driver_id::text
                )
            FROM public.train t
            ON CONFLICT (source_row_hash) DO NOTHING
        $sql$;
    ELSIF to_regclass('public.orders') IS NOT NULL THEN
        EXECUTE $sql$
            INSERT INTO raw.train_raw (
                source_name,
                source_row_hash,
                order_id_raw,
                tender_id_raw,
                city_id_raw,
                user_id_raw,
                driver_id_raw,
                offset_hours_raw,
                status_order_raw,
                status_tender_raw,
                order_timestamp_raw,
                tender_timestamp_raw,
                driverdone_timestamp_raw,
                clientcancel_timestamp_raw,
                drivercancel_timestamp_raw,
                order_modified_local_raw,
                cancel_before_accept_local_raw,
                distance_in_meters_raw,
                duration_in_seconds_raw,
                price_order_local_raw,
                price_tender_local_raw,
                price_start_local_raw,
                payload_json
            )
            SELECT
                'public.orders',
                md5(
                    concat_ws(
                        '||',
                        coalesce(o.order_id::text, ''),
                        coalesce(o.tender_id::text, ''),
                        coalesce(o.city_id::text, ''),
                        coalesce(o.user_id::text, ''),
                        coalesce(o.driver_id::text, ''),
                        coalesce(o.order_timestamp::text, ''),
                        coalesce(o.tender_timestamp::text, '')
                    )
                ),
                o.order_id::text,
                o.tender_id::text,
                o.city_id::text,
                o.user_id::text,
                o.driver_id::text,
                o.offset_hours::text,
                o.status_order::text,
                o.status_tender::text,
                o.order_timestamp::text,
                o.tender_timestamp::text,
                o.driverdone_timestamp::text,
                o.clientcancel_timestamp::text,
                o.drivercancel_timestamp::text,
                o.order_modified_local::text,
                o.cancel_before_accept_local::text,
                o.distance_in_meters::text,
                o.duration_in_seconds::text,
                o.price_order_local::text,
                o.price_tender_local::text,
                o.price_start_local::text,
                jsonb_build_object(
                    'source', 'public.orders',
                    'order_id', o.order_id::text,
                    'tender_id', o.tender_id::text,
                    'city_id', o.city_id::text,
                    'user_id', o.user_id::text,
                    'driver_id', o.driver_id::text
                )
            FROM public.orders o
            ON CONFLICT (source_row_hash) DO NOTHING
        $sql$;
    ELSE
        RAISE NOTICE 'No source table public.train or public.orders found. raw.train_raw ingestion skipped.';
    END IF;
END
$$;
