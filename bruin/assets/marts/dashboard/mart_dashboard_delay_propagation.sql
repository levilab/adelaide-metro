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
        route_short_name,
        stop_sequence,
        stop_name,
        trip_id,
        delay_minutes
    FROM `adelaide-metro-505702.core.fact_rt_trip_updates`
    WHERE actual_arrival_time IS NOT NULL
      AND delay_minutes IS NOT NULL
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY trip_id, stop_sequence
        ORDER BY trip_update_timestamp DESC, feed_timestamp DESC
    ) = 1
),

rt_delay_base AS (
    SELECT 
        route_short_name,
        stop_sequence,
        stop_name,
        trip_id,
        delay_minutes,
        LAG(delay_minutes) OVER (
            PARTITION BY trip_id ORDER BY stop_sequence
        ) AS prev_stop_delay_minutes,
        FIRST_VALUE(delay_minutes) OVER (
            PARTITION BY trip_id ORDER BY stop_sequence
        ) AS origin_delay_minutes
    FROM raw_latest
)

SELECT 
    route_short_name,
    stop_sequence,
    stop_name,
    COUNT(DISTINCT trip_id) AS total_trips_analyzed,
    ROUND(AVG(delay_minutes), 2) AS avg_delay_mins,
    ROUND(AVG(delay_minutes - COALESCE(prev_stop_delay_minutes, delay_minutes)), 2) AS delay_added_mins,
    ROUND(AVG(
        CASE 
            WHEN origin_delay_minutes > 0 THEN delay_minutes / origin_delay_minutes
            ELSE 1.0
        END
    ), 2) AS propagation_factor
FROM rt_delay_base
GROUP BY route_short_name, stop_sequence, stop_name
ORDER BY route_short_name, stop_sequence;
