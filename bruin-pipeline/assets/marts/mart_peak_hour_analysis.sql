/* @bruin
name: marts.mart_peak_hour_analysis
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
@bruin */

SELECT
    CAST(SPLIT(departure_time, ':')[OFFSET(0)] AS INT64) AS hour_of_day,
    COUNT(*) AS total_departures
FROM `adelaide-metro-505702.staging.stg_stop_times`
WHERE departure_time IS NOT NULL AND stop_sequence = 1
GROUP BY hour_of_day
ORDER BY total_departures DESC
