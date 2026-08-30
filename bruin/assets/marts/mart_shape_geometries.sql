/* @bruin
name: marts.mart_shape_geometries
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_shapes
@bruin */

WITH clean_shapes AS (
    -- Loại bỏ hoàn toàn dòng trùng lặp nếu bảng staging bị duplicate
    SELECT DISTINCT
        shape_id,
        shape_dist_traveled
    FROM staging.stg_shapes
    WHERE shape_id IS NOT NULL 
      AND shape_dist_traveled IS NOT NULL
)
SELECT 
    shape_id,
    -- Đổi từ KM sang Mét (Vì trong file gốc shape_dist_traveled tính theo KM)
    MAX(shape_dist_traveled) * 1000.0 AS actual_distance_m
FROM clean_shapes
GROUP BY shape_id;