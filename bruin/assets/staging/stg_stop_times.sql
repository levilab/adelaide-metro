/* @bruin
name: staging.stg_stop_times
type: bq.sql
materialization:
  type: table
  cluster_by:
    - stop_id
    - trip_id
depends:
  - raw.ingest_gtfs_static
@bruin */

-- cast a string

SELECT
    CAST(trip_id AS STRING)         AS trip_id, 
    CAST(stop_id AS STRING)         AS stop_id,
    CAST(stop_sequence AS INT64)    AS stop_sequence,
    CAST(arrival_time AS STRING)    AS arrival_time,
    CAST(departure_time AS STRING)  AS departure_time
FROM `adelaide-metro-505702.raw.gtfs_stop_times`
WHERE trip_id IS NOT NULL
    AND stop_id IS NOT NULL