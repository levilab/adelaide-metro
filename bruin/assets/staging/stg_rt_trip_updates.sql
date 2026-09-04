/* @bruin
name: staging.stg_rt_trip_updates
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH raw_trip_updates AS (
    SELECT
        ingested_date,
        ingested_at,
        feed_timestamp,
        entity_id,
        trip_id,
        route_id,
        direction_id,
        start_date,
        vehicle_id,
        vehicle_label,
        trip_update_timestamp,
        stop_id,
        stop_sequence,
        arrival_time,
        arrival_delay_seconds,
        departure_time,
        departure_delay_seconds,
        ROW_NUMBER() OVER (
            PARTITION BY trip_id, stop_sequence 
            ORDER BY trip_update_timestamp DESC, ingested_at DESC
        ) AS rn
    FROM `adelaide-metro-505702.streaming.gtfs_realtime_trip_updates`
    WHERE ingested_date >= DATE_SUB(CURRENT_DATE('Australia/Adelaide'), INTERVAL 1 DAY)
)

SELECT
    ingested_date,
    ingested_at,
    feed_timestamp,
    entity_id,
    trip_id,
    route_id,
    direction_id,
    start_date,
    vehicle_id,
    vehicle_label,
    trip_update_timestamp,
    stop_id,
    stop_sequence,
    arrival_time,
    arrival_delay_seconds,
    departure_time,
    departure_delay_seconds
FROM raw_trip_updates
WHERE rn = 1