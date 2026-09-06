/* @bruin
name: marts.mart_shape_geometries
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_shapes
@bruin */

SELECT 
    shape_id,
    -- convert to meter
    MAX(shape_dist_traveled) * 1000.0 AS actual_distance_m
FROM staging.stg_shapes
WHERE shape_id IS NOT NULL AND shape_dist_traveled IS NOT NULL
GROUP BY shape_id;