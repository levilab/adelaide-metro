/* @bruin
name: core.dim_trips
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
    - service_id
depends:
  - staging.stg_trips
  - core.dim_routes
  - core.dim_services
@bruin */

SELECT
  t.trip_id,
  t.route_id,
  t.service_id,
  t.shape_id,
  t.trip_headsign,
  t.trip_short_name,
  SAFE_CAST(t.direction_id AS INT64) AS direction_id,
  t.block_id,
  t.wheelchair_accessible,
  r.route_short_name,
  r.route_long_name,
  r.route_type,
  r.route_type_name,
  r.agency_id,
  s.service_pattern
FROM `adelaide-metro-505702.staging.stg_trips` t
LEFT JOIN `adelaide-metro-505702.core.dim_routes` r
  ON t.route_id = r.route_id
LEFT JOIN `adelaide-metro-505702.core.dim_services` s
  ON t.service_id = s.service_id
WHERE t.trip_id IS NOT NULL
