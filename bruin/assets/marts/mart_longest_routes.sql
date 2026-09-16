/* @bruin
name: marts.mart_longest_routes
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
    COUNT(DISTINCT stop_id) AS unique_stops_count
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
GROUP BY 1,2,3
ORDER BY unique_stops_count DESC LIMIT 20
