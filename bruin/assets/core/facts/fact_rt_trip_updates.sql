/* @bruin
name: core.fact_rt_trip_updates
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
  cluster_by:
    - route_id
    - stop_id
depends:
  - staging.stg_rt_trip_updates
  - core.fact_scheduled_stop_events
@bruin */

SELECT
  tu.ingested_date,
  tu.entity_id,
  tu.trip_id,
  tu.route_id,
  tu.direction_id,
  tu.feed_timestamp,
  tu.start_date,
  tu.schedule_relationship,
  tu.vehicle_id,
  tu.vehicle_label,
  tu.trip_update_timestamp,
  tu.stop_sequence,
  tu.stop_id,
  tu.arrival_time AS actual_arrival_time,
  se.route_short_name,
  se.route_type,
  se.route_type_name,
  se.stop_name,
  se.scheduled_arrival_seconds,
  DATETIME_ADD(
    DATETIME(tu.start_date),
    INTERVAL se.scheduled_arrival_seconds SECOND
  ) AS scheduled_arrival_datetime,
  DATETIME_DIFF(
    DATETIME(tu.arrival_time, 'Australia/Adelaide'),
    DATETIME_ADD(DATETIME(tu.start_date), INTERVAL se.scheduled_arrival_seconds SECOND),
    MINUTE
  ) AS delay_minutes
FROM `adelaide-metro-505702.staging.stg_rt_trip_updates` tu
LEFT JOIN `adelaide-metro-505702.core.fact_scheduled_stop_events` se
  ON tu.trip_id = se.trip_id
  AND tu.stop_sequence = se.stop_sequence
  AND tu.stop_id = se.stop_id
WHERE tu.trip_id IS NOT NULL
  AND tu.stop_id IS NOT NULL
