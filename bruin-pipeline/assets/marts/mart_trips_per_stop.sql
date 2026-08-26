/* @bruin
name: marts.mart_trips_per_stop
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_stops
  - staging.stg_routes
@bruin */ 

SELECT
    s.stop_name,
    s.latitude,
    s.longitude,
    COUNT(st.trip_id) as total_departures,
    ANY_VALUE(r.route_type) as route_type
FROM `adelaide-metro-505702.staging.stg_stops` s
JOIN `adelaide-metro-505702.staging.stg_stop_times` st ON s.stop_id = st.stop_id
JOIN `adelaide-metro-505702.staging.stg_trips` t ON t.trip_id = st.trip_id
JOIN `adelaide-metro-505702.staging.stg_routes` r ON r.route_id = t.route_id
GROUP BY s.stop_id, s.stop_name, s.latitude, s.longitude
ORDER BY total_departures DESC LIMIT 10