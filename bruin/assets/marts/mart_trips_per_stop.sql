/* @bruin
name: marts.mart_trips_per_stop
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
@bruin */ 

SELECT
    stop_name,
    stop_lat,
    stop_lon,
    COUNT(*) AS total_departures,
    ANY_VALUE(route_type) AS route_type
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
GROUP BY stop_id, stop_name, stop_lat, stop_lon
ORDER BY total_departures DESC LIMIT 10
