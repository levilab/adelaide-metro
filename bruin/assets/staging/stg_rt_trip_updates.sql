/* @bruin
name: staging.stg_rt_trip_updates
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH ranked_updates AS (
  SELECT
    -- Metadata
    ingested_date,
    
    -- Entity & Trip identifiers
    CAST(entity_id AS STRING) AS entity_id,
    CAST(trip_id AS STRING) AS trip_id,
    CAST(route_id AS STRING) AS route_id,
    CAST(direction_id AS INT64) AS direction_id,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    PARSE_DATE('%Y-%m-%d', start_date) AS start_date,
    CAST(schedule_relationship AS INT64) AS schedule_relationship,
    
    -- Vehicle info
    CAST(vehicle_id AS STRING) AS vehicle_id,
    CAST(vehicle_label AS STRING) AS vehicle_label,
    CAST(trip_update_timestamp AS TIMESTAMP) AS trip_update_timestamp,
    
    -- Stop updates
    CAST(stop_sequence AS INT64) AS stop_sequence,
    CAST(stop_id AS STRING) AS stop_id,
    CAST(arrival_time AS TIMESTAMP) AS arrival_time,
    
    -- Window function lấy record mới nhất cho từng stop của từng trip
    ROW_NUMBER() OVER (
      PARTITION BY trip_id, stop_sequence, stop_id
      ORDER BY trip_update_timestamp DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_trip_updates`
)
SELECT
  ingested_date,
  entity_id,
  trip_id,
  route_id,
  direction_id,
  feed_timestamp,
  start_date,
  schedule_relationship,
  vehicle_id,
  vehicle_label,
  trip_update_timestamp,
  stop_sequence,
  stop_id,
  arrival_time
FROM
  ranked_updates
WHERE
  rn = 1;