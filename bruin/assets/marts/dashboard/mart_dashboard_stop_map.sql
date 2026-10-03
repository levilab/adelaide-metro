/* @bruin
name: marts.mart_dashboard_stop_map
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
@bruin */

SELECT
    stop_id,
    stop_name,
    stop_lat,
    stop_lon,
    route_type,
    COUNT(*) AS total_departures
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
GROUP BY stop_id, stop_name, stop_lat, stop_lon, route_type
ORDER BY total_departures
