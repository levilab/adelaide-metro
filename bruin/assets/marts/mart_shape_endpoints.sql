/* @bruin
name: marts.mart_shape_endpoints
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_trips
  - staging.stg_stop_times
  - staging.stg_stops
@bruin */

-- Lấy điểm bắt đầu và kết thúc của từng shape_id
WITH shape_endpoints AS (
    SELECT DISTINCT
        t.shape_id,
        FIRST_VALUE(st.stop_id) OVER (PARTITION BY t.shape_id ORDER BY st.stop_sequence ASC) AS origin_stop_id,
        FIRST_VALUE(st.stop_id) OVER (PARTITION BY t.shape_id ORDER BY st.stop_sequence DESC) AS dest_stop_id
    FROM staging.stg_trips t
    JOIN staging.stg_stop_times st ON t.trip_id = st.trip_id
    WHERE t.shape_id IS NOT NULL
)
SELECT 
    se.shape_id,
    se.origin_stop_id,
    se.dest_stop_id,
    -- Tính khoảng cách đường chim bay giữa trạm đầu và trạm cuối (mét)
    ST_DISTANCE(
        ST_GEOGPOINT(s1.stop_lon, s1.stop_lat),
        ST_GEOGPOINT(s2.stop_lon, s2.stop_lat)
    ) AS geodesic_distance_m
FROM shape_endpoints se
JOIN staging.stg_stops s1 ON se.origin_stop_id = s1.stop_id
JOIN staging.stg_stops s2 ON se.dest_stop_id = s2.stop_id;