/* @bruin
name: marts.mart_route_segment_speeds
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_trips
  - staging.stg_stops
@bruin */

WITH raw_segments AS (
    -- 1. Tự JOIN và thêm bộ lọc chặn đứng các trạm trùng vị trí / trùng ID
    SELECT 
        t.route_id,
        st1.departure_time AS dept_str,
        st2.arrival_time AS arr_str,
        st1.shape_dist_traveled AS dist_from,
        st2.shape_dist_traveled AS dist_to,
        st1.stop_id AS from_stop_id,
        st2.stop_id AS to_stop_id
    FROM staging.stg_stop_times st1
    JOIN staging.stg_stop_times st2 
        ON st1.trip_id = st2.trip_id 
        AND st2.stop_sequence = st1.stop_sequence + 1
    JOIN staging.stg_trips t 
        ON st1.trip_id = t.trip_id
    -- SỬA LỖI 1: Loại bỏ tuyệt đối các bản ghi đứng yên tại một trạm
    WHERE st1.stop_id != st2.stop_id 
      AND st2.shape_dist_traveled > st1.shape_dist_traveled
),

converted_segments AS (
    -- 2. Tính toán khoảng cách và quy đổi thời gian sang giây
    SELECT 
        rs.route_id,
        rs.from_stop_id,
        s1.stop_name AS from_stop_name,
        rs.to_stop_id,
        s2.stop_name AS to_stop_name,
        (rs.dist_to - rs.dist_from) AS segment_distance_km,
        
        -- Quy đổi chuỗi STRING vượt quá 24h thành số giây
        (
            CAST(SPLIT(rs.arr_str, ':')[OFFSET(0)] AS INT64) * 3600 +
            CAST(SPLIT(rs.arr_str, ':')[OFFSET(1)] AS INT64) * 60 +
            CAST(SPLIT(rs.arr_str, ':')[OFFSET(2)] AS INT64)
        ) - (
            CAST(SPLIT(rs.dept_str, ':')[OFFSET(0)] AS INT64) * 3600 +
            CAST(SPLIT(rs.dept_str, ':')[OFFSET(1)] AS INT64) * 60 +
            CAST(SPLIT(rs.dept_str, ':')[OFFSET(2)] AS INT64)
        ) AS travel_time_sec

    FROM raw_segments rs
    JOIN staging.stg_stops s1 ON rs.from_stop_id = s1.stop_id
    JOIN staging.stg_stops s2 ON rs.to_stop_id = s2.stop_id
)

-- 3. Thống kê kết quả cuối cùng với công thức vận tốc chuẩn hóa
SELECT 
    route_id,
    from_stop_id,
    from_stop_name,
    to_stop_id,
    to_stop_name,  
    COUNT(*) AS total_trips_analyzed,
    -- Đổi tên cột hiển thị thành km cho đúng bản chất dữ liệu trong ảnh của bạn
    ROUND(AVG(segment_distance_km), 2) AS avg_segment_km,
    ROUND(AVG(travel_time_sec), 2) AS avg_time_sec,
    
    -- SỬA LỖI 2: Công thức tính vận tốc chuẩn khi khoảng cách là KM và thời gian là GIÂY
    -- Công thức: (Km / Giây) * 3600 giây = Km/h
    ROUND(
        SAFE_DIVIDE(AVG(segment_distance_km), AVG(travel_time_sec)) * 3600, 
        2
    ) AS avg_scheduled_speed_kmh

FROM converted_segments
-- Chặn lỗi dữ liệu: Thời gian chạy giữa 2 trạm khác nhau bắt buộc phải lớn hơn 0 giây
WHERE travel_time_sec > 0 
    AND (SAFE_DIVIDE(segment_distance_km, travel_time_sec) * 3600) <= 90.0
GROUP BY route_id, from_stop_id, from_stop_name, to_stop_id, to_stop_name
HAVING COUNT(*) > 5
ORDER BY avg_scheduled_speed_kmh ASC;
