/* @bruin
name: marts.mart_dashboard_route_lengths
type: bq.sql
materialization:
  type: table
depends:
  - core.dim_shapes
  - core.dim_routes
  - core.dim_trips
@bruin */

WITH route_shapes AS (
  SELECT DISTINCT route_id, shape_id
  FROM `adelaide-metro-505702.core.dim_trips`
  WHERE shape_id IS NOT NULL
)

SELECT
  r.route_id,
  r.route_short_name,
  r.route_long_name,
  r.route_type,
  CAST(ROUND(AVG(CAST(s.max_shape_dist_traveled AS NUMERIC)), 2) AS FLOAT64) AS avg_length_km,
  CAST(ROUND(MIN(CAST(s.max_shape_dist_traveled AS NUMERIC)), 2) AS FLOAT64) AS min_length_km,
  CAST(ROUND(MAX(CAST(s.max_shape_dist_traveled AS NUMERIC)), 2) AS FLOAT64) AS max_length_km,
  COUNT(*) AS shape_count
FROM route_shapes rs
INNER JOIN `adelaide-metro-505702.core.dim_shapes` s ON rs.shape_id = s.shape_id
INNER JOIN `adelaide-metro-505702.core.dim_routes` r ON rs.route_id = r.route_id
WHERE s.max_shape_dist_traveled > 0
GROUP BY r.route_id, r.route_short_name, r.route_long_name, r.route_type;
