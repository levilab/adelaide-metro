/* @bruin
name: marts.mart_ranked_stops
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_stops
  - staging.stg_routes
@bruin */

SELECT
    s.stop_id,
    s.stop_name,
    s.stop_lat,
    s.stop_lon,
    COUNT(st.trip_id) as total_departures,
    ANY_VALUE(r.route_type) as route_type
FROM `adelaide-metro-505702.staging.stg_stop_times` st
JOIN `adelaide-metro-505702.staging.stg_stops` s ON st.stop_id = s.stop_id
JOIN `adelaide-metro-505702.staging.stg_trips` t ON t.trip_id = st.trip_id
JOIN `adelaide-metro-505702.staging.stg_routes` r ON t.route_id = r.route_id
GROUP BY 1,2,3,4
ORDER BY total_departures