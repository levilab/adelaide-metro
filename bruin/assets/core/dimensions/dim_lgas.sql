/* @bruin
name: core.dim_lgas
type: bq.sql
materialization:
  type: table
depends:
  - raw.geo_lgas
@bruin */

SELECT
  CAST(lga_name AS STRING) AS lga_name,
  polygon_geom
FROM `adelaide-metro-505702.staging.stg_lgas`
WHERE lga_name IS NOT NULL
  AND polygon_geom IS NOT NULL
