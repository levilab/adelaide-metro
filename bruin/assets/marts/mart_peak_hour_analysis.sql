/* @bruin
name: marts.mart_peak_hour_analysis
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
@bruin */

SELECT
    departure_hour AS hour_of_day,
    COUNT(*) AS total_departures
FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
WHERE departure_hour IS NOT NULL
  AND is_first_stop
GROUP BY hour_of_day
ORDER BY total_departures DESC
