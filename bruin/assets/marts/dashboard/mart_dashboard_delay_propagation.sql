/* @bruin
name: marts.mart_dashboard_delay_propagation
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_rt_trip_updates
@bruin */

WITH raw_latest AS (
    SELECT 
        start_date,
        route_short_name,
        stop_sequence,
        stop_name,
        trip_id,
        delay_minutes,
        trip_update_timestamp
    FROM `adelaide-metro-505702.core.fact_rt_trip_updates`
    WHERE actual_arrival_time IS NOT NULL
      AND delay_minutes IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY start_date, trip_id, stop_sequence
        ORDER BY trip_update_timestamp DESC, feed_timestamp DESC
    ) = 1
),

rt_delay_base AS (
    SELECT 
        start_date,
        route_short_name,
    stop_sequence,
    stop_name,
        trip_id,
        delay_minutes,
        trip_update_timestamp,
        LAG(delay_minutes) OVER (
            PARTITION BY start_date, trip_id ORDER BY stop_sequence
        ) AS prev_stop_delay_minutes
    FROM raw_latest
)

SELECT 
    route_short_name,
    stop_sequence,
    stop_name,
    COUNT(DISTINCT CONCAT(
        CAST(start_date AS STRING),
        '|',
        trip_id
    )) AS total_trips_analyzed,
    -- Decimal aggregation keeps two-decimal rounding stable across query plans.
    CAST(ROUND(AVG(CAST(delay_minutes AS NUMERIC)), 2) AS FLOAT64) AS avg_delay_mins,
    CAST(ROUND(AVG(CAST(delay_minutes - COALESCE(prev_stop_delay_minutes, delay_minutes) AS NUMERIC)), 2) AS FLOAT64) AS delay_added_mins,
    MAX(trip_update_timestamp) AS data_as_of
FROM rt_delay_base
GROUP BY route_short_name, stop_sequence, stop_name
ORDER BY route_short_name, stop_sequence;
