/* @bruin
name: marts.mart_dashboard_lga_service
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
  - core.dim_lgas
columns:
  - name: lga_name
    type: string
    checks:
      - name: not_null
      - name: unique
@bruin */

-- One row per LGA over the loaded timetable, not a selected service day.
WITH lga_metrics AS (
    SELECT
        lga_name,
        COUNT(DISTINCT stop_id) AS stop_count,
        COUNT(DISTINCT route_id) AS route_count,
        COUNT(*) AS scheduled_stop_visits
    FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
    GROUP BY lga_name
)

SELECT
    lgas.lga_name,
    metrics.stop_count,
    metrics.route_count,
    metrics.scheduled_stop_visits
FROM lga_metrics AS metrics
JOIN `adelaide-metro-505702.core.dim_lgas` AS lgas
    ON metrics.lga_name = lgas.lga_name;
