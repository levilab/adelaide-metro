/* @bruin
name: marts.mart_dashboard_route_trip_counts
type: bq.sql
materialization:
  type: table
depends:
  - core.dim_trips
@bruin */

SELECT
    route_short_name,
    route_long_name,
    route_type,
    COUNT(DISTINCT trip_id) AS total_trips
FROM `adelaide-metro-505702.core.dim_trips`
WHERE route_short_name IS NOT NULL
GROUP BY route_short_name, route_long_name, route_type
ORDER BY total_trips DESC;
