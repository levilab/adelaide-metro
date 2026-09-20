/* @bruin
name: core.fact_scheduled_route_segments
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
    - from_stop_id
depends:
  - core.fact_scheduled_stop_events
@bruin */

WITH ordered_events AS (
  SELECT
    *,
    LEAD(stop_id) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_stop_id,
    LEAD(stop_name) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_stop_name,
    LEAD(stop_lat) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_stop_lat,
    LEAD(stop_lon) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_stop_lon,
    LEAD(lga_name) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_lga_name,
    LEAD(stop_sequence) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_stop_sequence,
    LEAD(scheduled_arrival_seconds) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS scheduled_arrival_seconds,
    LEAD(shape_dist_traveled) OVER (PARTITION BY trip_id ORDER BY stop_sequence) AS to_shape_dist_traveled
  FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
),

paired_events AS (
  SELECT
    trip_id,
    route_id,
    service_id,
    shape_id,
    direction_id,
    route_short_name,
    route_long_name,
    route_type,
    route_type_name,
    agency_id,
    stop_sequence AS from_stop_sequence,
    to_stop_sequence,
    stop_id AS from_stop_id,
    stop_name AS from_stop_name,
    stop_lat AS from_stop_lat,
    stop_lon AS from_stop_lon,
    lga_name AS from_lga_name,
    to_stop_id,
    to_stop_name,
    to_stop_lat,
    to_stop_lon,
    to_lga_name,
    scheduled_departure_seconds,
    scheduled_arrival_seconds,
    departure_hour,
    departure_time_bucket,
    shape_dist_traveled AS from_shape_dist_traveled,
    to_shape_dist_traveled
  FROM ordered_events
  WHERE to_stop_id IS NOT NULL
    AND stop_id != to_stop_id
)

SELECT
  *,
  to_shape_dist_traveled - from_shape_dist_traveled AS segment_distance_km,
  scheduled_arrival_seconds - scheduled_departure_seconds AS scheduled_travel_time_seconds,
  SAFE_DIVIDE(
    to_shape_dist_traveled - from_shape_dist_traveled,
    scheduled_arrival_seconds - scheduled_departure_seconds
  ) * 3600 AS scheduled_speed_kmh
FROM paired_events
WHERE to_shape_dist_traveled > from_shape_dist_traveled
  AND scheduled_arrival_seconds > scheduled_departure_seconds