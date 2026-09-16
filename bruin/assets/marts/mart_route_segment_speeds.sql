/* @bruin
name: marts.mart_route_segment_speeds
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_route_segments
@bruin */

SELECT 
    route_id,
    from_stop_id,
    from_stop_name,
    to_stop_id,
    to_stop_name,
    COUNT(*) AS total_trips_analyzed,
    ROUND(AVG(segment_distance_km), 2) AS avg_segment_km,
    ROUND(AVG(scheduled_travel_time_seconds), 2) AS avg_time_sec,
    ROUND(
        SAFE_DIVIDE(AVG(segment_distance_km), AVG(scheduled_travel_time_seconds)) * 3600,
        2
    ) AS avg_scheduled_speed_kmh
FROM `adelaide-metro-505702.core.fact_scheduled_route_segments`
WHERE scheduled_travel_time_seconds > 0
    AND scheduled_speed_kmh <= 90.0
GROUP BY route_id, from_stop_id, from_stop_name, to_stop_id, to_stop_name
HAVING COUNT(*) > 5
ORDER BY avg_scheduled_speed_kmh ASC;
