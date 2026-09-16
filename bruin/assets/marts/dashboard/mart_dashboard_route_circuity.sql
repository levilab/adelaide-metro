/* @bruin
name: marts.mart_dashboard_route_circuity
type: bq.sql
materialization:
  type: table
depends:
  - marts.mart_shape_geometries
  - core.dim_routes
  - core.dim_trips
  - core.fact_scheduled_stop_events
@bruin */

WITH shape_representative_trips AS (
  SELECT
    shape_id,
    route_id,
    ARRAY_AGG(trip_id ORDER BY trip_id LIMIT 1)[OFFSET(0)] AS representative_trip_id,
    COUNT(DISTINCT trip_id) AS total_trips_count
  FROM `adelaide-metro-505702.core.dim_trips`
  WHERE shape_id IS NOT NULL
  GROUP BY shape_id, route_id
),

origin_stations AS (
  SELECT
    trip_id,
    ARRAY_AGG(
      ST_GEOGPOINT(stop_lon, stop_lat)
      ORDER BY stop_sequence ASC
      LIMIT 1
    )[OFFSET(0)] AS origin_pt
  FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
  WHERE trip_id IN (
    SELECT representative_trip_id
    FROM shape_representative_trips
  )
  GROUP BY trip_id
),

shape_max_span AS (
  SELECT
    srt.shape_id,
    srt.route_id,
    MAX(srt.total_trips_count) AS total_trips_count,
    MAX(ST_DISTANCE(os.origin_pt, ST_GEOGPOINT(se.stop_lon, se.stop_lat))) AS max_span_m
  FROM shape_representative_trips srt
  INNER JOIN `adelaide-metro-505702.core.fact_scheduled_stop_events` se
    ON srt.representative_trip_id = se.trip_id
  INNER JOIN origin_stations os
    ON srt.representative_trip_id = os.trip_id
  WHERE se.stop_lat IS NOT NULL
    AND se.stop_lon IS NOT NULL
  GROUP BY srt.shape_id, srt.route_id
),

classified_shapes AS (
  SELECT
    r.route_short_name,
    r.route_long_name,
    sg.shape_id,
    sg.actual_distance_m,
    ms.max_span_m,
    CASE
      WHEN LOWER(r.route_long_name) LIKE '%school%'
        OR LOWER(r.route_long_name) LIKE '%college%'
        OR (LOWER(r.route_short_name) LIKE '7%' AND LENGTH(r.route_short_name) = 3)
        THEN 'School Service'
      WHEN LOWER(r.route_long_name) LIKE '%loop%'
        OR LOWER(r.route_long_name) LIKE '%circuit%'
        OR LOWER(r.route_long_name) LIKE '%clockwise%'
        OR LOWER(r.route_long_name) LIKE '%township%'
        OR LOWER(r.route_long_name) LIKE '%town service%'
        OR LOWER(r.route_long_name) LIKE '%connector%'
        OR ms.max_span_m < 3000
        OR (sg.actual_distance_m / NULLIF(ms.max_span_m, 0)) >= 2.5
        THEN 'Local Loop / Feeder'
      ELSE 'Regular Commuter'
    END AS service_type
  FROM `adelaide-metro-505702.marts.mart_shape_geometries` sg
  INNER JOIN shape_max_span ms
    ON sg.shape_id = ms.shape_id
  INNER JOIN `adelaide-metro-505702.core.dim_routes` r
    ON ms.route_id = r.route_id
)

SELECT
  route_short_name,
  route_long_name,
  service_type,
  ROUND(AVG(actual_distance_m) / 1000.0, 2) AS actual_km,
  ROUND(AVG(max_span_m) / 1000.0, 2) AS max_reach_km,
  ROUND(
    AVG(
      actual_distance_m / NULLIF(
        CASE 
          WHEN service_type = 'Local Loop / Feeder' THEN max_span_m * 2.0
          ELSE max_span_m
        END,
        0
      )
    ),
    2
  ) AS circuity_factor,
  ROUND(
    AVG(
      GREATEST(
        0.0,
        actual_distance_m - (
          CASE 
            WHEN service_type = 'Local Loop / Feeder' THEN max_span_m * 2.0
            ELSE max_span_m
          END
        )
      )
    ) / 1000.0,
    2
  ) AS excess_km,
  COUNT(DISTINCT shape_id) AS distinct_shapes_count
FROM classified_shapes
GROUP BY route_short_name, route_long_name, service_type
ORDER BY circuity_factor DESC;
