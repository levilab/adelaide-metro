/* @bruin
name: staging.stg_rt_service_alert_entities
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
depends:
  - streaming.ingest_gtfs_realtime
@bruin */

WITH ranked_entities AS (
  SELECT
    ingested_date,
    CAST(ingested_at AS TIMESTAMP) AS ingested_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    CAST(alert_entity_id AS STRING) AS alert_id,
    CAST(route_id AS STRING) AS route_id,
    
    ROW_NUMBER() OVER (
      PARTITION BY alert_entity_id, route_id
      ORDER BY ingested_at DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_service_alert_informed_entities`
)
SELECT
  ingested_date,
  ingested_at,
  feed_timestamp,
  source_gcs_uri,
  alert_id,
  route_id
FROM
  ranked_entities
WHERE
  rn = 1;