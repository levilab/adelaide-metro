/* @bruin
name: marts.mart_coverage_hubs
type: bq.sql
materialization:
  type: table
depends:
  - staging.stg_stop_times
  - staging.stg_trips
  - staging.stg_routes
  - staging.stg_stops
@bruin */

WITH stops_with_lga AS (
    -- JOIN with polygon to find out which LGA the stop belongs
    SELECT 
        s.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        COALESCE(l.lga_name, 'Other') AS lga
    FROM `adelaide-metro-505702.staging.stg_stops` s
    LEFT JOIN `adelaide-metro-505702.staging.stg_lgas` l
        ON ST_CONTAINS(l.polygon_geom, ST_GEOGPOINT(s.stop_lon, s.stop_lat))
),
 
direct_lga_connections AS (
    -- Find out how many LGAS that a specific stop can reach out to
    SELECT
        st1.stop_id AS origin_stop_id,
        sl2.lga AS destination_lga,
        COUNT(DISTINCT t1.route_id) AS routes_to_lga
    FROM `adelaide-metro-505702.staging.stg_stop_times` st1
    JOIN stops_with_lga sl1 
        ON st1.stop_id = sl1.stop_id
    JOIN `adelaide-metro-505702.staging.stg_trips` t1
        ON st1.trip_id = t1.trip_id
    JOIN `adelaide-metro-505702.staging.stg_stop_times` st2 
        ON st1.trip_id = st2.trip_id AND st1.stop_sequence < st2.stop_sequence
    JOIN stops_with_lga sl2 
        ON st2.stop_id = sl2.stop_id
    WHERE sl2.lga != sl1.lga
    GROUP BY st1.stop_id, sl2.lga
)

SELECT 
    swl.stop_id,
    swl.stop_name,
    swl.lga,
    swl.stop_lat,
    swl.stop_lon,
    
    COUNT(DISTINCT r.route_id) AS route_count,
    COUNT(DISTINCT r.route_type) AS transport_modes,
    
    COUNT(DISTINCT dlc.destination_lga) AS connected_lgas,
    STRING_AGG(DISTINCT CONCAT(dlc.destination_lga, ':', CAST(dlc.routes_to_lga AS STRING)), ' | ') AS connected_lgas_list,

    STRING_AGG(DISTINCT r.route_short_name, ', ' ORDER BY r.route_short_name LIMIT 5) AS top_5_routes,
    STRING_AGG(DISTINCT r.agency_id, ', ') AS operators

FROM stops_with_lga swl
JOIN `adelaide-metro-505702.staging.stg_stop_times` st ON swl.stop_id = st.stop_id
JOIN `adelaide-metro-505702.staging.stg_trips` t ON st.trip_id = t.trip_id
JOIN `adelaide-metro-505702.staging.stg_routes` r ON t.route_id = r.route_id
LEFT JOIN direct_lga_connections dlc ON swl.stop_id = dlc.origin_stop_id
GROUP BY swl.stop_id, swl.stop_name, swl.lga, swl.stop_lat, swl.stop_lon
HAVING route_count >= 5
ORDER BY route_count DESC;