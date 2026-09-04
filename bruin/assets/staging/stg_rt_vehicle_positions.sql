/* @bruin
name: staging.stg_rt_vehicle_positions
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH raw_vehicles AS (
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
        latitude,
        longitude,
        bearing,
        speed,
        current_stop_sequence,
        stop_id,
        vehicle_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY vehicle_id 
            ORDER BY vehicle_timestamp DESC, ingested_at DESC
        ) AS rn
    FROM `{{ var.gcp_project }}.streaming.gtfs_realtime_vehicle_positions`
    -- Partition pruning: Chỉ quét dữ liệu trong 1 ngày gần nhất để giảm chi phí scan
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
    latitude,
    longitude,
    bearing,
    speed,
    current_stop_sequence,
    stop_id,
    vehicle_timestamp
FROM raw_vehicles
WHERE rn = 1