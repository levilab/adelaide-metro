/* @bruin
name: staging.stg_trips
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
depends:
  - raw.ingest_gtfs_static
@bruin */

SELECT
    CAST(trip_id AS STRING)           AS trip_id,
    CAST(route_id AS STRING)          AS route_id,
    CAST(service_id AS STRING)        AS service_id,
    CAST(trip_headsign AS STRING)     AS trip_headsign,
    CAST(trip_short_name AS STRING)   AS trip_short_name,
    CAST(direction_id AS STRING)      AS direction_id,
    CAST(block_id AS STRING)          AS block_id,
    CAST(shape_id AS STRING)          AS shape_id,
    CAST(wheelchair_accessible AS STRING)   AS wheelchair_accessible
FROM `adelaide-metro-505702.raw.gtfs_trips`
WHERE trip_id IS NOT NULL
