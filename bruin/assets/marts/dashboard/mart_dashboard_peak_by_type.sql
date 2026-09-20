/* @bruin
name: marts.mart_dashboard_peak_by_type
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
@bruin */

-- One row per clock hour and transport type. A trip can be active in several hours.

WITH stop_events AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY trip_id
      ORDER BY stop_sequence
    ) = 1 AS is_first_stop
  FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
)

SELECT
    departure_hour AS hour_of_day,
    route_type,
    route_type_name,
    COUNT(DISTINCT trip_id) AS total_trips,
    COUNTIF(is_first_stop) AS total_departures
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
WHERE departure_hour BETWEEN 0 AND 23
GROUP BY hour_of_day, route_type, route_type_name;
