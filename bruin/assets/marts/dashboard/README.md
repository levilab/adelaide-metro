# Dashboard Marts

Data flow: ingestion -> staging -> core dimensions/facts -> dashboard marts -> Streamlit.

This directory groups Bruin assets; the BigQuery dataset remains `marts`.
`dashboard/App.py` reads only the eight tables below.

| Table | Grain / purpose |
| --- | --- |
| `mart_dashboard_network_kpi` | One network snapshot; stop/route counts, departures, busiest route and peak hour. |
| `mart_dashboard_stop_map` | One stop; coordinates and scheduled stop-event count for the map and busiest stops. |
| `mart_dashboard_peak_by_type` | Clock hour and route type; active trips and first-stop departures. |
| `mart_dashboard_coverage_hubs` | One hub with at least five routes; downstream LGA connectivity and nested destination polygons. |
| `mart_dashboard_route_circuity` | Route short/long name and service class; path length and circuity. |
| `mart_dashboard_cbd_corridor_speed` | Corridor and time bucket; scheduled speed and trip volume. |
| `mart_dashboard_delay_propagation` | Route short name, stop sequence and stop name; latest available delay metrics. |
| `mart_dashboard_route_trip_counts` | Route short/long name and type; distinct scheduled trips. |

Counts describe the loaded GTFS timetable, not trips operated on a selected date.
`total_departures` in the stop map counts stop events. In the peak mart it counts
first-stop events; `total_trips` counts trips active within each hour and must not
be summed across hours as a daily unique-trip total. The busiest-route KPI uses
trip counts, not stop-event counts.

Coverage polygons are stored as `connected_lga_polygons`, an array of
`STRUCT<lga STRING, geojson STRING>`. The app loads only the selected hub's
polygons. Existing coverage thresholds and delay/circuity calculations are retained.

Build the new assets and their upstream dependencies before restarting the
dashboard, so cached data is refreshed. The KPI asset depends on the stop map,
route trip counts and peak marts; Bruin's dependency graph determines build order.
Other analytical/intermediate marts remain in the parent directory, including
`mart_shape_geometries`, which feeds circuity. Renaming asset files does not delete
the old tables already present in BigQuery.
