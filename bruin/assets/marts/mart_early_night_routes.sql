/* @bruin
name: marts.mart_early_night_routes
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
@bruin */

SELECT
    route_short_name,
    route_long_name,
    route_type,
    COUNTIF(departure_hour BETWEEN 0 AND 5) AS early_morning_departures,
    COUNTIF(departure_hour BETWEEN 22 AND 23) AS night_departures,
    COUNTIF(departure_hour BETWEEN 0 AND 5 OR departure_hour BETWEEN 22 AND 23) AS total_early_night_departures,
    MIN(departure_hour) AS first_departure_hour,
    MAX(departure_hour) AS last_departure_hour
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
WHERE is_first_stop
  AND departure_hour IS NOT NULL
GROUP BY route_short_name, route_long_name, route_type
HAVING total_early_night_departures > 0
ORDER BY total_early_night_departures DESC;
