/* @bruin
name: marts.mart_route_circuity
type: bq.sql
materialization:
  type: table
depends:
  - marts.mart_shape_geometries
  - staging.stg_routes
  - staging.stg_stops
  - staging.stg_trips
  - staging.stg_stop_times
@bruin */

WITH shape_representative_trips AS (
    -- 1. Lấy trip đại diện và đếm tổng số chuyến cho mỗi shape_id
    SELECT 
        shape_id,
        route_id,
        ARRAY_AGG(trip_id LIMIT 1)[OFFSET(0)] AS representative_trip_id,
        COUNT(DISTINCT trip_id) AS total_trips_count
    FROM staging.stg_trips
    WHERE shape_id IS NOT NULL
    GROUP BY shape_id, route_id
),

origin_stations AS (
    -- 2. Xác định chính xác tọa độ trạm đầu tiên (Origin) của từng trip đại diện bằng GROUP BY
    SELECT 
        st.trip_id,
        ARRAY_AGG(ST_GEOGPOINT(s.stop_lon, s.stop_lat) ORDER BY st.stop_sequence ASC LIMIT 1)[OFFSET(0)] AS origin_pt
    FROM staging.stg_stop_times st
    JOIN staging.stg_stops s ON st.stop_id = s.stop_id
    WHERE st.trip_id IN (SELECT representative_trip_id FROM shape_representative_trips)
    GROUP BY st.trip_id
),

shape_max_span AS (
    -- 3. Tính khoảng cách từ trạm đầu tới trạm xa nhất (Max Reach)
    SELECT 
        srt.shape_id,
        srt.route_id,
        MAX(srt.total_trips_count) AS total_trips_count,
        MAX(ST_DISTANCE(os.origin_pt, ST_GEOGPOINT(s.stop_lon, s.stop_lat))) AS max_span_m
    FROM shape_representative_trips srt
    JOIN staging.stg_stop_times st ON srt.representative_trip_id = st.trip_id
    JOIN staging.stg_stops s ON st.stop_id = s.stop_id
    JOIN origin_stations os ON srt.representative_trip_id = os.trip_id
    GROUP BY srt.shape_id, srt.route_id
)

SELECT 
    r.route_short_name,
    r.route_long_name,
    sg.shape_id,
    
    -- Quãng đường thực tế (km)
    ROUND(sg.actual_distance_m / 1000.0, 2) AS actual_km,
    
    -- Khoảng cách vươn xa nhất của tuyến (km)
    ROUND(ms.max_span_m / 1000.0, 2) AS max_reach_km,
    
    -- Phân loại nghiệp vụ (Service Type)
    CASE 
        WHEN LOWER(r.route_long_name) LIKE '%school%' 
             OR LOWER(r.route_long_name) LIKE '%college%' 
             OR (LOWER(r.route_short_name) LIKE '7%' AND LENGTH(r.route_short_name) = 3)
             THEN 'School Service'
        WHEN ms.max_span_m < 3000 
             OR LOWER(r.route_long_name) LIKE '%loop%' 
             OR LOWER(r.route_long_name) LIKE '%circuit%' 
             THEN 'Local Loop / Feeder'
        ELSE 'Regular Commuter'
    END AS service_type,

    -- Chỉ số uốn lượn mới (Adjusted Circuity Factor)
    -- Công thức: Actual Distance / (Max Span * 2)
    ROUND(
        sg.actual_distance_m / NULLIF(ms.max_span_m * 2.0, 0), 
        2
    ) AS adjusted_circuity_factor,

    -- Số km chạy dư thừa so với bán kính phục vụ
    ROUND(
        (sg.actual_distance_m - (ms.max_span_m * 2.0)) / 1000.0, 
        2
    ) AS excess_km

FROM marts.mart_shape_geometries sg
JOIN shape_max_span ms ON sg.shape_id = ms.shape_id
JOIN staging.stg_routes r ON ms.route_id = r.route_id
ORDER BY adjusted_circuity_factor DESC;
