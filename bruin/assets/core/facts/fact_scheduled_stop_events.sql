/* @bruin
name: core.fact_scheduled_stop_events
type: bq.sql
materialization:
  type: table
  cluster_by:
    - route_id
    - stop_id
depends:
  - staging.stg_stop_times
  - core.dim_trips
  - core.dim_stops
@bruin */

WITH stop_times AS (
  SELECT
    trip_id,
    stop_id,
    stop_sequence,
    arrival_time,
    departure_time,
    shape_dist_traveled,
    REGEXP_CONTAINS(arrival_time, r'^\d+:\d{2}:\d{2}$') AS valid_arrival_time,
    REGEXP_CONTAINS(departure_time, r'^\d+:\d{2}:\d{2}$') AS valid_departure_time
  FROM `adelaide-metro-505702.staging.stg_stop_times`
  WHERE trip_id IS NOT NULL
    AND stop_id IS NOT NULL
)

SELECT
  st.trip_id,
  st.stop_id,
  st.stop_sequence,
  t.route_id,
  t.service_id,
  t.shape_id,
  t.direction_id,
  t.route_short_name,
  t.route_long_name,
  t.route_type,
  t.route_type_name,
  t.agency_id,
  s.stop_name,
  s.stop_lat,
  s.stop_lon,
  s.lga_name,
  st.arrival_time,
  st.departure_time,
  CASE
    WHEN st.valid_arrival_time THEN
      CAST(SPLIT(st.arrival_time, ':')[OFFSET(0)] AS INT64) * 3600
      + CAST(SPLIT(st.arrival_time, ':')[OFFSET(1)] AS INT64) * 60
      + CAST(SPLIT(st.arrival_time, ':')[OFFSET(2)] AS INT64)
  END AS scheduled_arrival_seconds,
  CASE
    WHEN st.valid_departure_time THEN
      CAST(SPLIT(st.departure_time, ':')[OFFSET(0)] AS INT64) * 3600
      + CAST(SPLIT(st.departure_time, ':')[OFFSET(1)] AS INT64) * 60
      + CAST(SPLIT(st.departure_time, ':')[OFFSET(2)] AS INT64)
  END AS scheduled_departure_seconds,
  CASE
    WHEN st.valid_departure_time THEN MOD(CAST(SPLIT(st.departure_time, ':')[OFFSET(0)] AS INT64), 24)
  END AS departure_hour,
  CASE
    WHEN st.valid_departure_time AND MOD(CAST(SPLIT(st.departure_time, ':')[OFFSET(0)] AS INT64), 24) BETWEEN 7 AND 9 THEN '1. AM Peak (7-9h)'
    WHEN st.valid_departure_time AND MOD(CAST(SPLIT(st.departure_time, ':')[OFFSET(0)] AS INT64), 24) BETWEEN 10 AND 15 THEN '2. Mid Day (10-15h)'
    WHEN st.valid_departure_time AND MOD(CAST(SPLIT(st.departure_time, ':')[OFFSET(0)] AS INT64), 24) BETWEEN 16 AND 18 THEN '3. PM Peak (16-18h)'
    WHEN st.valid_departure_time THEN '4. Off Peak'
  END AS departure_time_bucket,
  st.shape_dist_traveled
FROM stop_times st
JOIN `adelaide-metro-505702.core.dim_trips` t
  ON st.trip_id = t.trip_id
LEFT JOIN `adelaide-metro-505702.core.dim_stops` s
  ON st.stop_id = s.stop_id
