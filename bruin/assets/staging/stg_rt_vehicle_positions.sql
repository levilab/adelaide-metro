/* @bruin
name: staging.stg_rt_vehicle_positions
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.gtfs_realtime_service_alerts
@bruin */

WITH ranked_vehicles AS (
  SELECT
    -- Metadata
    ingested_date,
    CAST(ingested_at AS TIMESTAMP) AS ingested_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    
    -- Entity & Trip identifiers
    CAST(entity_id AS STRING) AS entity_id,
    CAST(trip_id AS STRING) AS trip_id,
    CAST(route_id AS STRING) AS route_id,
    CAST(direction_id AS INT64) AS direction_id,
    PARSE_DATE('%Y-%m-%d', start_date) AS start_date,
    
    -- Vehicle info
    CAST(vehicle_id AS STRING) AS vehicle_id,
    CAST(vehicle_label AS STRING) AS vehicle_label,
    
    -- Spatial / Position data
    CAST(latitude AS FLOAT64) AS latitude,
    CAST(longitude AS FLOAT64) AS longitude,
    CAST(bearing AS FLOAT64) AS bearing,
    CAST(speed AS FLOAT64) AS speed,
    CAST(vehicle_timestamp AS TIMESTAMP) AS vehicle_timestamp,
    
    -- Window function lấy vị trí mới nhất của từng xe
    ROW_NUMBER() OVER (
      PARTITION BY vehicle_id
      ORDER BY ingested_at DESC, vehicle_timestamp DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_vehicle_positions`
)
SELECT
  ingested_date,
  ingested_at,
  feed_timestamp,
  source_gcs_uri,
  entity_id,
  trip_id,
  route_id,
  direction_id,
  start_date,
  vehicle_id,
  vehicle_label,
  latitude,
  longitude,
  bearing,
  speed,
  vehicle_timestamp
FROM
  ranked_vehicles
WHERE
  rn = 1;