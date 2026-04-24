EXPLAIN (ANALYZE, BUFFERS)
SELECT
    ft.city_id,
    DATE(ft.tender_timestamp) AS day,
    ROUND(
        100 * AVG(CASE WHEN ft.status_tender = 'decline' THEN 1 ELSE 0 END),
        2
    ) AS tender_decline_rate
FROM fact.tenders ft
WHERE ft.tender_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ft.city_id, DATE(ft.tender_timestamp)
ORDER BY day DESC, tender_decline_rate DESC
LIMIT 200;
