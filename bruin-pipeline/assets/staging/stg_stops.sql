/* @bruin
name: staging.stg_stops
type: bq.sql
materialization:
  type: table
depends:
  - raw.gtfs_static_adelaide-metro
@bruin */

SELECT
    CAST(stop_id AS STRING)       AS stop_id,
    CAST(stop_name AS STRING)     AS stop_name,
    CAST(stop_lat AS FLOAT64)     AS latitude,
    CAST(stop_lon AS FLOAT64)     AS longitude
FROM `adelaide-metro-505702.raw.gtfs_stops`
WHERE stop_id IS NOT NULL
