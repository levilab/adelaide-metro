/* @bruin
name: staging.stg_shapes
type: bq.sql
materialization:
  type: table
  cluster_by:
    - shape_id
depends:
  - raw.ingest_gtfs_static
@bruin */

SELECT 
  CAST(shape_id AS STRING) as shape_id,
  CAST(shape_pt_lat AS FLOAT64) as shape_pt_lat,
  CAST(shape_pt_lon AS FLOAT64) as shape_pt_lon,
  CAST(shape_pt_sequence AS STRING) as shape_pt_sequence,
  CAST(shape_dist_traveled AS FLOAT64) as shape_dist_traveled
FROM `adelaide-metro-505702.raw.gtfs_shapes`