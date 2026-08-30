/* @bruin
name: marts.mart_route_circuity
type: bq.sql
materialization:
  type: table
depends:
  - marts.mart_shape_geometries
  - staging.stg_routes
  - staging.stg_stops
  - staging.stg_trips
  - staging.stg_stop_times
@bruin */

WITH shape_routes AS (
    -- Ánh xạ duy nhất shape_id với route_id
    SELECT DISTINCT 
        shape_id, 
        route_id 
    FROM staging.stg_trips 
    WHERE shape_id IS NOT NULL
),

trip_endpoints AS (
    -- Lấy duy nhất 1 trip đại diện cho mỗi shape_id để tìm origin_stop và dest_stop
    SELECT 
        t.shape_id,
        FIRST_VALUE(st.stop_id) OVER (PARTITION BY t.shape_id ORDER BY st.stop_sequence ASC) AS origin_stop_id,
        FIRST_VALUE(st.stop_id) OVER (PARTITION BY t.shape_id ORDER BY st.stop_sequence DESC) AS dest_stop_id
    FROM (
        SELECT 
            shape_id, 
            ARRAY_AGG(trip_id LIMIT 1)[OFFSET(0)] AS trip_id 
        FROM staging.stg_trips 
        WHERE shape_id IS NOT NULL 
        GROUP BY shape_id
    ) t
    JOIN staging.stg_stop_times st ON t.trip_id = st.trip_id
    QUALIFY ROW_NUMBER() OVER (PARTITION BY t.shape_id ORDER BY st.stop_sequence ASC) = 1
)

SELECT 
    r.route_short_name,
    r.route_long_name,
    sg.shape_id,
    ROUND(sg.actual_distance_m / 1000.0, 2) AS actual_km,
    ROUND(
        ST_DISTANCE(
            ST_GEOGPOINT(s1.longitude, s1.latitude),
            ST_GEOGPOINT(s2.longitude, s2.latitude)
        ) / 1000.0, 
        2
    ) AS geodesic_km,

    -- Phân loại tuyến
    CASE 
        WHEN ST_DISTANCE(ST_GEOGPOINT(s1.longitude, s1.latitude), ST_GEOGPOINT(s2.longitude, s2.latitude)) < 3000 THEN 'Loop / Local Feeder'
        ELSE 'Point-to-Point Line'
    END AS route_type,
    
    -- Nếu khoảng cách đường chim bay < 1km (các tuyến vòng tròn Loop), gán NULL để tránh circuity_factor bị bùng nổ
    CASE 
        WHEN ST_DISTANCE(ST_GEOGPOINT(s1.longitude, s1.latitude), ST_GEOGPOINT(s2.longitude, s2.latitude)) < 3000 THEN NULL
        ELSE ROUND(
            sg.actual_distance_m / 
            NULLIF(
                ST_DISTANCE(
                    ST_GEOGPOINT(s1.longitude, s1.latitude),
                    ST_GEOGPOINT(s2.longitude, s2.latitude)
                ), 
                0
            ), 
            2
        ) 
    END AS circuity_factor

FROM marts.mart_shape_geometries sg
JOIN trip_endpoints te ON sg.shape_id = te.shape_id
JOIN shape_routes sr ON sg.shape_id = sr.shape_id
JOIN staging.stg_routes r ON sr.route_id = r.route_id
JOIN staging.stg_stops s1 ON te.origin_stop_id = s1.stop_id
JOIN staging.stg_stops s2 ON te.dest_stop_id = s2.stop_id
ORDER BY circuity_factor DESC NULLS LAST;