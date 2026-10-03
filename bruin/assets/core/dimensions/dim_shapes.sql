/* @bruin
name: core.dim_shapes
type: bq.sql
materialization:
  type: table
  cluster_by:
    - shape_id
depends:
  - staging.stg_shapes
columns:
  - name: shape_id
    type: string
    checks:
      - name: not_null
      - name: unique
@bruin */

WITH shape_points AS (
  SELECT
    shape_id,
    shape_dist_traveled
  FROM `adelaide-metro-505702.staging.stg_shapes`
  WHERE shape_id IS NOT NULL
    AND shape_pt_lat IS NOT NULL
    AND shape_pt_lon IS NOT NULL
)

SELECT
  shape_id,
  MAX(shape_dist_traveled) AS max_shape_dist_traveled
FROM shape_points
GROUP BY shape_id
HAVING COUNT(*) >= 2
