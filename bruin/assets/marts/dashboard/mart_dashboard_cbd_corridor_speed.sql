/* @bruin
name: marts.mart_dashboard_cbd_corridor_speed
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_route_segments
@bruin */

WITH cleaned_segments AS (
    SELECT 
        trip_id,
        departure_time_bucket AS time_bucket,
        CASE 
            WHEN from_stop_name LIKE '%King William%' OR to_stop_name LIKE '%King William%' THEN 'King William St'
            WHEN from_stop_name LIKE '%Grenfell%' OR to_stop_name LIKE '%Grenfell%' THEN 'Grenfell St'
            WHEN from_stop_name LIKE '%North Tce%' OR to_stop_name LIKE '%North Tce%' THEN 'North Tce'
            WHEN from_stop_name LIKE '%Currie%' OR to_stop_name LIKE '%Currie%' THEN 'Currie St'
            WHEN from_stop_name LIKE '%Victoria Sq%' OR to_stop_name LIKE '%Victoria Sq%' THEN 'Victoria Sq'
            ELSE 'Other CBD / Non-CBD'
        END AS corridor_name,
        segment_distance_km AS dist_km,
        scheduled_travel_time_seconds AS travel_time_sec,
        scheduled_speed_kmh
    FROM `adelaide-metro-505702.core.fact_scheduled_route_segments`
)

SELECT 
    corridor_name,
    time_bucket,
    COUNT(DISTINCT trip_id) AS unique_trips,
    COUNT(*) AS analyzed_segments,
    ROUND(SUM(dist_km), 2) AS total_km,
    ROUND(SUM(travel_time_sec) / 60.0, 2) AS total_minutes,
    ROUND(
        SAFE_DIVIDE(SUM(dist_km), SUM(travel_time_sec)) * 3600,
        2
    ) AS corridor_avg_speed_kmh
FROM cleaned_segments
WHERE travel_time_sec > 0
  AND scheduled_speed_kmh <= 80.0
  AND corridor_name != 'Other CBD / Non-CBD'
  AND time_bucket IS NOT NULL
GROUP BY corridor_name, time_bucket
ORDER BY corridor_name, time_bucket;
