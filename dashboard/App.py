import os
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
import requests
from google.cloud import bigquery
from datetime import datetime
import pytz
import re
from dotenv import load_dotenv
import time
load_dotenv()

_BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; adelaide-transit-pulse/1.0)"}

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

st.set_page_config(
    page_title="Adelaide Metro - Network Traffic Analytics",
    page_icon="🚌",
    layout="wide",
    )

@st.cache_data(ttl=3600)
def load_csv_url(url):
    import io
    resp = requests.get(url, headers=_BROWSER_UA, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.content.decode("utf-8-sig")))

# ── Adelaide Theme ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Australian Green & Gold Theme */
    h1, h2, h3 { color: #00843D; } /* Australian National Green */
    .stMetric label { color: #00843D; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #f4f8f5;
        border-radius: 4px 4px 0 0;
        padding: 8px 20px;
        font-weight: bold;
        color: #333;
    }
    .stTabs [aria-selected="true"] {
        background-color: #00843D !important;
        color: white !important;
    }
    .stInfo { border-left: 4px solid #FFCD00; background-color: #fffef0; } /* Wattle Gold */
</style>
""", unsafe_allow_html=True)

import base64 as _b64

@st.cache_resource
def get_flag_b64():
    with open("dashboard/au-flag.png", "rb") as _f:
        return _b64.b64encode(_f.read()).decode()

_flag_b64 = get_flag_b64()
st.markdown(f"""
<div style='display:flex; align-items:center; gap:12px; margin-bottom:0;'>
    <img src='data:image/png;base64,{_flag_b64}' height='44'/>
    <span style='font-size:2.2rem; font-weight:700; line-height:1.2;'> Adelaide Network Analytics</span>
</div>
""", unsafe_allow_html=True)
st.markdown("Adelaide public transport network — routes, stops, and peak hours.")

@st.cache_resource
def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)

@st.cache_data(ttl=3600)
def load_data(query):
    return get_bq_client().query(query).to_dataframe(create_bqstorage_client=False)

@st.cache_data(ttl=3600)
def load_lga_polygons(project_id, stop_id):
    df = get_bq_client().query(f"""
        SELECT 
            polygon.lga,
            polygon.geojson
        FROM `{project_id}.marts.mart_dashboard_coverage_hubs` AS hub,
        UNNEST(hub.connected_lga_polygons) AS polygon
        WHERE hub.stop_id = @stop_id
    """, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("stop_id", "STRING", str(stop_id))
    ])).to_dataframe()

    import json
    features = []
    for _, row in df.iterrows():
        features.append({
            "type": "Feature",
            "properties": {"lga": row["lga"]},
            "geometry": json.loads(row["geojson"]),
        })
    return features

@st.cache_data(ttl=3600)
def load_circuity_data(project_id):
    return get_bq_client().query(f"""
    SELECT 
            route_short_name,
            route_long_name,
            service_type,
            actual_km,
            max_reach_km,
            circuity_factor,
            excess_km,
            distinct_shapes_count
        FROM `{project_id}.marts.mart_dashboard_route_circuity`
    """).to_dataframe()

@st.cache_data(ttl=3600)
def load_cbd_corridor_data(project_id):
    return get_bq_client().query(f"""
    SELECT 
        corridor_name,
        time_bucket,
        unique_trips,
        corridor_avg_speed_kmh
    FROM `{project_id}.marts.mart_dashboard_cbd_corridor_speed`
    ORDER BY corridor_name, time_bucket
    """).to_dataframe()

@st.cache_data(ttl=300)
def load_delay_data(project_id):
    # initilize BigQuery Client
    return get_bq_client().query(f"""
        SELECT 
            route_short_name,
            stop_sequence,
            stop_name,
            total_trips_analyzed,
            avg_delay_mins,
            delay_added_mins,
            propagation_factor,
            data_as_of
        FROM `{project_id}.marts.mart_dashboard_delay_propagation`
        ORDER BY route_short_name, stop_sequence
    """
    ).to_dataframe()

@st.cache_data(ttl=3600)
def format_gtfs_time(t):
    """Convert GTFS time (e.g. 25:30:00) to readable format (e.g. 01:30 +1day)."""
    if not t or ":" not in str(t):
        return t
    parts = str(t).split(":")
    if len(parts) >= 2:
        hours = int(parts[0])
        if hours >= 24:
            # Convert 24:10:00 -> 00:10:00 (Next day)
            hours -= 24
            return f"{hours:02d}:{parts[1]} (+1d)"
        return f"{parts[0]}:{parts[1]}"
    return time_str

ROUTE_TYPE_LABEL = {0: "Tram", 2: "Rail", 3: "Bus", 4: "Ferry",  701: "Regional Bus", 712: "Express Bus"}
COLOR_MAP = {"Tram": "#00c864", 
            "Bus": "#ff3232", 
            "Ferry": "#0078ff",
            "Rail": "#b400ff", 
            "Regional Bus": "#c81e1e",
            "Express Bus": "#ff7800",
            }

adelaide_tz = pytz.timezone("Australia/Adelaide")
visible_types = [0, 3, 4, 2]

def route_type_color(rt):
    return {
        0: [0, 200, 100, 220],
        2: [180, 0, 255, 220],
        3: [255, 50, 50, 220],
        4: [0, 120, 255, 220],
        701: [200, 30, 30, 220],
        712: [255, 120, 0, 220],
    }.get(rt, [200, 200, 200, 180])

def clean_stop_name(name):
    if not name:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', str(name))
    clean = re.sub(r'\[.*?\]', '', clean)
    return ' '.join(clean.split()).replace('"', '')

# ── Single KPI query — replaces 4 separate upfront queries ────────────────────
@st.cache_data(ttl=3600)
def load_kpi(project_id):
    return get_bq_client().query(f"""
    SELECT
        total_stops, total_departures, total_routes, top_stop,
        busiest_route, busiest_route_trips, peak_hour
    FROM `{project_id}.marts.mart_dashboard_network_kpi`
    """).to_dataframe()

kpi = load_kpi(PROJECT_ID).iloc[0]
total_stops         = int(kpi["total_stops"])
total_departures    = int(kpi["total_departures"])
total_routes        = int(kpi["total_routes"])
top_stop            = kpi["top_stop"]
busiest_route       = kpi["busiest_route"]
busiest_route_trips = int(kpi["busiest_route_trips"])
peak_hour           = int(kpi["peak_hour"])

# ── Lazy-load network tab data into session_state ─────────────────────────────
def load_network_data():
    if "stops_df" not in st.session_state:
        stops_df = load_data(f"""
        SELECT stop_id, stop_name, stop_lat, stop_lon, total_departures,
               COALESCE(route_type, 3) AS route_type
        FROM `{PROJECT_ID}.marts.mart_dashboard_stop_map`
        WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
        """)
        stops_df["color"] = stops_df["route_type"].apply(route_type_color)
        stops_df["Transport Type"] = stops_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        st.session_state.stops_df = stops_df

        trips_df = load_data(f"""
        SELECT route_short_name, route_long_name, route_type, total_trips
        FROM `{PROJECT_ID}.marts.mart_dashboard_route_trip_counts`
        ORDER BY total_trips DESC LIMIT 20
        """)
        trips_df["Route Type"] = trips_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        st.session_state.trips_df = trips_df

st.info(
    f"**Network Snapshot:** Adelaide public transport has **{total_stops:,} stops** across **{total_routes} routes**. "
    f"Route **{busiest_route}** is the busiest with **{busiest_route_trips:,} trips**. "
    f"The network peaks at **{peak_hour:02d}:00**. "
    f"The highest-traffic stop is **{top_stop}**."
)

# ── KPI row ────────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("GTFS Stops", f"{total_stops:,}")
col2.metric("GTFS Routes", f"{total_routes:,}")
col3.metric("Total Departures", f"{total_departures:,}")
col4.metric("Peak Hour", f"{peak_hour:02d}:00")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_network, tab_circuity, tab_cbd, tab_delay = st.tabs(["Network Analytics", "Circuity Analysis", "CBD Corridor Speed", "Delay Propagation Monitoring"])

with tab_network:
    with st.spinner("Loading network data..."):
        load_network_data()
    stops_df = st.session_state.stops_df
    trips_df = st.session_state.trips_df

    # ── Transport type selector ────────────────────────────────────────────────
    TYPE_OPTIONS = {
        "🚦 All":        None,
        "🚌 Bus":        3,
        "🚃 Tram":       0,
        "🚄 Rail":       2,
        "⛴️ Ferry":      4,
        "🏠 Regional Bus":  701,
        "⚡ Express Bus":  712,
    }
    selected_label = st.radio(
        "Transport Type", list(TYPE_OPTIONS.keys()),
        horizontal=True, label_visibility="collapsed",
    )
    rt_filter = TYPE_OPTIONS[selected_label]

    # Filtered dataframes (used throughout this tab)
    f_stops = stops_df if rt_filter is None else stops_df[stops_df["route_type"] == rt_filter]
    f_trips = trips_df if rt_filter is None else trips_df[trips_df["route_type"] == rt_filter]
    rt_sql  = "" if rt_filter is None else f"AND route_type = {rt_filter}"
    rt_sql_where = "" if rt_filter is None else f"WHERE route_type = {rt_filter}"

    # ── Stop map ───────────────────────────────────────────────────────────────
    st.subheader("Stop Locations")
    st.caption(f"Showing: **{selected_label}** stops from GTFS open data.")
    try:
        # calculate central coordinates (or fallback to Adelaide coordinates)
        lat_center = f_stops["stop_lat"].mean() if not f_stops.empty else -34.9285
        lon_center = f_stops["stop_lon"].mean() if not f_stops.empty else 138.6007

        st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=f_stops,
                        get_position=["stop_lon", "stop_lat"],
                        get_radius=120,
                        get_fill_color="color",
                        pickable=True,
                        auto_highlight=True,
                    )
                ],
                # Adelaide coordinates: Lat -34.9285, Lon 138.6007
                initial_view_state=pdk.ViewState(
                    latitude=lat_center,
                    longitude=lon_center,
                    zoom=11,
                    pitch=30,
                ),
                tooltip={
                    "text": "{stop_name}\nDepartures: {total_departures}\nType: {Transport Type}"
                },
                map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
            )
        )
    except Exception:
        st.info("Map unavailable — refresh the page to reload.")

    st.divider()

    # ── Busiest stops ──────────────────────────────────────────────────────────
    st.subheader("Top 10 Busiest Stops")
    st.caption("Ranked by total scheduled departures.")
    top_stops = (
        f_stops[["stop_name", "total_departures", "Transport Type"]]
        .sort_values("total_departures", ascending=False).head(10).reset_index(drop=True)
    )
    top_stops.index += 1
    top_stops.columns = ["Stop Name", "Total Departures", "Transport Type"]
    st.dataframe(top_stops, width='stretch')
    st.download_button("⬇ Download CSV", data=top_stops.to_csv(index=False),
                       file_name="adelaide_busiest_stops.csv", mime="text/csv")

    st.divider()

    # ── Coverage Hubs Component ────────────────────────────────────────────────
    st.subheader("Coverage Hubs & Spatial Reach Inspector")
    st.markdown(
        "Explore major transit hubs in Greater Adelaide and inspect direct inter-LGA connectivity."
    )
    TOP_N_DEFAULT = 50

    with st.expander("📚 What am I looking at?", expanded=False):
        st.markdown(f"""
            **What this shows:** which stops let passengers travel directly — same trip, no transfer —
            into the most different Local Government Areas (LGAs). This is a **one-seat-ride reach**
            metric, not transfer-point connectivity.

            **How to read it:**
            - **Table below** — most reliable numbers, best for comparing stops.
            - **Default map** — top {TOP_N_DEFAULT} hubs by route count; darker color = higher reach.
            Toggle "Show all stops" to see everything.
            - **Click a stop** — highlighted regions are the LGAs it reaches directly. Darker fill =
            more routes serving that region (a stronger connection, not just presence).

            **Use case:** if this stop were disrupted (roadworks, route changes), how many regions
            would lose their direct one-seat link to it? A high reach count flags stops worth
            prioritizing for reliability and infrastructure investment — one outage there ripples
            across several areas at once, not just one.
            """)

    hubs_df = load_data(f"""
        SELECT 
            stop_id, stop_name, lga, stop_lat, stop_lon, 
            route_count, connected_lgas, connected_lgas_list,
            transport_modes, top_5_routes, operators
        FROM `{PROJECT_ID}.marts.mart_dashboard_coverage_hubs`
        ORDER BY route_count DESC
    """)

    if hubs_df.empty:
        st.warning("⚠️ No data returned from BigQuery for `marts.mart_dashboard_coverage_hubs`.")
    else:
        # Clean & format spatial coordinates
        hubs_df = hubs_df.dropna(subset=["stop_lat", "stop_lon"]).copy()
        hubs_df["clean_stop_name"] = hubs_df["stop_name"].apply(clean_stop_name)
        hubs_df["stop_lat"] = hubs_df["stop_lat"].astype(float)
        hubs_df["stop_lon"] = hubs_df["stop_lon"].astype(float)

        max_routes_in_db = int(hubs_df["route_count"].max()) if not hubs_df.empty else 2

        # Filters & Control Panel

        col_filter_lga, col_filter_routes, col_view_mode, col_inspector, col_reset = st.columns(
            [1, 1, 1, 2, 0.8]
        )

        with col_filter_lga:
            all_lgas = ["All LGAs"] + sorted(
                [l for l in hubs_df["lga"].dropna().unique() if l != "Other"]
            )
            selected_lga = st.selectbox("Filter LGA:", all_lgas)

        with col_filter_routes:
            min_routes = st.slider(
                "Min Routes:",
                min_value=2,
                max_value=max_routes_in_db,
                value=min(3, max_routes_in_db),
            )

        with col_view_mode:
            st.write("")
            show_all_stops = st.toggle(
                "Show all stops",
                value=False,
                key="show_all_stops",
                help=f"Off: chỉ hiện top {TOP_N_DEFAULT} hub theo route count. On: hiện toàn bộ stop đạt ngưỡng lọc.",
            )
        # Filter dataframe based on selections
        filtered_hubs = hubs_df[hubs_df["route_count"] >= min_routes].copy()
        if selected_lga != "All LGAs":
            filtered_hubs = filtered_hubs[filtered_hubs["lga"] == selected_lga]

        if "inspect_hub" not in st.session_state:
            st.session_state["inspect_hub"] = "None (Show All Hubs)"

        with col_reset:
            st.write("")
            st.write("")
            if st.button("❌ Clear", use_container_width=True):
                st.session_state["inspect_hub"] = "None (Show All Hubs)"
                st.rerun()

        hub_options = ["None (Show All Hubs)"] + filtered_hubs[
            "clean_stop_name"
        ].tolist()

        if st.session_state["inspect_hub"] not in hub_options:
            st.session_state["inspect_hub"] = "None (Show All Hubs)"

        def on_hub_select():
            st.session_state["inspect_hub"] = st.session_state["hub_widget_key"]

        with col_inspector:
            selected_hub_name = st.selectbox(
                "🔍 Inspect Hub Reach (Click Map or Select):",
                options=hub_options,
                index=hub_options.index(st.session_state["inspect_hub"]),
                key="hub_widget_key",
                on_change=on_hub_select,
            )

        current_inspect_hub = st.session_state["inspect_hub"]

        # KPI Summary Metrics Header
        if not filtered_hubs.empty:
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Active Hubs", len(filtered_hubs))
            top_hub = filtered_hubs.iloc[0]
            kpi2.metric("Top Connected Hub", top_hub["clean_stop_name"], f"{top_hub['route_count']} routes")
            kpi3.metric("Avg Reach / Hub", f"{filtered_hubs['connected_lgas'].mean():.1f} LGAs")
            if selected_lga == "All LGAs":
                kpi4.metric("Top Transit LGA", filtered_hubs.groupby("lga")["route_count"].sum().idxmax())
            else:
                kpi4.metric("Total Routes in Area", f"{filtered_hubs['route_count'].sum():,}")
            st.write("")

        if filtered_hubs.empty:
            st.info("ℹ️ No transfer hubs match the selected filters. Try lowering the 'Min Routes' slider.")
        else:
            # Arc & Focus Logic Calculation
            selected_lgas_to_highlight = []
            selected_hub_row = None

            if current_inspect_hub != "None (Show All Hubs)":
                selected_hub_df = filtered_hubs[
                    filtered_hubs["clean_stop_name"] == current_inspect_hub
                ].head(1)
                if not selected_hub_df.empty:
                    selected_hub_row = selected_hub_df.iloc[0]
                    if selected_hub_row["connected_lgas_list"]:
                        selected_lgas_to_highlight = [
                            item.strip().split(":")[0].strip()
                            for item in selected_hub_row["connected_lgas_list"].split("|")
                        ]

            if selected_hub_row is not None:
                st.success(
                    f"📍 **{current_inspect_hub}** (in **{selected_hub_row['lga']}**) connects directly to "
                    f"**{selected_hub_row['connected_lgas']} LGAs** via **{selected_hub_row['route_count']} routes**!"
                )

            # Full-Width Map Render
            layers = []
            is_inspecting = current_inspect_hub != "None (Show All Hubs)"

            if is_inspecting and selected_hub_row is not None:
                # Layer 1: Background Dimmed Hubs
                bg_layer = pdk.Layer(
                    "ScatterplotLayer",
                    id="bg-scatterplot",
                    data=filtered_hubs[filtered_hubs["clean_stop_name"] != current_inspect_hub],
                    get_position=["stop_lon", "stop_lat"],
                    get_radius=60,
                    get_fill_color=[180, 180, 180, 120],
                    pickable=True,
                )
                layers.append(bg_layer)

                # Layer 2: Calculated LGA Centroid Arcs
                hub_lat = float(selected_hub_row["stop_lat"])
                hub_lon = float(selected_hub_row["stop_lon"])

                if selected_lgas_to_highlight:
                    # Parse "lga:routes_to_lga" ra dict {lga: weight} từ connected_lgas_list gốc
                    lga_weights = {}
                    if selected_hub_row["connected_lgas_list"]:
                        for item in selected_hub_row["connected_lgas_list"].split("|"):
                            item = item.strip()
                            if ":" in item:
                                lga_name, weight_str = item.rsplit(":", 1)
                                lga_weights[lga_name.strip()] = int(weight_str)

                    max_weight = max(lga_weights.values()) if lga_weights else 1

                    def weight_to_fill(weight, max_w):
                        # heavy weight -> darker red, light weight -> light yellow.
                        t = weight / max_w if max_w > 0 else 0
                        r = 230
                        g = int(200 * (1 - t))
                        b = int(40 * (1 - t))
                        return [r, g, b, 130]

                    lga_polygons = load_lga_polygons(PROJECT_ID, selected_hub_row["stop_id"])

                    geojson_features = []
                    for feat in lga_polygons:
                        lga_name = feat["properties"]["lga"]
                        if lga_name in lga_weights:
                            weight = lga_weights[lga_name]
                            feat_copy = {
                                "type": "Feature",
                                "geometry": feat["geometry"],
                                "properties": {
                                    "lga": lga_name,
                                    "routes_to_lga": weight,
                                    "fill_color": weight_to_fill(weight, max_weight),
                                    "clean_stop_name": f"Region: {lga_name}",
                                    "route_count": weight,
                                    "connected_lgas": "—",
                                },
                            }
                            geojson_features.append(feat_copy)

                    if geojson_features:
                        coverage_layer = pdk.Layer(
                            "GeoJsonLayer",
                            id="lga-coverage",
                            data={"type": "FeatureCollection", "features": geojson_features},
                            get_fill_color="properties.fill_color",
                            get_line_color=[200, 60, 60, 200],
                            line_width_min_pixels=1.5,
                            stroked=True,
                            filled=True,
                            pickable=True,
                        )
                        layers.append(coverage_layer)

                view_lat, view_lon, view_zoom, view_pitch = hub_lat, hub_lon, 12, 35

            else:
                # select data to display: top N hub (default) or all data points if user toggles on
                if show_all_stops:
                    map_data = filtered_hubs.copy()
                else:
                    map_data = filtered_hubs.sort_values("route_count", ascending=False).head(
                        TOP_N_DEFAULT
                    ).copy()

                map_data["radius_px"] = (map_data["route_count"] ** 0.5) * 25
                map_data["radius_px"] = map_data["radius_px"].clip(upper=150)

                max_reach = max(map_data["connected_lgas"].max(), 1)

                def reach_to_color(reach):
                    t = reach / max_reach
                    r = 255
                    g = int(220 * (1 - t))
                    b = 0
                    return [r, g, b, 200]

                map_data["fill_color"] = map_data["connected_lgas"].apply(reach_to_color)

                hub_layer = pdk.Layer(
                    "ScatterplotLayer",
                    id="all-hubs-scatterplot",
                    data=map_data,
                    get_position=["stop_lon", "stop_lat"],
                    get_radius="radius_px",
                    get_fill_color="fill_color",
                    pickable=True,
                    auto_highlight=True,
                )
                layers.append(hub_layer)
                view_lat, view_lon, view_zoom, view_pitch = -34.9285, 138.6007, 10.8, 0

            map_tooltip = {
                "text": "Stop: {clean_stop_name}\nLGA: {lga}\nRoutes: {route_count}\nDirect Reach: {connected_lgas} LGAs"
            }

            deck_chart = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(
                    latitude=view_lat,
                    longitude=view_lon,
                    zoom=view_zoom,
                    pitch=view_pitch,
                ),
                tooltip=map_tooltip,
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            )

            event = st.pydeck_chart(
                deck_chart,
                on_select="rerun",
                selection_mode="single-object",
                key="hub_map_chart",
            )

            # Handle Map Selection Event
            if event and hasattr(event, "selection") and event.selection:
                objects = event.selection.get("objects", {})
                clicked_obj = None
                for layer_id in ["all-hubs-scatterplot", "bg-scatterplot", "focus-scatterplot"]:
                    if layer_id in objects and objects[layer_id]:
                        clicked_obj = objects[layer_id][0]
                        break

                if clicked_obj and "clean_stop_name" in clicked_obj:
                    clicked_name = clicked_obj["clean_stop_name"]
                    if clicked_name != st.session_state["inspect_hub"]:
                        st.session_state["inspect_hub"] = clicked_name
                        st.rerun()

            # Full-Width Clean Data Table
            st.subheader("📋 Top Coverage Hubs Breakdown")
            
            table_df = filtered_hubs[[
                "clean_stop_name",
                "lga",
                "route_count",
                "connected_lgas",
                "top_5_routes",
            ]].copy()

            table_df.columns = [
                "Stop Name",
                "LGA",
                "Routes Count",
                "Direct Reach",
                "Key Served Routes",
            ]

            max_reach_val = int(hubs_df["connected_lgas"].max()) if not hubs_df.empty else 10

            table_event = st.dataframe(
                            table_df,
                            column_config={
                                "Stop Name": st.column_config.TextColumn("Stop Name", width="large"),
                                "LGA": st.column_config.TextColumn("LGA Region", width="medium"),
                                "Routes Count": st.column_config.NumberColumn("Routes", format="%d lines"),
                                "Direct Reach": st.column_config.ProgressColumn(
                                    "Inter-LGA Reach",
                                    format="%d LGAs",
                                    min_value=0,
                                    max_value=max_reach_val,
                                ),
                                "Key Served Routes": st.column_config.TextColumn("Key Routes", width="large"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            height=350,
                            on_select="rerun",
                            selection_mode="single-row",
                            key="hub_table",
                        )

            if table_event and hasattr(table_event, "selection") and table_event.selection.get("rows"):
                selected_idx = table_event.selection["rows"][0]
                clicked_name = table_df.iloc[selected_idx]["Stop Name"]
                if clicked_name != st.session_state["inspect_hub"]:
                    st.session_state["inspect_hub"] = clicked_name
                    st.rerun()

    st.divider()

with tab_circuity:
    df = load_circuity_data(PROJECT_ID)
    st.subheader("🚌 Adelaide Metro: Route Circuity & Network Efficiency Monitor")
    st.caption("Operational dashboard tracking transit route circuity factors and spatial efficiency across network shapes.")

    with st.expander("🔍 Filter Options", expanded=True):
        # Service Type Filter
        service_types = df["service_type"].dropna().unique().tolist()
        selected_services = st.multiselect(
            "Service Type:",
            options=service_types,
            default=["Regular Commuter"] if "Regular Commuter" in service_types else service_types
        )

        # Circuity Factor Threshold Slider
        min_circuity = st.slider(
            "Minimum Circuity Factor:",
            min_value=1.0,
            max_value=float(df["circuity_factor"].max()) if not df.empty else 5.0,
            value=1.0,
            step=0.1
        )

    # Apply filters
    filtered_df = df[
        (df["service_type"].isin(selected_services)) & 
        (df["circuity_factor"] >= min_circuity)
    ]

    st.divider()

    # HIGH-LEVEL KPI METRICS
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        median_circuity = filtered_df["circuity_factor"].median()
        st.metric(
            label="Median Circuity Factor", 
            value=f"{median_circuity:.2f}" if pd.notnull(median_circuity) else "N/A",
            help="Network median baseline. Benchmark standard: 1.20 - 1.50"
        )

    with kpi2:
        high_circuity_count = (filtered_df["circuity_factor"] >= 1.8).sum()
        st.metric(
            label="High Circuity Routes (>= 1.8)", 
            value=f"{high_circuity_count} routes",
            delta="Review Needed" if high_circuity_count > 0 else "Optimal",
            delta_color="inverse"
        )

    with kpi3:
        total_excess = filtered_df["excess_km"].sum()
        st.metric(
            label="Total Excess Distance / Trip", 
            value=f"{total_excess:,.1f} km" if pd.notnull(total_excess) else "0 km",
            help="Cumulative delta between actual travel distance and maximum spatial reach (* 2)"
        )

    with kpi4:
        total_routes = len(filtered_df)
        st.metric(
            label="Active Routes Displayed", 
            value=f"{total_routes}"
        )

    st.divider()

    # ANALYTICAL VISUALIZATIONS
    col_chart1, col_chart2 = st.columns([1, 1])

    with col_chart1:
        st.subheader("📊 Network Composition by Service Type")
        fig_pie = px.pie(
            df, 
            names="service_type", 
            title="Distribution of Network Route Patterns",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4
        )
        st.plotly_chart(fig_pie, width='stretch')
        st.caption("*Note: School Services & Local Loops intentionally exhibit higher circuity factors due to door-to-door feeder characteristics.*")

    with col_chart2:
        st.subheader("📈 Circuity Factor Distribution")
        fig_hist = px.histogram(
            filtered_df, 
            x="circuity_factor", 
            nbins=20,
            title="Circuity Factor Frequency",
            labels={"circuity_factor": "Circuity Factor"},
            color_discrete_sequence=["#2b5c8f"]
        )
        fig_hist.add_vline(x=1.5, line_dash="dash", line_color="orange", annotation_text="Standard Target (1.5)")
        fig_hist.add_vline(x=1.8, line_dash="dash", line_color="red", annotation_text="Threshold Warning (1.8)")
        st.plotly_chart(fig_hist, width='stretch')

    st.divider()

    # ACTIONABLE MONITORING TABLE
    st.subheader("⚠️ Priority Network Review Table")
    st.markdown("Detailed list of routes prioritized by highest circuity factor based on active filters:")

    # Prepare table display
    display_df = filtered_df.sort_values(by="circuity_factor", ascending=False).copy()

    # Rename columns to English standardized schema
    display_df = display_df.rename(columns={
        "route_short_name": "Route ID",
        "route_long_name": "Route Description",
        "service_type": "Service Type",
        "actual_km": "Actual Distance (km)",
        "max_reach_km": "Max Reach (km)",
        "circuity_factor": "Circuity Factor",
        "excess_km": "Excess Distance (km)",
        "distinct_shapes_count": "Shapes Count"
    })

    # Display formatted dataframe
    st.dataframe(
        display_df[[
            "Route ID", "Route Description", "Service Type", 
            "Actual Distance (km)", "Max Reach (km)", "Circuity Factor", 
            "Excess Distance (km)", "Shapes Count"
        ]],
        column_config={
            "Circuity Factor": st.column_config.NumberColumn(format="%.2f"),
            "Actual Distance (km)": st.column_config.NumberColumn(format="%.2f"),
            "Max Reach (km)": st.column_config.NumberColumn(format="%.2f"),
            "Excess Distance (km)": st.column_config.NumberColumn(format="%.2f"),
            "Shapes Count": st.column_config.NumberColumn(format="%d"),
        },
        width='stretch',
        hide_index=True
    )
    st.divider()

with tab_cbd:
    st.subheader("Adelaide CBD Transit Speed & Volume Analysis")
    st.caption("Analyze vehicle speeds and traffic volumes across major Adelaide CBD corridors by time buckets.")

    # Load data
    try:
        cbd_df = load_cbd_corridor_data(PROJECT_ID)
    except Exception as e:
        st.warning(f"Could not load CBD corridor speed data. Make sure the Bruin asset `mart_dashboard_cbd_corridor_speed` has been executed. Error: {e}")
        cbd_df = pd.DataFrame()

    if cbd_df.empty:
        st.info("No data available in `marts.mart_dashboard_cbd_corridor_speed` yet.")
    else:
        all_corridors = list(cbd_df["corridor_name"].unique())

        # Initialize Session State for CBD corridors if not present
        if "selected_cbd_corridors" not in st.session_state:
            st.session_state["selected_cbd_corridors"] = all_corridors

        def reset_cbd_filters():
            st.session_state["selected_cbd_corridors"] = all_corridors

        # Filters container inside the tab
        with st.expander("⚙️ Filter Options", expanded=True):
            f_col1, f_col2 = st.columns([3, 1])
            with f_col1:
                selected_corridors = st.multiselect(
                    "Select Corridors:",
                    options=all_corridors,
                    key="selected_cbd_corridors"
                )
            with f_col2:
                st.write("")
                st.write("")
                st.button("Reset Filter", on_click=reset_cbd_filters, width='stretch')

        filtered_cbd_df = cbd_df[cbd_df["corridor_name"].isin(selected_corridors)].copy()

        if filtered_cbd_df.empty:
            st.warning("Please select at least one corridor.")
        else:
            # Key Metrics Overview
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Trips", f"{filtered_cbd_df['unique_trips'].sum():,}")
            col2.metric("Average CBD Speed", f"{filtered_cbd_df['corridor_avg_speed_kmh'].mean():.2f} km/h")
            
            slowest_row = filtered_cbd_df.loc[filtered_cbd_df['corridor_avg_speed_kmh'].idxmin()]
            col3.metric("Slowest Segment", f"{slowest_row['corridor_name']} ({slowest_row['corridor_avg_speed_kmh']} km/h)")
            
            # Dynamic Context Highlights
            slowest_corridor = filtered_cbd_df.groupby('corridor_name')['corridor_avg_speed_kmh'].mean().idxmin()
            slowest_speed = filtered_cbd_df.groupby('corridor_name')['corridor_avg_speed_kmh'].mean().min()
            
            busiest_corridor = filtered_cbd_df.groupby('corridor_name')['unique_trips'].sum().idxmax()
            busiest_trips = filtered_cbd_df.groupby('corridor_name')['unique_trips'].sum().max()
            busiest_speed = filtered_cbd_df.groupby('corridor_name')['corridor_avg_speed_kmh'].mean()[busiest_corridor]

            st.info(f"""
            * **Lowest Operating Speed:** **{slowest_corridor}** registers the lowest average speed at **{slowest_speed:.1f} km/h** across selected filters.
            * **Highest Traffic Volume:** **{busiest_corridor}** carries the heaviest load with **{busiest_trips:,} unique trips**, maintaining an average speed of **{busiest_speed:.1f} km/h**.
            """)

            st.divider()

            # Data Preprocessing for Categorical Sorting
            time_order = ['1. AM Peak (7-9h)', '2. Mid Day (10-15h)', '3. PM Peak (16-18h)', '4. Off Peak']
            
            # Match categories dynamically with existing time_bucket strings
            filtered_cbd_df['time_bucket'] = pd.Categorical(
                filtered_cbd_df['time_bucket'], 
                categories=[c for c in time_order if c in filtered_cbd_df['time_bucket'].unique()] or filtered_cbd_df['time_bucket'].unique(), 
                ordered=True
            )
            filtered_cbd_df = filtered_cbd_df.sort_values(['corridor_name', 'time_bucket'])

            # Visualizations (Heatmap & Bar Chart)
            left_col, right_col = st.columns(2)
            
            with left_col:
                st.subheader("1. Velocity Heatmap")
                
                heatmap_data = filtered_cbd_df.pivot_table(
                    index="corridor_name", 
                    columns="time_bucket", 
                    values="corridor_avg_speed_kmh",
                    aggfunc='mean',
                    observed=False
                )
                
                # Build Custom Hover Text Matrix
                hover_text = []
                for index, row in heatmap_data.iterrows():
                    hover_row = []
                    for col in heatmap_data.columns:
                        val = row[col]
                        trips_match = filtered_cbd_df[
                            (filtered_cbd_df['corridor_name'] == index) & 
                            (filtered_cbd_df['time_bucket'] == col)
                        ]['unique_trips']
                        trips = trips_match.values[0] if not trips_match.empty else 0
                        
                        status = "🔴 Severe Bottleneck" if val < 12 else ("🟡 Moderate" if val < 20 else "🟢 Flowing")
                        
                        hover_row.append(
                            f"<b>Corridor:</b> {index}<br>" +
                            f"<b>Time Window:</b> {col}<br>" +
                            f"<b>Avg Speed:</b> {val:.1f} km/h<br>" +
                            f"<b>Unique Trips:</b> {trips:,}<br>" +
                            f"<b>Status:</b> {status}"
                        )
                    hover_text.append(hover_row)
                
                fig_heatmap = px.imshow(
                    heatmap_data,
                    labels=dict(x="Time Window", y="Corridor", color="Speed (km/h)"),
                    color_continuous_scale="RdYlGn",
                    range_color=[5, 35],
                    aspect="auto",
                    text_auto=".1f"
                )

                fig_heatmap.update_traces(
                    hovertemplate="%{customdata}<extra></extra>",
                    customdata=hover_text
                )
                st.plotly_chart(fig_heatmap, width='stretch')

            with right_col:
                st.subheader("2. Traffic Volume (Unique Trips)")
                fig_bar = px.bar(
                    filtered_cbd_df,
                    x="corridor_name",
                    y="unique_trips",
                    color="time_bucket",
                    barmode="group",
                    labels={"corridor_name": "Corridor", "unique_trips": "Unique Trips", "time_bucket": "Time Window"},
                    color_discrete_sequence=px.colors.qualitative.Set2
                )
                st.plotly_chart(fig_bar, width='stretch')
                
            with st.expander("📚 Methodology & Business Definitions"):
                st.markdown("""
                * **Scheduled Speed:** Calculated by dividing actual GTFS `shapes.txt` distance by the time difference between arrival and departure times in `stop_times.txt`.
                * **Unique Trips:** Represents distinct bus runs passing through the corridor segment, deduplicating intermediate stops.
                * **Off-Peak Baseline:** Reflects the baseline infrastructure speed limit without commuter traffic interference.
                """)
    st.divider()

with tab_delay:
    st.subheader("Corridor Delay & Propagation Analytics")
    st.caption("Track how delays start at one stop and build up across the route.")
    count = st_autorefresh(interval=60000, limit=100, key="delay_tab_autorefresh")
    
    try:
        df = load_delay_data(PROJECT_ID)
        latest_update = df["data_as_of"].dropna().max()
        if pd.notna(latest_update):
            latest_update = pd.to_datetime(latest_update, utc=True).tz_convert(
                "Australia/Adelaide"
            )
            st.caption(
                f"Latest realtime update: {latest_update:%d %b %Y, %H:%M:%S %Z}"
            )
    except Exception as e:
        st.warning(f"Failed to connect to BigQuery: ({e}).")

    # ------------------------------------------------------------------------------
    # SIDEBAR FILTERS
    # ------------------------------------------------------------------------------
    routes = sorted(df["route_short_name"].unique())
    # Filter creation
    f_col1, f_col2 = st.columns([1, 3])
    with f_col1:
        # Add key so Streamlit retains choice after rerun/refresh
        selected_route = st.selectbox(
            "🔍 Select Route:", 
            routes, 
            key="delay_selected_route"
        )
        
        # Place Refresh here and clear cache if needed
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    # Filtering by selected route
    route_df = df[df["route_short_name"] == selected_route].sort_values(
        "stop_sequence"
    )

    st.divider()

    # ------------------------------------------------------------------------------
    # KPI METRICS
    # ------------------------------------------------------------------------------
    total_trips = route_df["total_trips_analyzed"].max()
    max_delay_row = route_df.loc[route_df["avg_delay_mins"].idxmax()]
    worst_bottleneck_row = route_df.loc[route_df["delay_added_mins"].idxmax()]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Route", f"Route {selected_route}")
    col2.metric("Total trips analyzed for this route", f"{total_trips:,} trips")
    col3.metric(
        "Stop With Worst Bottleneck",
        f"{worst_bottleneck_row['stop_name']}",
        f"+{worst_bottleneck_row['delay_added_mins']} mins",
        delta_color="inverse",
    )
    col4.metric(
        "Stop With Highest Average Time ",
        f"{max_delay_row['stop_name']}",
        f"{max_delay_row['avg_delay_mins']} mins",
        delta_color="inverse",
    )

    st.divider()

    # ------------------------------------------------------------------------------
    # CHARTS SECTION
    # ------------------------------------------------------------------------------

    # Chart 1: Combo Chart - Delay Added (Bar) vs Total Avg Delay (Line)
    st.subheader("1. Stop-by-Stop Delay Progression & Accumulation")
    st.caption("""
        💡 **Understanding the Metrics:**
        - **Bar (Delay Added):** Instant delay generated (+) or recovered (-) specifically at this stop.
        - **Line (Average Delay):** Cumulative total delay accumulated up to this stop.
        """)

    # Creating labels
    route_df["stop_label"] = (
        route_df["stop_sequence"].astype(str) + ". " + route_df["stop_name"]
    )

    fig_combo = go.Figure()

    # Bar chart: Delay added 
    fig_combo.add_trace(
        go.Bar(
            x=route_df["stop_label"],
            y=route_df["delay_added_mins"],
            name="Delay Added",
            marker_color=[
                "#EF5350" if x > 0 else "#66BB6A" for x in route_df["delay_added_mins"]
            ],
            hovertemplate="Stop: %{x}<br>Delay Added: %{y:.2f} mins<extra></extra>",
        )
    )

    # Line chart: Cumulative Avg Delay
    fig_combo.add_trace(
        go.Scatter(
            x=route_df["stop_label"],
            y=route_df["avg_delay_mins"],
            name="Average Delay Minutes",
            mode="lines+markers",
            line=dict(color="#29B6F6", width=3),
            marker=dict(size=8),
            hovertemplate="Stop: %{x}<br>Total Average Delay: %{y:.2f} mins<extra></extra>",
        )
    )

    fig_combo.update_layout(
        xaxis_title="Stop Sequence",
        yaxis_title="Time (mins)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
    )

    st.plotly_chart(fig_combo, width='stretch')


    # Chart 2: Propagation Factor Line Chart
    st.subheader("2. Stop-to-Stop Delay Propagation Factor")
    st.caption("""
        💡 **Understanding the Factor:**
        - **> 1.0 (Amplified Delay):** Delays are worsening downstream (e.g., **1.5x** means a 2-min initial delay expanded to 3 mins).
        - **= 1.0 (Stable Delay):** Delay remains constant.
        - **< 1.0 (Recovered Delay):** The driver is absorbing the delay and recovering back to schedule.
        """)

    fig_prop = px.line(
        route_df,
        x="stop_label",
        y="propagation_factor",
        markers=True,
        labels={
            "stop_label": "Stop Sequence",
            "propagation_factor": "Propagation Factor",
        },
    )

    # add Baseline = 1.0
    fig_prop.add_hline(
        y=1.0,
        line_dash="dash",
        line_color="gray",
        annotation_text="Baseline (1.0)",
        annotation_position="bottom right",
    )

    fig_prop.update_traces(
        line_color="#AB47BC",
        marker=dict(size=8),
        hovertemplate="Stop: %{x}<br>Propagation Factor: %{y:.2f}<extra></extra>",
    )
    fig_prop.update_layout(height=350)

    st.plotly_chart(fig_prop, width='stretch')

    # ------------------------------------------------------------------------------
    # DATA TABLE DETAIL
    # ------------------------------------------------------------------------------
    with st.expander("📄 View Detailed Analytics Table", expanded=False):
        tab_top, tab_all = st.tabs(
            ["🔥 Top Bottlenecks (Action Needed)", "📋 Full Route Table"]
        )

        with tab_top:
            # Filter stops with highest added delay or propagation factor
            top_bottlenecks = (
                route_df[route_df["delay_added_mins"] > 0]
                .sort_values(by="delay_added_mins", ascending=False)
                .head(10)
            )

            st.dataframe(
                top_bottlenecks[
                    [
                        "stop_sequence",
                        "stop_name",
                        "delay_added_mins",
                        "avg_delay_mins",
                        "propagation_factor",
                    ]
                ],
                column_config={
                    "stop_sequence": st.column_config.NumberColumn("Seq"),
                    "stop_name": "Stop Name",
                    "delay_added_mins": st.column_config.ProgressColumn(
                        "Delay Added (mins)",
                        format="%.2f",
                        min_value=0,
                        max_value=float(
                            route_df["delay_added_mins"].max() or 1
                        ),
                    ),
                    "avg_delay_mins": st.column_config.NumberColumn(
                        "Avg Delay (mins)", format="%.2f"
                    ),
                    "propagation_factor": st.column_config.NumberColumn(
                        "Prop. Factor", format="%.2f"
                    ),
                },
                hide_index=True,
                width='stretch',
            )

        with tab_all:
            st.dataframe(
                route_df[
                    [
                        "stop_sequence",
                        "stop_name",
                        "total_trips_analyzed",
                        "avg_delay_mins",
                        "delay_added_mins",
                        "propagation_factor",
                    ]
                ],
                column_config={
                    "stop_sequence": st.column_config.NumberColumn("Seq"),
                    "stop_name": "Stop Name",
                    "total_trips_analyzed": st.column_config.NumberColumn(
                        "Trips Analyzed"
                    ),
                    "avg_delay_mins": st.column_config.NumberColumn(
                        "Avg Delay (mins)", format="%.2f"
                    ),
                    "delay_added_mins": st.column_config.NumberColumn(
                        "Delay Added (mins)", format="%.2f"
                    ),
                    "propagation_factor": st.column_config.NumberColumn(
                        "Prop. Factor", format="%.2f"
                    ),
                },
                hide_index=True,
                width='stretch',
            )
    time.sleep(60)
    st.rerun()
