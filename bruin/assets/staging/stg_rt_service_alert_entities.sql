/* @bruin
name: staging.stg_rt_service_alert_entities
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH raw_entities AS (
    SELECT
        ingested_date,
        ingested_at,
        feed_timestamp,
        alert_entity_id AS alert_id,
        route_id,
        ROW_NUMBER() OVER (
            PARTITION BY alert_entity_id, COALESCE(route_id, '') 
            ORDER BY feed_timestamp DESC, ingested_at DESC
        ) AS rn
    FROM `adelaide-metro-505702.streaming.gtfs_realtime_service_alert_informed_entities`
    WHERE ingested_date >= DATE_SUB(CURRENT_DATE('Australia/Adelaide'), INTERVAL 1 DAY)
)

SELECT
    ingested_date,
    ingested_at,
    feed_timestamp,
    alert_id,
    route_id,
FROM raw_entities
WHERE rn = 1