import os
import streamlit as st
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
load_dotenv()

_BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; hk-transit-pulse/1.0)"}

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
def load_cbd_corridor_data(project_id):
    return get_bq_client().query(f"""
    SELECT 
        corridor_name,
        time_bucket,
        unique_trips,
        corridor_avg_speed_kmh
    FROM `{project_id}.marts.mart_cbd_corridor_speed`
    ORDER BY corridor_name, time_bucket
    """).to_dataframe()

@st.cache_data(ttl=300)
def load_delay_data(project_id):
    # Khởi tạo BigQuery Client
    return get_bq_client().query(f"""
        SELECT 
            route_short_name,
            stop_sequence,
            stop_name,
            total_trips_analyzed,
            avg_delay_mins,
            delay_added_mins,
            propagation_factor
        FROM `{project_id}.marts.mart_rt_delay_propagation`
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
tab_network, tab_cbd, tab_delay = st.tabs(["Network Analytics", "CBD Corridor Speed", "Delay Propagation Monitoring"])

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
                    latitude=lat_center,
                    longitude=lon_center,
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
                       file_name="adelaide_busiest_stops.csv", mime="text/csv")

    st.divider()


with tab_cbd:
    st.subheader("Adelaide CBD Transit Speed & Volume Analysis")
    st.caption("Analyze vehicle speeds and traffic volumes across major Adelaide CBD corridors by time buckets.")

    # Load data
    try:
        cbd_df = load_cbd_corridor_data(PROJECT_ID)
    except Exception as e:
        st.warning(f"Could not load CBD corridor speed data. Make sure the Bruin asset `mart_cbd_corridor_speed` has been executed. Error: {e}")
        cbd_df = pd.DataFrame()

    if cbd_df.empty:
        st.info("No data available in `marts.mart_cbd_corridor_speed` yet.")
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
                st.button("Reset Filter", on_click=reset_cbd_filters, use_container_width=True)

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
                st.plotly_chart(fig_heatmap, use_container_width=True)

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
                st.plotly_chart(fig_bar, use_container_width=True)
                
            with st.expander("📚 Methodology & Business Definitions"):
                st.markdown("""
                * **Scheduled Speed:** Calculated by dividing actual GTFS `shapes.txt` distance by the time difference between arrival and departure times in `stop_times.txt`.
                * **Unique Trips:** Represents distinct bus runs passing through the corridor segment, deduplicating intermediate stops.
                * **Off-Peak Baseline:** Reflects the baseline infrastructure speed limit without commuter traffic interference.
                """)

with tab_delay:
    st.title("🚌 Adelaide Metro: Corridor Delay & Propagation Analytics")
    st.markdown(
        "Phân tích sự phát sinh và lan truyền độ trễ realtime dọc theo các hành lang tuyến xe bus."
    )
    try:
        df = load_delay_data(PROJECT_ID)
    except Exception as e:
        st.warning(f"Không thể kết nối BigQuery ({e}). Đang hiển thị dữ liệu mẫu.")

    # ------------------------------------------------------------------------------
    # 3. SIDEBAR FILTERS
    # ------------------------------------------------------------------------------
    routes = sorted(df["route_short_name"].unique())
    # Tạo một vùng Filter nhỏ gọn ngay trong Tab
    with st.container():
        f_col1, f_col2 = st.columns([1, 3])
        with f_col1:
            selected_route = st.selectbox("🔍 Chọn tuyến xe (Route):", routes)

    # Lọc dữ liệu theo tuyến được chọn
    route_df = df[df["route_short_name"] == selected_route].sort_values(
        "stop_sequence"
    )

    st.divider()

    # ------------------------------------------------------------------------------
    # 4. KPI METRICS
    # ------------------------------------------------------------------------------
    total_trips = route_df["total_trips_analyzed"].max()
    max_delay_row = route_df.loc[route_df["avg_delay_mins"].idxmax()]
    worst_bottleneck_row = route_df.loc[route_df["delay_added_mins"].idxmax()]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Tuyến đang xem", f"Route {selected_route}")
    col2.metric("Số chuyến phân tích", f"{total_trips:,} chuyến")
    col3.metric(
        "Nút thắt kẹt nặng nhất",
        f"{worst_bottleneck_row['stop_name']}",
        f"+{worst_bottleneck_row['delay_added_mins']} phút",
        delta_color="inverse",
    )
    col4.metric(
        "Trạm trễ tích lũy cao nhất",
        f"{max_delay_row['stop_name']}",
        f"{max_delay_row['avg_delay_mins']} phút",
        delta_color="inverse",
    )

    st.divider()

    # ------------------------------------------------------------------------------
    # 5. CHARTS SECTION
    # ------------------------------------------------------------------------------

    # Chart 1: Combo Chart - Delay Added (Bar) vs Total Avg Delay (Line)
    st.subheader("1. Sự phát sinh & Tích lũy độ trễ qua từng trạm (Delay Progression)")

    # Tạo nhãn hiển thị dạng "Seq 16 - Stop Name"
    route_df["stop_label"] = (
        route_df["stop_sequence"].astype(str) + ". " + route_df["stop_name"]
    )

    fig_combo = go.Figure()

    # Thanh Bar: Delay phát sinh thêm tại trạm
    fig_combo.add_trace(
        go.Bar(
            x=route_df["stop_label"],
            y=route_df["delay_added_mins"],
            name="Độ trễ phát sinh thêm (Delay Added)",
            marker_color=[
                "#EF5350" if x > 0 else "#66BB6A" for x in route_df["delay_added_mins"]
            ],
            hovertemplate="Trạm: %{x}<br>Phát sinh thêm: %{y:.2f} phút<extra></extra>",
        )
    )

    # Đường Line: Tổng độ trễ tích lũy trung bình
    fig_combo.add_trace(
        go.Scatter(
            x=route_df["stop_label"],
            y=route_df["avg_delay_mins"],
            name="Tổng độ trễ tích lũy (Avg Delay)",
            mode="lines+markers",
            line=dict(color="#29B6F6", width=3),
            marker=dict(size=8),
            hovertemplate="Trạm: %{x}<br>Tổng độ trễ tích lũy: %{y:.2f} phút<extra></extra>",
        )
    )

    fig_combo.update_layout(
        xaxis_title="Thứ tự bến dừng (Stop Sequence)",
        yaxis_title="Thời gian (Phút)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
    )

    st.plotly_chart(fig_combo, use_container_width=True)


    # Chart 2: Propagation Factor Line Chart
    st.subheader("2. Hệ số lan truyền trễ dây chuyền (Delay Propagation Factor)")
    st.caption(
        "Chỉ số > 1.0 phản ánh độ trễ từ bến xuất phát đang bị nhân rộng (khổ hơn) khi qua các trạm sau."
    )

    fig_prop = px.line(
        route_df,
        x="stop_label",
        y="propagation_factor",
        markers=True,
        labels={
            "stop_label": "Thứ tự bến dừng",
            "propagation_factor": "Propagation Factor",
        },
    )

    # Thêm đường tham chiếu Baseline = 1.0
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
        hovertemplate="Trạm: %{x}<br>Propagation Factor: %{y:.2f}<extra></extra>",
    )
    fig_prop.update_layout(height=350)

    st.plotly_chart(fig_prop, use_container_width=True)

    # ------------------------------------------------------------------------------
    # 6. DATA TABLE DETAIL
    # ------------------------------------------------------------------------------
    with st.expander("📄 Xem chi tiết bảng dữ liệu (Data Table)"):
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
            use_container_width=True,
            hide_index=True,
        )
