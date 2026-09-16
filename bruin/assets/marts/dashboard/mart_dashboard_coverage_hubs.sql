/* @bruin
name: marts.mart_dashboard_coverage_hubs
type: bq.sql
materialization:
  type: table
depends:
  - core.fact_scheduled_stop_events
  - core.dim_lgas
@bruin */

WITH stops_with_lga AS (
    SELECT 
        stop_id,
        ANY_VALUE(stop_name) AS stop_name,
        ANY_VALUE(lga_name) AS lga,
        ANY_VALUE(stop_lat) AS stop_lat,
        ANY_VALUE(stop_lon) AS stop_lon
    FROM `adelaide-metro-505702.core.fact_scheduled_stop_events`
    GROUP BY stop_id
),

direct_lga_connections AS (
    SELECT
        st1.stop_id AS origin_stop_id,
        st2.lga_name AS destination_lga,
        COUNT(DISTINCT st1.route_id) AS routes_to_lga
    FROM `adelaide-metro-505702.core.fact_scheduled_stop_events` st1
    JOIN stops_with_lga sl1
        ON st1.stop_id = sl1.stop_id
    JOIN `adelaide-metro-505702.core.fact_scheduled_stop_events` st2
        ON st1.trip_id = st2.trip_id
        AND st1.stop_sequence < st2.stop_sequence
    WHERE st2.lga_name != sl1.lga
    GROUP BY st1.stop_id, st2.lga_name
),

hub_metrics AS (
SELECT 
    swl.stop_id,
    swl.stop_name,
    swl.lga,
    swl.stop_lat,
    swl.stop_lon,
    COUNT(DISTINCT st.route_id) AS route_count,
    COUNT(DISTINCT st.route_type) AS transport_modes,
    COUNT(DISTINCT dlc.destination_lga) AS connected_lgas,
    STRING_AGG(DISTINCT CONCAT(dlc.destination_lga, ':', CAST(dlc.routes_to_lga AS STRING)), ' | ') AS connected_lgas_list,
    STRING_AGG(DISTINCT st.route_short_name, ', ' ORDER BY st.route_short_name LIMIT 5) AS top_5_routes,
    STRING_AGG(DISTINCT st.agency_id, ', ') AS operators
FROM stops_with_lga swl
JOIN `adelaide-metro-505702.core.fact_scheduled_stop_events` st
    ON swl.stop_id = st.stop_id
LEFT JOIN direct_lga_connections dlc
    ON swl.stop_id = dlc.origin_stop_id
GROUP BY swl.stop_id, swl.stop_name, swl.lga, swl.stop_lat, swl.stop_lon
HAVING route_count >= 5
),

coverage_geometry AS (
    SELECT
        dlc.origin_stop_id,
        ARRAY_AGG(STRUCT(
            dlc.destination_lga AS lga,
            ST_ASGEOJSON(lga.polygon_geom) AS geojson
        ) ORDER BY dlc.destination_lga) AS connected_lga_polygons
    FROM direct_lga_connections dlc
    JOIN `adelaide-metro-505702.core.dim_lgas` lga
        ON dlc.destination_lga = lga.lga_name
    GROUP BY dlc.origin_stop_id
)

SELECT hubs.*, geometry.connected_lga_polygons
FROM hub_metrics hubs
LEFT JOIN coverage_geometry geometry ON hubs.stop_id = geometry.origin_stop_id
ORDER BY route_count DESC;
