/* @bruin
name: staging.stg_calendar
type: bq.sql
materialization:
  type: table
depends:
  - raw.ingest_gtfs_static
@bruin */

WITH casted AS (
  SELECT
    CAST(service_id AS STRING) AS service_id,
    CAST(monday AS INT64) AS monday,
    CAST(tuesday AS INT64) AS tuesday,
    CAST(wednesday AS INT64) AS wednesday,
    CAST(thursday AS INT64) AS thursday,
    CAST(friday AS INT64) AS friday,
    CAST(saturday AS INT64) AS saturday,
    CAST(sunday AS INT64) AS sunday,
    CAST(start_date AS INT64) AS start_date,
    CAST(end_date AS INT64) AS end_date
  FROM `adelaide-metro-505702.raw.gtfs_calendar`
  WHERE service_id IS NOT NULL
)
SELECT
  *,
  (monday + tuesday + wednesday + thursday + friday) AS weekdays_count,
  (saturday + sunday) AS weekends_count
FROM casted