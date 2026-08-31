/* @bruin
name: staging.stg_stops
type: bq.sql
materialization:
  type: table
depends:
  - raw.ingest_gtfs_static
@bruin */

SELECT
    CAST(stop_id AS STRING)       AS stop_id,
    CAST(stop_name AS STRING)     AS stop_name,
    CAST(stop_lat AS FLOAT64)     AS stop_lat,
    CAST(stop_lon AS FLOAT64)     AS stop_lon
FROM `adelaide-metro-505702.raw.gtfs_stops`
WHERE stop_id IS NOT NULL
