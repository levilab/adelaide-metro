/* @bruin
name: marts.mart_dashboard_network_kpi
type: bq.sql
materialization:
  type: table
depends:
  - core.dim_routes
  - marts.mart_dashboard_stop_map
  - marts.mart_dashboard_route_trip_counts
  - core.fact_scheduled_stop_events
@bruin */

-- A single network snapshot over the loaded GTFS timetable, not a service day.
WITH stop_totals AS (
    SELECT stop_id, stop_name, SUM(total_departures) AS total_departures
    FROM `adelaide-metro-505702.marts.mart_dashboard_stop_map`
    GROUP BY stop_id, stop_name
),
route_totals AS (
    SELECT route_short_name, SUM(total_trips) AS total_trips
    FROM `adelaide-metro-505702.marts.mart_dashboard_route_trip_counts`
    GROUP BY route_short_name
),
ranked_departures AS (
    SELECT departure_hour,
        ROW_NUMBER() OVER (PARTITION BY trip_id ORDER BY stop_sequence) = 1 AS is_first_stop
    FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
),
hour_totals AS (
    SELECT departure_hour AS hour_of_day, COUNTIF(is_first_stop) AS total_departures
    FROM ranked_departures
    WHERE departure_hour BETWEEN 0 AND 23
    GROUP BY departure_hour
)
SELECT
    (SELECT COUNT(DISTINCT stop_id) FROM `adelaide-metro-505702.marts.mart_dashboard_stop_map`
     WHERE stop_lat IS NOT NULL) AS total_stops,
    (SELECT COALESCE(SUM(total_departures), 0)
     FROM `adelaide-metro-505702.marts.mart_dashboard_stop_map`) AS total_departures,
    (SELECT COUNT(DISTINCT route_short_name)
     FROM `adelaide-metro-505702.core.dim_routes`) AS total_routes,
    (SELECT stop_name FROM stop_totals
     ORDER BY total_departures DESC, stop_id LIMIT 1) AS top_stop,
    (SELECT route_short_name FROM route_totals
     ORDER BY total_trips DESC, route_short_name LIMIT 1) AS busiest_route,
    (SELECT total_trips FROM route_totals
     ORDER BY total_trips DESC, route_short_name LIMIT 1) AS busiest_route_trips,
    (SELECT hour_of_day FROM hour_totals
     ORDER BY total_departures DESC, hour_of_day LIMIT 1) AS peak_hour;
