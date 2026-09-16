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

WITH paired_events AS (
  SELECT
    cur.trip_id,
    cur.route_id,
    cur.service_id,
    cur.shape_id,
    cur.direction_id,
    cur.route_short_name,
    cur.route_long_name,
    cur.route_type,
    cur.route_type_name,
    cur.agency_id,
    cur.stop_sequence AS from_stop_sequence,
    nxt.stop_sequence AS to_stop_sequence,
    cur.stop_id AS from_stop_id,
    cur.stop_name AS from_stop_name,
    cur.stop_lat AS from_stop_lat,
    cur.stop_lon AS from_stop_lon,
    cur.lga_name AS from_lga_name,
    nxt.stop_id AS to_stop_id,
    nxt.stop_name AS to_stop_name,
    nxt.stop_lat AS to_stop_lat,
    nxt.stop_lon AS to_stop_lon,
    nxt.lga_name AS to_lga_name,
    cur.scheduled_departure_seconds,
    nxt.scheduled_arrival_seconds,
    cur.departure_hour,
    cur.departure_time_bucket,
    cur.shape_dist_traveled AS from_shape_dist_traveled,
    nxt.shape_dist_traveled AS to_shape_dist_traveled
  FROM `adelaide-metro-505702.core.fact_scheduled_stop_events` cur
  JOIN `adelaide-metro-505702.core.fact_scheduled_stop_events` nxt
    ON cur.trip_id = nxt.trip_id
    AND nxt.stop_sequence = cur.stop_sequence + 1
  WHERE cur.stop_id != nxt.stop_id
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
