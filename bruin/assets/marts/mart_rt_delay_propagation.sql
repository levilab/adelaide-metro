/* @bruin
name: marts.mart_rt_delay_propagation
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_trips
  - staging.stg_stops
  - staging.stg_routes
@bruin */

WITH raw_latest AS (
    SELECT 
        r.route_short_name,
        tu.stop_sequence,
        s.stop_name,
        tu.trip_id,
        
        -- Tính delay_minutes trực tiếp
        DATETIME_DIFF(
            DATETIME(tu.arrival_time, 'Australia/Adelaide'),
            DATETIME_ADD(
                DATETIME(tu.start_date),
                INTERVAL CAST(SUBSTR(st.arrival_time, 1, 2) AS INT64) * 3600 
                       + CAST(SUBSTR(st.arrival_time, 4, 2) AS INT64) * 60 
                       + CAST(SUBSTR(st.arrival_time, 7, 2) AS INT64) SECOND
            ),
            MINUTE
        ) AS delay_minutes

    FROM `staging.stg_rt_trip_updates` tu
    JOIN `staging.stg_stop_times` st 
      ON tu.trip_id = st.trip_id AND tu.stop_sequence = st.stop_sequence
    JOIN `staging.stg_trips` t ON tu.trip_id = t.trip_id
    JOIN `staging.stg_routes` r ON t.route_id = r.route_id
    JOIN `staging.stg_stops` s ON tu.stop_id = s.stop_id
    WHERE tu.arrival_time IS NOT NULL

    -- Lọc bản ghi mới nhất ngay tại đây
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY tu.trip_id, tu.stop_sequence 
        ORDER BY tu.trip_update_timestamp DESC, tu.feed_timestamp DESC
    ) = 1
),

rt_delay_base AS (
    SELECT 
        route_short_name,
        stop_sequence,
        stop_name,
        trip_id,
        delay_minutes,
        
        -- Lấy delay của trạm kế trước
        LAG(delay_minutes) OVER (
            PARTITION BY trip_id ORDER BY stop_sequence
        ) AS prev_stop_delay_minutes,
        
        -- Lấy delay của trạm đầu tiên (Origin)
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

    -- 1. Độ trễ trung bình tại trạm
    ROUND(AVG(delay_minutes), 2) AS avg_delay_mins,
    
    -- 2. Tải thêm độ trễ (delay_added_mins)
    ROUND(AVG(delay_minutes - COALESCE(prev_stop_delay_minutes, delay_minutes)), 2) AS delay_added_mins,
    
    -- 3. Tỷ lệ lan truyền độ trễ (propagation_factor)
    ROUND(AVG(
        CASE 
            WHEN origin_delay_minutes > 0 THEN (delay_minutes / origin_delay_minutes)
            ELSE 1.0 
        END
    ), 2) AS propagation_factor

FROM rt_delay_base
GROUP BY route_short_name, stop_sequence, stop_name
ORDER BY route_short_name, stop_sequence;