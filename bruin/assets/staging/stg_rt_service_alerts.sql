/* @bruin
name: staging.stg_rt_service_alerts
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.gtfs_realtime_service_alerts
@bruin */

WITH ranked_alerts AS (
  SELECT
    ingested_date,
    CAST(ingested_at AS TIMESTAMP) AS ingested_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    CAST(entity_id AS STRING) AS alert_id,
    CAST(header_text AS STRING) AS header_text,
    CAST(description_text AS STRING) AS description_text,
    CAST(url AS STRING) AS alert_url,
    CAST(active_start AS TIMESTAMP) AS active_start,
    CAST(route_id AS STRING) AS route_id,
    ROW_NUMBER() OVER (
      PARTITION BY entity_id
      ORDER BY ingested_at DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_service_alerts`
)
SELECT
  ingested_date,
  alert_id,
  header_text,
  description_text,
  active_start,
  route_id
FROM
  ranked_alerts
WHERE
  rn = 1;