/* @bruin
name: marts.mart_trips_per_route
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_routes
  - staging.stg_stop_times
  - staging.stg_trips
@bruin */

SELECT
    r.route_short_name,
    r.route_type,
    COUNT(st.trip_id) as total_departures
FROM `adelaide-metro-505702.staging.stg_stop_times` st
JOIN `adelaide-metro-505702.staging.stg_trips` t ON st.trip_id = t.trip_id
JOIN `adelaide-metro-505702.staging.stg_routes` r ON r.route_id = t.route_id
WHERE r.route_id IS NOT NULL
GROUP by r.route_id,  r.route_short_name, r.route_type
ORDER BY total_departures