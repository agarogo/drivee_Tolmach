EXPLAIN (ANALYZE, BUFFERS)
SELECT
    day,
    orders_count,
    completed_trips,
    active_drivers,
    revenue,
    tender_decline_rate
FROM mart.orders_kpi_daily
WHERE day BETWEEN CURRENT_DATE - INTERVAL '90 days' AND CURRENT_DATE
ORDER BY day DESC;
