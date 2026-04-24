EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE)
SELECT
  dim_city.city_name AS city,
  SUM(fo.price_order_local) FILTER (WHERE fo.status_order = 'done') AS revenue
FROM fact.orders AS fo
JOIN dim.cities AS dim_city ON dim_city.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dim_city.city_name
ORDER BY revenue DESC
LIMIT 10;

EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE)
SELECT
  fo.order_day AS day,
  COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.status_order = 'done') AS completed_trips
FROM fact.orders AS fo
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY fo.order_day
ORDER BY day ASC
LIMIT 20;

EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE)
SELECT
  dim_city.city_name AS city,
  COUNT(DISTINCT fo.order_id) FILTER (WHERE fo.clientcancel_timestamp IS NOT NULL) AS client_cancellations
FROM fact.orders AS fo
JOIN dim.cities AS dim_city ON dim_city.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dim_city.city_name
ORDER BY client_cancellations DESC
LIMIT 20;

EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE)
SELECT
  dim_city.city_name AS city,
  COUNT(DISTINCT fo.driver_id) FILTER (WHERE fo.status_order = 'done' AND fo.driver_id IS NOT NULL) AS active_drivers
FROM fact.orders AS fo
JOIN dim.cities AS dim_city ON dim_city.city_id = fo.city_id
WHERE fo.order_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY dim_city.city_name
ORDER BY active_drivers DESC
LIMIT 20;

EXPLAIN (FORMAT JSON, COSTS TRUE, VERBOSE FALSE)
SELECT
  dim_city.city_name AS city,
  ROUND(100 * AVG(CASE WHEN ft.status_tender = 'decline' THEN 1 ELSE 0 END), 2) AS tender_decline_rate
FROM fact.tenders AS ft
JOIN dim.cities AS dim_city ON dim_city.city_id = ft.city_id
WHERE ft.tender_timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY dim_city.city_name
ORDER BY tender_decline_rate DESC
LIMIT 20;
