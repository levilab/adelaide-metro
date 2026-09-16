/* @bruin
name: core.dim_shapes
type: bq.sql
materialization:
  type: table
  cluster_by:
    - shape_id
depends:
  - staging.stg_shapes
@bruin */

WITH shape_points AS (
  SELECT
    shape_id,
    shape_pt_lat,
    shape_pt_lon,
    SAFE_CAST(shape_pt_sequence AS INT64) AS shape_pt_sequence,
    shape_dist_traveled
  FROM `adelaide-metro-505702.staging.stg_shapes`
  WHERE shape_id IS NOT NULL
    AND shape_pt_lat IS NOT NULL
    AND shape_pt_lon IS NOT NULL
)

SELECT
  shape_id,
  COUNT(*) AS shape_point_count,
  MIN(shape_dist_traveled) AS min_shape_dist_traveled,
  MAX(shape_dist_traveled) AS max_shape_dist_traveled,
  ST_MAKELINE(
    ARRAY_AGG(
      ST_GEOGPOINT(shape_pt_lon, shape_pt_lat)
      ORDER BY shape_pt_sequence
    )
  ) AS shape_geom
FROM shape_points
GROUP BY shape_id
HAVING COUNT(*) >= 2
