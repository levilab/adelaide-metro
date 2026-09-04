/* @bruin
name: staging.stg_rt_service_alerts
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH raw_alerts AS (
    SELECT
        ingested_date,
        ingested_at,
        feed_timestamp,
        entity_id AS alert_id,
        cause,
        effect,
        header_text,
        description_text,
        active_start,
        active_end,
        ROW_NUMBER() OVER (
            PARTITION BY entity_id 
            ORDER BY feed_timestamp DESC, ingested_at DESC
        ) AS rn
    FROM `{{ var.gcp_project }}.streaming.gtfs_realtime_service_alerts`
    WHERE ingested_date >= DATE_SUB(CURRENT_DATE('Australia/Adelaide'), INTERVAL 1 DAY)
)

SELECT
    ingested_date,
    ingested_at,
    feed_timestamp,
    alert_id,
    cause,
    effect,
    header_text,
    description_text,
    active_start,
    active_end
FROM raw_alerts
WHERE rn = 1