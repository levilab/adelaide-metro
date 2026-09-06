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
  -- 1. Lấy trip đại diện cho mỗi shape_id
  SELECT
    shape_id,
    route_id,
    ARRAY_AGG(trip_id ORDER BY trip_id LIMIT 1)[OFFSET(0)] AS representative_trip_id,
    COUNT(DISTINCT trip_id) AS total_trips_count
  FROM `staging.stg_trips`
  WHERE shape_id IS NOT NULL
  GROUP BY shape_id, route_id
),

origin_stations AS (
  -- 2. Xác định tọa độ trạm đầu tiên (Origin) của từng trip đại diện
  SELECT
    st.trip_id,
    ARRAY_AGG(
      ST_GEOGPOINT(s.stop_lon, s.stop_lat) 
      ORDER BY st.stop_sequence ASC 
      LIMIT 1
    )[OFFSET(0)] AS origin_pt
  FROM `staging.stg_stop_times` st
  INNER JOIN `staging.stg_stops` s 
    ON st.stop_id = s.stop_id
  WHERE st.trip_id IN (
    SELECT representative_trip_id 
    FROM shape_representative_trips
  )
  GROUP BY st.trip_id
),

shape_max_span AS (
  -- 3. Tính khoảng cách từ trạm đầu tới trạm xa nhất (Max Reach) cho từng shape_id
  SELECT
    srt.shape_id,
    srt.route_id,
    MAX(srt.total_trips_count) AS total_trips_count,
    MAX(ST_DISTANCE(os.origin_pt, ST_GEOGPOINT(s.stop_lon, s.stop_lat))) AS max_span_m
  FROM shape_representative_trips srt
  INNER JOIN `staging.stg_stop_times` st 
    ON srt.representative_trip_id = st.trip_id
  INNER JOIN `staging.stg_stops` s 
    ON st.stop_id = s.stop_id
  INNER JOIN origin_stations os 
    ON srt.representative_trip_id = os.trip_id
  GROUP BY srt.shape_id, srt.route_id
),

classified_shapes AS (
  -- 4. Phân loại dịch vụ và tính toán các khoảng cách cho từng shape_id
  SELECT
    r.route_short_name,
    r.route_long_name,
    sg.shape_id,
    sg.actual_distance_m,
    ms.max_span_m,
    CASE
      WHEN LOWER(r.route_long_name) LIKE '%school%'
        OR LOWER(r.route_long_name) LIKE '%college%'
        OR (LOWER(r.route_short_name) LIKE '7%' AND LENGTH(r.route_short_name) = 3)
        THEN 'School Service'
      WHEN LOWER(r.route_long_name) LIKE '%loop%'
        OR LOWER(r.route_long_name) LIKE '%circuit%'
        OR LOWER(r.route_long_name) LIKE '%clockwise%'
        OR LOWER(r.route_long_name) LIKE '%township%'
        OR LOWER(r.route_long_name) LIKE '%town service%'
        OR LOWER(r.route_long_name) LIKE '%connector%'
        OR ms.max_span_m < 3000
        OR (sg.actual_distance_m / NULLIF(ms.max_span_m, 0)) >= 2.5
        THEN 'Local Loop / Feeder'
      ELSE 'Regular Commuter'
    END AS service_type
  FROM `marts.mart_shape_geometries` sg
  INNER JOIN shape_max_span ms 
    ON sg.shape_id = ms.shape_id
  INNER JOIN `staging.stg_routes` r 
    ON ms.route_id = r.route_id
)

-- 5. TRUY VẤN CUỐI CÙNG: Gom nhóm theo Route để loại bỏ lặp dữ liệu do trùng thông số shape
SELECT
  route_short_name,
  route_long_name,
  service_type,

  -- Lấy giá trị khoảng cách đại diện (AVG/MAX)
  ROUND(AVG(actual_distance_m) / 1000.0, 2) AS actual_km,
  ROUND(AVG(max_span_m) / 1000.0, 2) AS max_reach_km,

  -- Chỉ số uốn lượn trung bình của tuyến
  ROUND(
    AVG(
      actual_distance_m / NULLIF(
        CASE 
          WHEN service_type = 'Local Loop / Feeder' THEN max_span_m * 2.0
          ELSE max_span_m
        END, 
        0
      )
    ), 
    2
  ) AS circuity_factor,

  -- Số km dư thừa trung bình
  ROUND(
    AVG(
      GREATEST(
        0.0, 
        actual_distance_m - (
          CASE 
            WHEN service_type = 'Local Loop / Feeder' THEN max_span_m * 2.0
            ELSE max_span_m
          END
        )
      )
    ) / 1000.0, 
    2
  ) AS excess_km,

  -- Thống kê số lượng shape_id tạo nên tuyến này
  COUNT(DISTINCT shape_id) AS distinct_shapes_count

FROM classified_shapes
GROUP BY 
  route_short_name,
  route_long_name,
  service_type
ORDER BY circuity_factor DESC;