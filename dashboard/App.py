import os
import streamlit as st
import pandas as pd
import pydeck as pdk
import plotly.express as px
import requests
from google.cloud import bigquery
from datetime import datetime
import pytz
import re
from dotenv import load_dotenv
load_dotenv()

_BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; hk-transit-pulse/1.0)"}

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

st.set_page_config(
    page_title="Adelaide Transit Pulse",
    page_icon="🚌",
    layout="wide"
)

@st.cache_data(ttl=3600)
def load_csv_url(url):
    import io
    resp = requests.get(url, headers=_BROWSER_UA, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.content.decode("utf-8-sig")))

# ── HK Theme ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* HK red accent */
    h1, h2, h3 { color: #C8102E; }
    .stMetric label { color: #C8102E; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #f5f5f5;
        border-radius: 4px 4px 0 0;
        padding: 8px 20px;
        font-weight: bold;
        color: #333;
    }
    .stTabs [aria-selected="true"] {
        background-color: #C8102E !important;
        color: white !important;
    }
    .stInfo { border-left: 4px solid #C8102E; }
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
    <span style='font-size:2.2rem; font-weight:700; line-height:1.2;'> Adelaide Transit Pulse</span>
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
def load_peak_by_type(project_id, route_type=None):
    rt_sql = f"AND route_type = {route_type}" if route_type is not None else ""
    return get_bq_client().query(f"""
    SELECT CAST(SUBSTR(st.departure_time, 1, 2) AS INT64) AS hour_of_day,
            CASE CAST(r.route_type AS INT64)
            WHEN 3 THEN 'Bus'
            WHEN 0 THEN 'Tram'
            WHEN 4 THEN 'Ferry'
            WHEN 2 THEN 'Rail'
            WHEN 701 THEN 'Regional Bus'
            ELSE 'Express Bus'
        END AS route_type_name,
           COUNT(DISTINCT t.trip_id) AS total_trips
    FROM `{project_id}.staging.stg_stop_times` st
    JOIN `{project_id}.staging.stg_trips` t ON st.trip_id = t.trip_id
    JOIN `{project_id}.staging.stg_routes` r ON t.route_id = r.route_id
    WHERE REGEXP_CONTAINS(st.departure_time, r'^\\d+:\\d{{2}}:\\d{{2}}$')
      AND CAST(SUBSTR(st.departure_time, 1, 2) AS INT64) BETWEEN 0 AND 23
      {rt_sql}
    GROUP BY hour_of_day, route_type_name ORDER BY hour_of_day
    """).to_dataframe()

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

au_tz = pytz.timezone("Australia/South")
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
        (SELECT COUNT(*) FROM `{project_id}.marts.mart_ranked_stops`
         WHERE stop_lat IS NOT NULL) AS total_stops,
        (SELECT SUM(total_departures) FROM `{project_id}.marts.mart_ranked_stops`) AS total_departures,
        (SELECT COUNT(DISTINCT route_short_name) FROM `{project_id}.staging.stg_routes`) AS total_routes,
        (SELECT stop_name FROM `{project_id}.marts.mart_ranked_stops`
         ORDER BY total_departures DESC LIMIT 1) AS top_stop,
        (SELECT route_short_name FROM `{project_id}.marts.mart_trips_per_route`
         ORDER BY total_departures DESC LIMIT 1) AS busiest_route,
        (SELECT total_departures FROM `{project_id}.marts.mart_trips_per_route`
         ORDER BY total_departures DESC LIMIT 1) AS busiest_route_trips,
        (SELECT hour_of_day FROM `{project_id}.marts.mart_peak_hour_analysis`
         ORDER BY total_departures DESC LIMIT 1) AS peak_hour
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
        FROM `{PROJECT_ID}.marts.mart_ranked_stops`
        WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
        """)
        stops_df["color"] = stops_df["route_type"].apply(route_type_color)
        stops_df["Transport Type"] = stops_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        st.session_state.stops_df = stops_df

        trips_df = load_data(f"""
        SELECT r.route_short_name, r.route_long_name, r.route_type, COUNT(t.trip_id) AS total_trips
        FROM `{PROJECT_ID}.staging.stg_trips` t
        JOIN `{PROJECT_ID}.staging.stg_routes` r ON t.route_id = r.route_id
        GROUP BY r.route_short_name, r.route_long_name, r.route_type
        ORDER BY total_trips DESC LIMIT 20
        """)
        trips_df["Route Type"] = trips_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        st.session_state.trips_df = trips_df

        st.session_state.peak_df = load_data(f"""
        SELECT hour_of_day, total_departures
        FROM `{PROJECT_ID}.marts.mart_peak_hour_analysis`
        WHERE hour_of_day BETWEEN 0 AND 23
        ORDER BY hour_of_day
        """)

st.info(
    f"**Network Snapshot:** HK public transport has **{total_stops:,} stops** across **{total_routes} routes**. "
    f"Route **{busiest_route}** is the busiest with **{busiest_route_trips:,} trips**. "
    f"The network peaks at **{peak_hour:02d}:00** — morning rush hour. "
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
tab_network, = st.tabs(["Network Analytics"])

with tab_network:
    with st.spinner("Loading network data..."):
        load_network_data()
    stops_df = st.session_state.stops_df
    trips_df = st.session_state.trips_df
    peak_df  = st.session_state.peak_df

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

    st.info(
        ""
    )

    # Filtered dataframes (used throughout this tab)
    f_stops = stops_df if rt_filter is None else stops_df[stops_df["route_type"] == rt_filter]
    f_trips = trips_df if rt_filter is None else trips_df[trips_df["route_type"] == rt_filter]
    rt_sql  = "" if rt_filter is None else f"AND route_type = {rt_filter}"
    rt_sql_where = "" if rt_filter is None else f"WHERE route_type = {rt_filter}"

    st.divider()

    # ── Stop map ───────────────────────────────────────────────────────────────
    st.subheader("Stop Locations")
    st.caption(f"Showing: **{selected_label}** stops from GTFS open data.")
    try:
        # Tính tọa độ trung tâm động dựa trên dữ liệu lọc (hoặc fallback về tâm Adelaide)
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
                # Tọa độ trung tâm Adelaide: Lat -34.9285, Lon 138.6007
                initial_view_state=pdk.ViewState(
                    stop_lat=lat_center,
                    stop_lon=lon_center,
                    zoom=11,
                    pitch=30,
                ),
                tooltip={
                    "text": "{stop_name}\nDepartures: {total_departures}\nType: {Transport Type}"
                },
                # Style Mapbox chuẩn, sạch đẹp, load cực nhanh và ổn định
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
                       file_name="hk_busiest_stops.csv", mime="text/csv")

    st.divider()