/* @bruin
name: staging.stg_trips
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
depends:
  - raw.gtfs_static_adelaide-metro
@bruin */

SELECT
    CAST(trip_id AS STRING) AS trip_id,
    CAST(route_id AS STRING)     AS route_id,
    CAST(service_id AS STRING)   AS service_id
FROM `adelaide-metro-505702.raw.gtfs_trips`
WHERE trip_id IS NOT NULL
