/* @bruin
name: core.fact_service_alerts
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
  cluster_by:
    - route_id
depends:
  - staging.stg_rt_service_alerts
  - core.dim_routes
@bruin */

SELECT
  a.ingested_date,
  a.alert_id,
  a.header_text,
  a.description_text,
  a.active_start,
  a.route_id,
  r.route_short_name,
  r.route_type,
  r.route_type_name
FROM `adelaide-metro-505702.staging.stg_rt_service_alerts` a
LEFT JOIN `adelaide-metro-505702.core.dim_routes` r
  ON a.route_id = r.route_id
WHERE a.alert_id IS NOT NULL
