/* @bruin
name: core.dim_stops
type: bq.sql
materialization:
  type: table
  cluster_by:
    - lga_name
depends:
  - staging.stg_stops
  - core.dim_lgas
@bruin */

SELECT
  s.stop_id,
  s.stop_name,
  s.stop_lat,
  s.stop_lon,
  ST_GEOGPOINT(s.stop_lon, s.stop_lat) AS stop_geom,
  COALESCE(l.lga_name, 'Other') AS lga_name
FROM `adelaide-metro-505702.staging.stg_stops` s
LEFT JOIN `adelaide-metro-505702.core.dim_lgas` l
  ON ST_CONTAINS(l.polygon_geom, ST_GEOGPOINT(s.stop_lon, s.stop_lat))
WHERE s.stop_id IS NOT NULL
  AND s.stop_lat IS NOT NULL
  AND s.stop_lon IS NOT NULL
