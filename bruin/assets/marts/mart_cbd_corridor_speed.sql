/* @bruin
name: marts.mart_cbd_corridor_speed
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_trips
  - staging.stg_stops
@bruin */

WITH ordered_stops AS (
    SELECT 
        st.trip_id,
        st.departure_time AS dept_str,
        LEAD(st.arrival_time) OVER (PARTITION BY st.trip_id ORDER BY st.stop_sequence) AS arr_str,

        s.stop_name AS from_stop_name,
        LEAD(s.stop_name) OVER (PARTITION BY st.trip_id ORDER BY st.stop_sequence) AS to_stop_name,
        
        st.shape_dist_traveled AS dist_from,
        LEAD(st.shape_dist_traveled) OVER (PARTITION BY st.trip_id ORDER BY st.stop_sequence) AS dist_to
    FROM staging.stg_stop_times st
    LEFT JOIN staging.stg_stops s ON st.stop_id = s.stop_id
),

raw_segments AS (
    -- calculate distance between two stops
    SELECT 
        trip_id,
        dept_str,
        arr_str,
        CAST(SPLIT(dept_str, ':')[OFFSET(0)] AS INT64) AS dept_hour,
        (dist_to - dist_from) AS dist_km,
        from_stop_name,
        to_stop_name
    FROM ordered_stops
    WHERE to_stop_name IS NOT NULL 
      AND dist_to > dist_from
),

cleaned_segments AS (
    SELECT 
        trip_id,
        
        -- Categorize time windows
        CASE 
            WHEN dept_hour BETWEEN 7 AND 9 THEN '1. AM Peak (7-9h)'
            WHEN dept_hour BETWEEN 10 AND 15 THEN '2. Mid Day (10-15h)'
            WHEN dept_hour BETWEEN 16 AND 18 THEN '3. PM Peak (16-18h)'
            ELSE '4. Off Peak'
        END AS time_bucket,

        -- Category traffic corridors, focus on CBD corridors
        CASE 
            WHEN from_stop_name LIKE '%King William%' OR to_stop_name LIKE '%King William%' THEN 'King William St'
            WHEN from_stop_name LIKE '%Grenfell%' OR to_stop_name LIKE '%Grenfell%' THEN 'Grenfell St'
            WHEN from_stop_name LIKE '%North Tce%' OR to_stop_name LIKE '%North Tce%' THEN 'North Tce'
            WHEN from_stop_name LIKE '%Currie%' OR to_stop_name LIKE '%Currie%' THEN 'Currie St'
            WHEN from_stop_name LIKE '%Victoria Sq%' OR to_stop_name LIKE '%Victoria Sq%' THEN 'Victoria Sq'
            ELSE 'Other CBD / Non-CBD'
        END AS corridor_name,

        dist_km,
        
        -- Calculate travel time by seconds
        (
            CAST(SPLIT(arr_str, ':')[OFFSET(0)] AS INT64) * 3600 +
            CAST(SPLIT(arr_str, ':')[OFFSET(1)] AS INT64) * 60 +
            CAST(SPLIT(arr_str, ':')[OFFSET(2)] AS INT64)
        ) - (
            CAST(SPLIT(dept_str, ':')[OFFSET(0)] AS INT64) * 3600 +
            CAST(SPLIT(dept_str, ':')[OFFSET(1)] AS INT64) * 60 +
            CAST(SPLIT(dept_str, ':')[OFFSET(2)] AS INT64)
        ) AS travel_time_sec

    FROM raw_segments
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
  AND (SAFE_DIVIDE(dist_km, travel_time_sec) * 3600) <= 80.0
  -- eliminate non-critical CBD corrdiors for optimized GROUP BY
  AND corridor_name != 'Other CBD / Non-CBD'
GROUP BY corridor_name, time_bucket
ORDER BY corridor_name, time_bucket;
