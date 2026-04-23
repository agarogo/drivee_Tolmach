EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.city_name,
    cd.day,
    cd.orders_count,
    cd.completed_trips,
    cd.revenue
FROM mart.city_daily cd
JOIN dim.cities c
    ON c.city_id = cd.city_id
WHERE cd.day >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY cd.day DESC, cd.revenue DESC
LIMIT 100;
