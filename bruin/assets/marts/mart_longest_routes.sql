/* @bruin
name: marts.mart_longest_route
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_trips
  - staging.stg_routes
@bruin */

SELECT
    r.route_short_name,
    r.route_long_name,
    r.route_type,
    COUNT(DISTINCT st.stop_id) as unique_stops_count,

FROM `adelaide-metro-505702.staging.stg_routes` r
JOIN `adelaide-metro-505702.staging.stg_trips` t
    ON r.route_id = t.route_id
JOIN `adelaide-metro-505702.staging.stg_stop_times` st
    ON st.trip_id = t.trip_id
GROUP BY 1,2,3
ORDER BY unique_stops_count DESC LIMIT 20