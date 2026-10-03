import os
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go
from google.cloud import bigquery
from dotenv import load_dotenv
load_dotenv()

PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

st.set_page_config(
    page_title="Adelaide Metro - Network Analytics",
    page_icon="🚌",
    layout="wide",
    )

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
def load_route_lengths(project_id):
    return get_bq_client().query(f"""
    SELECT 
            route_id, route_short_name, route_long_name, route_type,
            avg_length_km, min_length_km, max_length_km, shape_count
        FROM `{project_id}.marts.mart_dashboard_route_lengths`
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
            data_as_of
        FROM `{project_id}.marts.mart_dashboard_delay_propagation`
        ORDER BY route_short_name, stop_sequence
    """
    ).to_dataframe()

ROUTE_TYPE_LABEL = {0: "Tram", 2: "Rail", 3: "Bus", 4: "Ferry",  701: "Regional Bus", 712: "Express Bus"}

def route_type_color(rt):
    return {
        0: [0, 200, 100, 220],
        2: [180, 0, 255, 220],
        3: [255, 50, 50, 220],
        4: [0, 120, 255, 220],
        701: [200, 30, 30, 220],
        712: [255, 120, 0, 220],
    }.get(rt, [200, 200, 200, 180])

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
        SELECT s.stop_id, s.stop_name, s.stop_lat, s.stop_lon, s.total_departures,
               COALESCE(s.route_type, -1) AS route_type,
               COALESCE(d.lga_name, 'Other') AS lga_name
        FROM `{PROJECT_ID}.marts.mart_dashboard_stop_map` AS s
        LEFT JOIN `{PROJECT_ID}.core.dim_stops` AS d ON s.stop_id = d.stop_id
        WHERE s.stop_lat IS NOT NULL AND s.stop_lon IS NOT NULL
        """)
        stops_df["Transport Type"] = stops_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        st.session_state.stops_df = stops_df

st.info(
    f"**Network Snapshot:** Adelaide public transport has **{total_stops:,} stops** across **{total_routes} routes**. "
    f"Route **{busiest_route}** has the most scheduled trips (**{busiest_route_trips:,}**). "
    f"The peak hour for scheduled trip starts is **{peak_hour:02d}:00**. "
    f"**{top_stop}** has the most scheduled stop visits. Counts cover the loaded timetable."
)

# ── KPI row ────────────────────────────────────────────────────────────────────

col1, col2, col3, col4 = st.columns(4)
col1.metric("GTFS Stops", f"{total_stops:,}")
col2.metric("GTFS Routes", f"{total_routes:,}")
col3.metric("Scheduled Stop Visits", f"{total_departures:,}")
col4.metric("Peak Hour", f"{peak_hour:02d}:00")

st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_network, tab_lengths, tab_cbd, tab_delay = st.tabs(["Network Analytics", "Route Lengths", "Scheduled CBD Speed", "Realtime Arrival Delay"])

with tab_network:
    with st.spinner("Loading network data..."):
        load_network_data()
    stops_df = st.session_state.stops_df
    st.subheader("Explore Stops")
    selected_lga = st.selectbox(
        "Local Government Area",
        ["All areas"] + sorted(stops_df["lga_name"].unique()),
        key="lga_region",
    )

    # ── Transport type selector ────────────────────────────────────────────────
    TYPE_OPTIONS = {
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
    f_stops = stops_df[stops_df["route_type"] == rt_filter]
    if selected_lga != "All areas":
        f_stops = f_stops[f_stops["lga_name"] == selected_lga]
    stop_color = route_type_color(rt_filter)

    # ── Stop map ───────────────────────────────────────────────────────────────
    st.subheader("Stop Locations")
    st.caption(f"{selected_lga} · {len(f_stops):,} stops · {selected_label}")
    try:
        view = pdk.ViewState(latitude=-34.9285, longitude=138.6007, zoom=11)
        if selected_lga != "All areas" and not f_stops.empty:
            view = pdk.data_utils.compute_view(f_stops[["stop_lon", "stop_lat"]].values.tolist())
            view.zoom = min(view.zoom - 0.5, 14)
        if f_stops.empty:
            st.info("No stops match this area and transport type.")

        st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=f_stops,
                        get_position=["stop_lon", "stop_lat"],
                        get_radius=120,
                        radius_min_pixels=3,
                        radius_max_pixels=10,
                        get_fill_color=stop_color,
                        pickable=True,
                        auto_highlight=True,
                    )
                ],
                initial_view_state=view,
                tooltip={
                    "text": "{stop_name}\nScheduled stop visits: {total_departures}\nLocal Government Area: {lga_name}\nType: {Transport Type}"
                },
                map_style="https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
            )
        )
    except Exception:
        st.info("Map unavailable — refresh the page to reload.")

    st.divider()

    # ── Busiest stops ──────────────────────────────────────────────────────────
    st.subheader("Top 10 Stops by Scheduled Visits")
    st.caption(f"{selected_lga}. Visits match the selected transport type and cover the loaded timetable, not a single day or passenger counts.")
    top_stops = (
        f_stops[["stop_name", "total_departures", "Transport Type"]]
        .sort_values(["total_departures", "stop_name"], ascending=[False, True]).head(10).reset_index(drop=True)
    )
    top_stops.index += 1
    top_stops.columns = ["Stop Name", "Scheduled Stop Visits", "Transport Type"]
    st.dataframe(top_stops, width='stretch')
    st.download_button("⬇ Download CSV", data=top_stops.to_csv(index=False),
                       file_name="adelaide_busiest_stops.csv", mime="text/csv")

    st.divider()

    st.subheader("Service by Local Government Area")
    st.caption("Top 15 areas across all transport types. Counts cover the loaded timetable, not daily services or passenger demand. A route can serve multiple local government areas.")
    try:
        lga_df = load_data(f"""
            SELECT lga_name, stop_count, route_count, scheduled_stop_visits
            FROM `{PROJECT_ID}.marts.mart_dashboard_lga_service`
            ORDER BY scheduled_stop_visits DESC, lga_name
        """)
    except Exception:
        st.warning("Service data by local government area is currently unavailable.")
        lga_df = pd.DataFrame()

    if lga_df.empty:
        st.info("No service data by local government area available.")
    else:
        metric_labels = {
            "Scheduled Stop Visits": "scheduled_stop_visits",
            "Stops": "stop_count",
            "Routes": "route_count",
        }
        metric_label = st.selectbox("Compare", list(metric_labels), key="lga_metric")
        metric_column = metric_labels[metric_label]
        ranked_lgas = lga_df.sort_values(
            [metric_column, "lga_name"], ascending=[False, True]
        )
        chart = px.bar(
            ranked_lgas.head(15),
            x=metric_column,
            y="lga_name",
            orientation="h",
            labels={metric_column: metric_label, "lga_name": "Local Government Area"},
            color_discrete_sequence=["#00843D"],
        )
        chart.update_layout(yaxis={"autorange": "reversed"}, height=450)
        st.plotly_chart(chart, use_container_width=True)

    st.divider()

with tab_lengths:
    st.subheader("Route Lengths")
    st.caption("Distances from GTFS route shapes. Average length gives equal weight to each shape; the range includes different directions and route variants, not a selected journey.")
    try:
        lengths_df = load_route_lengths(PROJECT_ID)
    except Exception:
        st.warning("Route lengths are currently unavailable.")
        lengths_df = pd.DataFrame()

    if lengths_df.empty:
        st.info("No route lengths available.")
    else:
        lengths_df = lengths_df.copy()
        lengths_df["transport"] = lengths_df["route_type"].map(ROUTE_TYPE_LABEL).fillna("Unknown")
        type_col, search_col = st.columns([1, 2])
        with type_col:
            selected_type = st.selectbox("Transport Type", ["All"] + sorted(lengths_df["transport"].unique()), key="length_transport")
        with search_col:
            route_search = st.text_input("Route or Destination", key="length_search").strip()
        filtered_lengths = lengths_df
        if selected_type != "All":
            filtered_lengths = filtered_lengths[filtered_lengths["transport"] == selected_type]
        if route_search:
            matches = (
                filtered_lengths["route_short_name"].fillna("").str.contains(route_search, case=False, regex=False)
                | filtered_lengths["route_long_name"].fillna("").str.contains(route_search, case=False, regex=False)
            )
            filtered_lengths = filtered_lengths[matches]

        if filtered_lengths.empty:
            st.info("No routes match these filters.")
        else:
            longest = filtered_lengths.nlargest(15, "avg_length_km").copy()
            longest["route_label"] = longest["route_short_name"] + " / " + longest["transport"]
            st.subheader("Longest Routes in Selection")
            longest = longest.sort_values("avg_length_km")
            fig_lengths = px.bar(
                longest, x="avg_length_km", y="route_id",
                orientation="h", hover_data=["route_short_name", "route_long_name", "min_length_km", "max_length_km"],
                labels={"avg_length_km": "Average Length (km)", "route_id": "Route", "route_short_name": "Route Number",
                        "route_long_name": "Route Description", "min_length_km": "Shortest Shape (km)",
                        "max_length_km": "Longest Shape (km)"},
                color_discrete_sequence=["#00843D"],
            )
            fig_lengths.update_layout(height=max(300, 28 * len(longest)))
            fig_lengths.update_yaxes(tickmode="array", tickvals=longest["route_id"], ticktext=longest["route_label"], type="category")
            st.plotly_chart(fig_lengths, width='stretch')
            st.subheader(f"Routes ({len(filtered_lengths):,})")
            st.dataframe(
                filtered_lengths.sort_values("avg_length_km", ascending=False)[[
                    "route_short_name", "route_long_name", "transport", "avg_length_km",
                    "min_length_km", "max_length_km", "shape_count",
                ]],
                column_config={
                    "route_short_name": "Route", "route_long_name": "Route Description", "transport": "Transport",
                    "avg_length_km": st.column_config.NumberColumn("Average Length (km)", format="%.2f"),
                    "min_length_km": st.column_config.NumberColumn("Shortest Shape (km)", format="%.2f"),
                    "max_length_km": st.column_config.NumberColumn("Longest Shape (km)", format="%.2f"),
                    "shape_count": st.column_config.NumberColumn("Mapped Paths", help="Distinct GTFS shapes used to calculate the lengths.", format="%d"),
                }, hide_index=True, width='stretch',
            )
    st.divider()

with tab_cbd:
    st.subheader("Scheduled CBD Speed")
    st.caption("Total segment distance / total scheduled travel time from the loaded timetable, not observed traffic speed. Corridors are assigned from stop names, not street geometry.")

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
            col1, col2 = st.columns(2)
            col1.metric("Corridors Displayed", filtered_cbd_df['corridor_name'].nunique())
            slowest_row = filtered_cbd_df.loc[filtered_cbd_df['corridor_avg_speed_kmh'].idxmin()]
            col2.metric("Lowest Scheduled Speed", f"{slowest_row['corridor_avg_speed_kmh']:.2f} km/h",
                        help=f"{slowest_row['corridor_name']} / {slowest_row['time_bucket']}")

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
                st.subheader("Scheduled Speed by Time Window")
                
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
                        
                        hover_row.append(
                            f"<b>Corridor:</b> {index}<br>" +
                            f"<b>Time Window:</b> {col}<br>" +
                            f"<b>Scheduled Speed:</b> {val:.1f} km/h<br>" +
                            f"<b>Scheduled Trips:</b> {trips:,}"
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
                st.subheader("Scheduled Trips by Corridor")
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
                
            st.caption("Scheduled speed = total segment distance / total scheduled travel time. Trip counts are distinct within each corridor/time window; they are not additive across corridors or windows.")
    st.divider()

with tab_delay:
    st.subheader("Realtime Arrival Delay")
    st.caption("Latest available arrival update per trip/stop, compared with the timetable and pooled by route name and stop sequence. Route variants may differ; updates may be predictions, not observed arrivals.")
    st_autorefresh(interval=300000, key="delay_tab_autorefresh")
    
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
        df = pd.DataFrame()

    if df.empty:
        st.info("No realtime arrival delays available.")
        if st.button("🔄 Refresh Data"):
            load_delay_data.clear()
            st.rerun()
        st.stop()

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
            load_delay_data.clear()
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
    largest_change_row = route_df.loc[route_df["delay_added_mins"].idxmax()]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Route", f"Route {selected_route}")
    col2.metric("Maximum Trips at a Stop", f"{total_trips:,} trips")
    col3.metric(
        "Largest Reported Delay Change",
        f"{largest_change_row['stop_name']}",
        f"{largest_change_row['delay_added_mins']:+.2f} mins",
        delta_color="inverse",
    )
    col4.metric(
        "Highest Mean Arrival Delay",
        f"{max_delay_row['stop_name']}",
        f"{max_delay_row['avg_delay_mins']} mins",
        delta_color="inverse",
    )

    st.divider()

    # ------------------------------------------------------------------------------
    # CHARTS SECTION
    # ------------------------------------------------------------------------------

    # Chart 1: Combo Chart - Delay Added (Bar) vs Total Avg Delay (Line)
    st.subheader("Reported Delay by Stop")
    st.caption("Bars average the change from each trip's previous available stop update, which may skip stops. Lines show mean delay against the timetable; sample sizes can differ by stop.")

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
            name="Change from Previous Available Stop",
            marker_color=[
                "#EF5350" if x > 0 else "#66BB6A" for x in route_df["delay_added_mins"]
            ],
            hovertemplate="Stop: %{x}<br>Reported Change: %{y:.2f} mins<extra></extra>",
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
            hovertemplate="Stop: %{x}<br>Mean Arrival Delay: %{y:.2f} mins<extra></extra>",
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


    # ------------------------------------------------------------------------------
    # DATA TABLE DETAIL
    # ------------------------------------------------------------------------------
    with st.expander("📄 View Detailed Analytics Table", expanded=False):
        tab_top, tab_all = st.tabs(
            ["Largest Positive Changes", "Full Route Table"]
        )

        with tab_top:
            top_changes = (
                route_df[route_df["delay_added_mins"] > 0]
                .sort_values(by="delay_added_mins", ascending=False)
                .head(10)
            )

            st.dataframe(
                top_changes[
                    [
                        "stop_sequence",
                        "stop_name",
                        "delay_added_mins",
                        "avg_delay_mins",
                    ]
                ],
                column_config={
                    "stop_sequence": st.column_config.NumberColumn("Seq"),
                    "stop_name": "Stop Name",
                    "delay_added_mins": st.column_config.ProgressColumn(
                        "Reported Change (mins)",
                        format="%.2f",
                        min_value=0,
                        max_value=float(
                            max(1.0, route_df["delay_added_mins"].max())
                        ),
                    ),
                    "avg_delay_mins": st.column_config.NumberColumn(
                        "Avg Delay (mins)", format="%.2f"
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
                        "Reported Change (mins)", format="%.2f"
                    ),
                },
                hide_index=True,
                width='stretch',
            )
