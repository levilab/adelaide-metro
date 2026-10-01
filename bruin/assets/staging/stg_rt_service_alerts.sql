/* @bruin
name: staging.stg_rt_service_alerts
type: bq.sql
materialization:
  type: table
  partition_by: ingested_date
custom_checks:
  - name: description_text_contains_no_html_tags
    description: Plain-text alert descriptions must not contain HTML tags.
    query: |
      SELECT COUNT(*)
      FROM `adelaide-metro-505702.staging.stg_rt_service_alerts`
      WHERE description_text IS NOT NULL
        AND REGEXP_CONTAINS(
          description_text,
          r'<[^>]+>'
        )
    value: 0
  
  - name: unique_alert_per_route
    description: At most one latest record per alert and route.
    query: |
      SELECT COUNT(*)
      FROM (
        SELECT alert_id, route_id
        FROM `adelaide-metro-505702.staging.stg_rt_service_alerts`
        GROUP BY alert_id, route_id
        HAVING COUNT(*) > 1
      )
    value: 0

  - name: trip_updates_source_feed_is_fresh
    description: Latest successful poll contains a source snapshot less than 10 minutes old.
    query: |
      SELECT IF(
        COALESCE(
          (
            SELECT feed_timestamp >= TIMESTAMP_SUB(
              CURRENT_TIMESTAMP(),
              INTERVAL 10 MINUTE
            )
            FROM
              `adelaide-metro-505702.streaming.gtfs_feed_status`
            WHERE
              feed_name = 'trip_updates'
              AND http_success = TRUE
            ORDER BY polled_at DESC
            LIMIT 1
          ),
          FALSE
        ),
        0,
        1
      )
    value: 0
@bruin */

WITH ranked_alerts AS (
  SELECT
    ingested_date,
    COALESCE(fetched_date, ingested_date) AS fetched_date,
    CAST(COALESCE(fetched_at, ingested_at) AS TIMESTAMP) AS fetched_at,
    CAST(feed_timestamp AS TIMESTAMP) AS feed_timestamp,
    source_gcs_uri,
    CAST(entity_id AS STRING) AS alert_id,
    CAST(header_text AS STRING) AS header_text,
    CAST(description_text AS STRING) AS description_html,
    TRIM(
      REGEXP_REPLACE(
        REPLACE(
          REPLACE(
            REPLACE(
              REGEXP_REPLACE(
                CAST(description_text AS STRING),
                r'<[^>]+>',
                ' '
              ),
              '&nbsp;',
              ' '
            ),
            '&amp;',
            '&'
          ),
          '&ndash;',
          '–'
        ),
        r'\s+',
        ' '
      )
    ) AS description_text,
    CAST(url AS STRING) AS alert_url,
    CAST(active_start AS TIMESTAMP) AS active_start,
    CAST(route_id AS STRING) AS route_id,
    CAST(cause AS STRING) AS cause,
    CAST(effect AS STRING) AS effect,
    ROW_NUMBER() OVER (
      PARTITION BY entity_id, route_id
      ORDER BY fetched_at DESC
    ) AS rn
  FROM
    `streaming.gtfs_realtime_service_alerts`
)
SELECT
  ingested_date,
  fetched_date,
  alert_id,
  header_text,
  description_html,
  description_text,
  alert_url,
  active_start,
  cause,
  effect,
  route_id
FROM
  ranked_alerts
WHERE
  rn = 1;
