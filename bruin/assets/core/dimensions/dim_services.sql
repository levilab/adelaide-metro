/* @bruin
name: core.dim_services
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_calendar
@bruin */

SELECT
  service_id,
  monday,
  tuesday,
  wednesday,
  thursday,
  friday,
  saturday,
  sunday,
  PARSE_DATE('%Y%m%d', CAST(start_date AS STRING)) AS start_date,
  PARSE_DATE('%Y%m%d', CAST(end_date AS STRING)) AS end_date,
  weekdays_count,
  weekends_count,
  CASE
    WHEN weekdays_count > 0 AND weekends_count > 0 THEN 'Daily / Mixed'
    WHEN weekdays_count > 0 THEN 'Weekday'
    WHEN weekends_count > 0 THEN 'Weekend'
    ELSE 'Inactive'
  END AS service_pattern
FROM `adelaide-metro-505702.staging.stg_calendar`
WHERE service_id IS NOT NULL
