/* @bruin
name: core.fact_rt_vehicle_positions
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
  cluster_by:
    - route_id
    - vehicle_id
depends:
  - staging.stg_rt_vehicle_positions
  - core.dim_routes
  - core.dim_vehicles
@bruin */

SELECT
  vp.ingested_date,
  vp.ingested_at,
  vp.feed_timestamp,
  vp.source_gcs_uri,
  vp.entity_id,
  vp.trip_id,
  vp.route_id,
  r.route_short_name,
  r.route_type,
  r.route_type_name,
  vp.direction_id,
  vp.start_date,
  vp.vehicle_id,
  vp.vehicle_label,
  vp.latitude,
  vp.longitude,
  ST_GEOGPOINT(vp.longitude, vp.latitude) AS vehicle_geom,
  vp.bearing,
  vp.speed,
  vp.vehicle_timestamp,
  EXTRACT(HOUR FROM DATETIME(vp.vehicle_timestamp, 'Australia/Adelaide')) AS vehicle_hour
FROM `adelaide-metro-505702.staging.stg_rt_vehicle_positions` vp
LEFT JOIN `adelaide-metro-505702.core.dim_routes` r
  ON vp.route_id = r.route_id
WHERE vp.vehicle_id IS NOT NULL
  AND vp.latitude IS NOT NULL
  AND vp.longitude IS NOT NULL
