/* @bruin
name: core.dim_vehicles
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
depends:
  - staging.stg_rt_vehicle_positions
  - core.dim_routes
@bruin */

SELECT
  vp.vehicle_id,
  ANY_VALUE(vp.vehicle_label) AS vehicle_label,
  ANY_VALUE(vp.route_id) AS route_id,
  ANY_VALUE(r.route_short_name) AS route_short_name,
  ANY_VALUE(r.route_type) AS route_type,
  ANY_VALUE(r.route_type_name) AS route_type_name,
  MIN(vp.vehicle_timestamp) AS first_seen_at,
  MAX(vp.vehicle_timestamp) AS last_seen_at
FROM `adelaide-metro-505702.staging.stg_rt_vehicle_positions` vp
LEFT JOIN `adelaide-metro-505702.core.dim_routes` r
  ON vp.route_id = r.route_id
WHERE vp.vehicle_id IS NOT NULL
GROUP BY vp.vehicle_id
