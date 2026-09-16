/* @bruin
name: core.dim_routes
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_type
depends:
  - staging.stg_routes
@bruin */

SELECT
  route_id,
  route_short_name,
  route_long_name,
  route_desc,
  route_type,
  CASE route_type
    WHEN 0 THEN 'Tram'
    WHEN 2 THEN 'Rail'
    WHEN 3 THEN 'Bus'
    WHEN 4 THEN 'Ferry'
    WHEN 701 THEN 'Regional Bus'
    WHEN 712 THEN 'Express Bus'
    ELSE 'Other'
  END AS route_type_name,
  agency_id
FROM `adelaide-metro-505702.staging.stg_routes`
WHERE route_id IS NOT NULL
