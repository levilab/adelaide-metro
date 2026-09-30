/* @bruin
name: staging.stg_rt_vehicle_positions
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
@bruin */

WITH ranked_vehicles AS (
  SELECT
    -- Metadata
    ingested_date,
    COALESCE(fetched_date, ingested_date) AS fetched_date,
    CAST(COALESCE(fetched_at, ingested_at) AS TIMESTAMP) AS fetched_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    
    -- Entity & Trip identifiers
    CAST(entity_id AS STRING) AS entity_id,
    CAST(trip_id AS STRING) AS trip_id,
    CAST(route_id AS STRING) AS route_id,
    CAST(direction_id AS INT64) AS direction_id,
    PARSE_DATE('%Y-%m-%d', start_date) AS start_date,
    CAST(schedule_relationship AS STRING) AS schedule_relationship,
    
    -- Vehicle info
    CAST(vehicle_id AS STRING) AS vehicle_id,
    CAST(vehicle_label AS STRING) AS vehicle_label,
    
    -- Spatial / Position data
    CAST(latitude AS FLOAT64) AS latitude,
    CAST(longitude AS FLOAT64) AS longitude,
    CAST(bearing AS FLOAT64) AS bearing,
    CAST(speed AS FLOAT64) AS speed,
    CAST(vehicle_timestamp AS TIMESTAMP) AS vehicle_timestamp,
    CAST(occupancy_status AS STRING) AS occupancy_status,
    
    -- only get the latest positions for every vehicle
    ROW_NUMBER() OVER (
      PARTITION BY vehicle_id
      ORDER BY fetched_at DESC, vehicle_timestamp DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_vehicle_positions`
)
SELECT
  ingested_date,
  fetched_date,
  fetched_at,
  feed_timestamp,
  source_gcs_uri,
  entity_id,
  trip_id,
  route_id,
  direction_id,
  start_date,
  schedule_relationship,
  vehicle_id,
  vehicle_label,
  latitude,
  longitude,
  bearing,
  speed,
  vehicle_timestamp,
  occupancy_status
FROM
  ranked_vehicles
WHERE
  rn = 1;
