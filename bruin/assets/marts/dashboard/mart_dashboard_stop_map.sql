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
    COUNT(*) AS total_departures,
    ANY_VALUE(route_type) AS route_type
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
GROUP BY 1,2,3,4
ORDER BY total_departures
