/* @bruin
name: staging.stg_routes
type: bq.sql
materialization:
  type: table
depends:
  - raw.ingest_gtfs_static
@bruin */

SELECT
    CAST(route_id AS STRING) AS route_id,
    CAST(route_short_name AS STRING) AS route_short_name,
    CAST(route_long_name AS STRING) AS route_long_name,
    CAST(route_type AS INT64) AS route_type,
    CAST(agency_id AS STRING) AS agency_id 
FROM `adelaide-metro-505702.raw.gtfs_routes`
WHERE route_id IS NOT NULL