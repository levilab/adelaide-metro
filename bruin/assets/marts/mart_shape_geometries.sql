/* @bruin
name: marts.mart_shape_geometries
type: bq.sql
materialization:
  type: table
depends:
  - core.dim_shapes
@bruin */

SELECT 
    shape_id,
    max_shape_dist_traveled * 1000.0 AS actual_distance_m
FROM `adelaide-metro-505702.core.dim_shapes`
WHERE shape_id IS NOT NULL
  AND max_shape_dist_traveled IS NOT NULL;
