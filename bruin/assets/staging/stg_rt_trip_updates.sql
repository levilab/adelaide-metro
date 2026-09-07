/* @bruin
name: staging.stg_rt_trip_updates
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH ranked_alerts AS (
  SELECT
    ingested_date,
    CAST(ingested_at AS TIMESTAMP) AS ingested_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    CAST(entity_id AS STRING) AS alert_id,
    CAST(header_text AS STRING) AS header_text,
    CAST(url AS STRING) AS alert_url,
    CAST(active_start AS TIMESTAMP) AS active_start,
    
    ROW_NUMBER() OVER (
      PARTITION BY entity_id
      ORDER BY ingested_at DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_service_alerts`
)
SELECT
  ingested_date,
  ingested_at,
  feed_timestamp,
  source_gcs_uri,
  alert_id,
  header_text,
  alert_url,
  active_start
FROM
  ranked_alerts
WHERE
  rn = 1;