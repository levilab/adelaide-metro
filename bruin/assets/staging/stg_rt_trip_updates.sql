/* @bruin
name: staging.stg_rt_trip_updates
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
custom_checks:
  - name: trip_updates_successful_poll_is_fresh
    description: Producer successfully polled Trip Updates within the last 3 minutes.
    query: |
      SELECT IF(
        MAX(IF(http_success, polled_at, NULL)) >= TIMESTAMP_SUB(
          CURRENT_TIMESTAMP(),
          INTERVAL 3 MINUTE
        ),
        0,
        1
      )
      FROM
        `adelaide-metro-505702.streaming.gtfs_feed_status`
      WHERE
        feed_name = 'trip_updates'
    value: 0

  - name: unique_trip_stop_per_service_date
    description: One latest stop update per trip instance and stop.
    query: |
      SELECT COUNT(*)
      FROM (
        SELECT
          start_date,
          trip_id,
          stop_sequence,
          stop_id
        FROM
          `adelaide-metro-505702.staging.stg_rt_trip_updates`
        GROUP BY
          start_date,
          trip_id,
          stop_sequence,
          stop_id
        HAVING COUNT(*) > 1
      )
    value: 0
@bruin */

WITH typed_updates AS (
  SELECT
    -- Fetch metadata (legacy fallback supports the rolling deployment)
    ingested_date,
    COALESCE(fetched_date, ingested_date) AS fetched_date,
    CAST(COALESCE(fetched_at, ingested_at) AS TIMESTAMP) AS fetched_at,

    -- Entity and trip
    CAST(entity_id AS STRING) AS entity_id,
    CAST(trip_id AS STRING) AS trip_id,
    CAST(route_id AS STRING) AS route_id,
    CAST(direction_id AS INT64) AS direction_id,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    PARSE_DATE('%Y-%m-%d', start_date) AS start_date,
    CAST(schedule_relationship AS STRING)
      AS schedule_relationship,

    -- Vehicle
    CAST(vehicle_id AS STRING) AS vehicle_id,
    CAST(vehicle_label AS STRING) AS vehicle_label,
    CAST(trip_update_timestamp AS TIMESTAMP)
      AS trip_update_timestamp,

    -- Stop update
    CAST(stop_sequence AS INT64) AS stop_sequence,
    CAST(stop_id AS STRING) AS stop_id,
    CAST(arrival_time AS TIMESTAMP) AS arrival_time

  FROM
    `streaming.gtfs_realtime_trip_updates`

  WHERE COALESCE(fetched_date, ingested_date) >= DATE_SUB(
    CURRENT_DATE('Australia/Adelaide'),
    INTERVAL 1 DAY
  )
),

ranked_updates AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY
        start_date,
        trip_id,
        stop_sequence,
        stop_id
      ORDER BY
        trip_update_timestamp DESC,
        feed_timestamp DESC,  -- in case duplicated trip_update_timestamp due to delay from upstream 
        fetched_at DESC -- in case crash before commit
    ) AS rn
  FROM typed_updates
)

SELECT
  ingested_date,
  fetched_date,
  entity_id,
  trip_id,
  route_id,
  direction_id,
  feed_timestamp,
  start_date,
  schedule_relationship,
  vehicle_id,
  vehicle_label,
  trip_update_timestamp,
  stop_sequence,
  stop_id,
  arrival_time
FROM ranked_updates
WHERE rn = 1;
