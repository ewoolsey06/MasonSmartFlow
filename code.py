from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import folium
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_folium import st_folium

# Define Eastern Time Zone (handles both EST and EDT automatically)
EASTERN_TZ = ZoneInfo("America/New_York")

st.title("Living Lab Smart Flow: Fairfax Campus Rainfall and Water Depth Data")

TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

if "data_window" not in st.session_state:
    end = datetime.now(EASTERN_TZ)
    start = end - timedelta(days=8)
    st.session_state["data_window"] = {
        "start": start,
        "end": end
    }

start = st.session_state["data_window"]["start"]
end = st.session_state["data_window"]["end"]


@st.cache_data(ttl=3600)
def fetch_devices():
    response = requests.get(
        "https://api.licor.cloud/v2/devices",
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError("Could not retrieve devices.")

    return response.json().get("devices", [])


@st.cache_data(ttl=3600)
def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt
    }

    response = requests.get(
        "https://api.licor.cloud/v1/data",
        headers=headers,
        params=params,
        timeout=30
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Device {serial} data request failed: {response.status_code}"
        )

    return response.json().get("data", [])


def daterange_chunks(start_dt: datetime, end_dt: datetime, chunk_days: int = 1):
    chunks = []
    current = start_dt
    while current < end_dt:
        chunk_end = min(current + timedelta(days=chunk_days), end_dt)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


def keep_half_hour_marks(df_chunk: pd.DataFrame) -> pd.DataFrame:
    """
    Keep one reading every 30 minutes, per sensor, anchored to actual clock
    time (:00 and :30) in Eastern Time.
    """
    if df_chunk.empty:
        return df_chunk

    df_chunk = df_chunk.copy()
    
  
    df_chunk["timestamp"] = (
        pd.to_datetime(df_chunk["timestamp"], utc=True)
        .dt.tz_convert(EASTERN_TZ)
    )

    picked_frames = []
    for sensor, group in df_chunk.groupby("sensor_sn"):
        resampled = (
            group.sort_values("timestamp")
            .set_index("timestamp")
            .resample("30min")
            .first()
            .dropna(how="all")
        )
        resampled["sensor_sn"] = sensor
        picked_frames.append(resampled.reset_index())

    if not picked_frames:
        return df_chunk.iloc[0:0]

    return pd.concat(picked_frames, ignore_index=True)


@st.cache_data(ttl=3600)
def load_all_device_data(start_dt: datetime, end_dt: datetime):
    devices = fetch_devices()
    all_devices_data = []

    chunks = daterange_chunks(start_dt, end_dt, chunk_days=1)

    for d in devices:
        serial = d["deviceSerialNumber"]

        for chunk_start, chunk_end in chunks:
            chunk_start_str = chunk_start.strftime("%Y-%m-%d %H:%M:%S")
            chunk_end_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")

            try:
                data = fetch_device_data(serial, chunk_start_str, chunk_end_str)
            except RuntimeError as exc:
                st.warning(str(exc))
                continue

            if not data:
                continue

            df_chunk = pd.DataFrame(data)
            df_chunk = keep_half_hour_marks(df_chunk)

            if df_chunk.empty:
                continue

            all_devices_data.append(df_chunk)

    if not all_devices_data:
        return pd.DataFrame()

    df = pd.concat(all_devices_data, ignore_index=True)

    return df


try:
    df = load_all_device_data(start, end)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()


if df.empty:
    st.text("No data returned from any devices.")
    st.stop()


# Water depth sensors: name -> sensor_sn
SENSOR_CONFIG = {
    "Green Bridge": "22406680-1",
    "Mason Pond": "22406678-1",
    "The Hub": "22508090-1",
    "RAC Sensor": "22308166-1",
    "Lot C #1": "22308168-1",
    "Lot C #2": "22406679-1",
    "Aquatic Center": "22406677-1",
}

RANGE_OPTIONS = {
    "1 Week": timedelta(days=7),
    "3 Days": timedelta(days=3),
    "24 Hours": timedelta(hours=24),
}
DEFAULT_RANGE = "3 Days"


def compute_y_range(values: pd.Series, pad_frac: float = 0.05):
    """Y-axis range from the min/max of the whole dataset, with a little padding."""
    if values.empty:
        return [-0.01, 0.8]

    lo = float(values.min())
    hi = float(values.max())

    if lo == hi:
        lo -= 0.05
        hi += 0.05

    pad = (hi - lo) * pad_frac
    return [lo - pad, hi + pad]


def filter_by_range(sensor_df: pd.DataFrame, range_label: str) -> pd.DataFrame:
    """Slice a sensor's full-range data down to the selected window, anchored
    to that sensor's own most recent reading."""
    if sensor_df.empty:
        return sensor_df

    latest = sensor_df.index.max()
    cutoff = latest - RANGE_OPTIONS.get(range_label, RANGE_OPTIONS[DEFAULT_RANGE])
    return sensor_df[sensor_df.index >= cutoff]


def build_sensor_figure(sensor_df: pd.DataFrame, name: str, y_range, range_label: str) -> go.Figure:
    filtered = filter_by_range(sensor_df, range_label)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=filtered.index,
        y=filtered["value"] if "value" in filtered else [],
        mode='lines',
        name=name,
        line=dict(color='#005138', width=0.75)
    ))
    fig.update_layout(
        title=f"{name} Data ({range_label}) - Eastern Time",
        xaxis_title=f"Time ({range_label} EST/EDT)",
        yaxis_title="Water Depth (ft)",
        hovermode='x unified',
        width=1000,
        height=400,
        template='plotly_white',
        yaxis=dict(range=y_range)
    )
    return fig


sensor_data = {}
sensor_y_range = {}

for sensor_name, sensor_sn in SENSOR_CONFIG.items():
    sdf = df[df["sensor_sn"] == sensor_sn].copy()

    if sdf.empty:
        st.error(f"{sensor_name} sensor {sensor_sn} not found.")
        sensor_data[sensor_name] = pd.DataFrame(columns=["value"])
        sensor_y_range[sensor_name] = [-0.01, 0.8]
        continue

    sdf["timestamp"] = pd.to_datetime(sdf["timestamp"])
    sdf = sdf.sort_values("timestamp").set_index("timestamp")

    sensor_data[sensor_name] = sdf
    sensor_y_range[sensor_name] = compute_y_range(sdf["value"])

# Map
locations_df = pd.DataFrame({
    'name': ['Green Bridge', 'Mason Pond', 'The Hub', 'RAC Sensor', 'Lot C #1', 'Lot C #2', 'Aquatic Center'],
    'lat': [38.827153, 38.829022, 38.83019, 38.830625, 38.825383, 38.825994, 38.826328],
    'lon': [-77.30703, -77.310372, -77.30398, -77.310689, -77.303769, -77.304797, -77.303419]
})


# Rain sensor
rain_total = df[
    df["sensor_sn"] == "22334782-1"
].copy()

if rain_total.empty:
    st.error("Rain sensor 22334782-1 not found.")

rain_total = rain_total.sort_values("timestamp")
rain_total["timestamp"] = pd.to_datetime(rain_total["timestamp"])
rain_total = rain_total.set_index("timestamp")


# Plot
rt_fig = go.Figure()

rt_fig.add_trace(go.Bar(
    x=rain_total.index,
    y=rain_total["value"],
    name='Rainfall',
    marker=dict(
        color='#005138',
        line=dict(color='#005138', width=1),
        opacity=1
    ),
    opacity=1
))

rt_fig.update_layout(
    title="Rainfall Totals (Eastern Time)",
    xaxis_title="Day (last week EST/EDT)",
    yaxis_title="Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white',
    paper_bgcolor='white',
    plot_bgcolor='white'
)


# Accumulated Rain sensor
rain_acc = df[
    df["sensor_sn"] == "22334782-2"
].copy()

if rain_acc.empty:
    st.error("Accumulated Rain sensor 22334782-2 not found.")
    st.stop()

rain_acc = rain_acc.sort_values("timestamp")
rain_acc["timestamp"] = pd.to_datetime(rain_acc["timestamp"])
rain_acc = rain_acc.set_index("timestamp")


# Plot
ra_fig = go.Figure()

ra_fig.add_trace(go.Bar(
    x=rain_acc.index,
    y=rain_acc["value"],
    name='Rainfall',
    marker=dict(
        color='#005138',
        line=dict(color='#005138', width=1),
        opacity=1
    ),
    opacity=1
))

ra_fig.update_layout(
    title="Accumulated Rainfall Totals (Eastern Time)",
    xaxis_title="Day (last week EST/EDT)",
    yaxis_title="Accumulated Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white',
    paper_bgcolor='white',
    plot_bgcolor='white'
)

st.markdown(
    """
    <style>
    :root {
        --st-primary-color: #005138 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


st.subheader("Rainfall / Device Analytics")
rain_tab, acc_tab = st.tabs(["Total Rain", "Accumulated Rain"])

with rain_tab:
    st.plotly_chart(rt_fig, width='stretch')

with acc_tab:
    st.plotly_chart(ra_fig, width='stretch')

st.subheader("Fairfax Campus Sensor Location Map")
st.write("Click on any marker on the map or use the buttons to view the sensor's name and to display its specific water depth data")

center_lat = locations_df["lat"].mean()
center_lon = locations_df["lon"].mean()
bounds = [[row["lat"], row["lon"]] for _, row in locations_df.iterrows()]

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=16,
    tiles="OpenStreetMap"
)

for _, row in locations_df.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lon']],
        radius=8,
        popup=row['name'],
        tooltip=f"Click to view {row['name']}",
        color="#01090F",
        fill=True,
        fill_color="#318ece",
        fill_opacity=0.7
    ).add_to(m)


# Render buttons next to the map using columns
if "selected_location" not in st.session_state:
    st.session_state["selected_location"] = None
if "button_clicked" not in st.session_state:
    st.session_state["button_clicked"] = False
if "graph_range" not in st.session_state:
    st.session_state["graph_range"] = DEFAULT_RANGE


def set_selected(location: str):
    st.session_state["selected_location"] = location
    st.session_state["graph_range"] = DEFAULT_RANGE  # reset to 3 Days whenever a new sensor is picked
    st.session_state["button_clicked"] = True


def set_graph_range(range_label: str):
    st.session_state["graph_range"] = range_label
    st.session_state["button_clicked"] = True  # don't let the map click re-processing override this


left_col, right_col = st.columns([1, 3])

with left_col:
    left_col.markdown(
        "<p style='margin: 0 0 4px 0; font-size: 1.1rem; font-weight: 600;'>Select Sensor</p>",
        unsafe_allow_html=True
    )
    left_col.button("Green Bridge", key="inline_green", on_click=set_selected, args=("Green Bridge",))
    left_col.button("Mason Pond", key="inline_mason", on_click=set_selected, args=("Mason Pond",))
    left_col.button("The Hub", key="inline_hub", on_click=set_selected, args=("The Hub",))
    left_col.button("RAC Sensor", key="inline_rac", on_click=set_selected, args=("RAC Sensor",))
    left_col.button("Lot C #1", key="inline_lot_c1", on_click=set_selected, args=("Lot C #1",))
    left_col.button("Lot C #2", key="inline_lot_c2", on_click=set_selected, args=("Lot C #2",))
    left_col.button("Aquatic Center", key="inline_aquatic_center", on_click=set_selected, args=("Aquatic Center",))

# Keep the selected label inside the same left column
selection_placeholder = left_col.empty()

with right_col:
    map_data = st_folium(m, width="100%", height=450, key="map")


if st.session_state["button_clicked"]:
    st.session_state["button_clicked"] = False
else:
    if map_data and map_data.get("last_object_clicked"):
        loc = map_data["last_object_clicked"]

        matches = locations_df[
            (locations_df["lat"].sub(loc.get("lat", 0)).abs() < 0.0005) &
            (locations_df["lon"].sub(loc.get("lng", 0)).abs() < 0.0005)
        ]

        if not matches.empty:
            clicked_name = matches.iloc[0]["name"]
            if clicked_name != st.session_state.get("selected_location"):
                st.session_state["graph_range"] = DEFAULT_RANGE
            st.session_state["selected_location"] = clicked_name


if st.session_state.get("selected_location"):
    selection_placeholder.write(f"**Selected:** {st.session_state['selected_location']}")


selected_location = st.session_state.get("selected_location")

if selected_location is not None:
    st.subheader(f"{selected_location} Water Depth")

    # Custom CSS to shrink buttons and tighten vertical margins
    st.markdown(
        """
        <style>
        /* Target buttons to shrink height, font, and padding */
        div[data-testid="column"] button {
            min-height: 28px !important;
            height: 28px !important;
            padding: 0px 8px !important;
            font-size: 0.8rem !important;
            line-height: 1 !important;
            margin-top: -10px !important;
            margin-bottom: -10px !important;
        }
        
        /* Adjust alignment for the caption label */
        div[data-testid="column"] div[data-testid="stCaptionContainer"] {
            margin-top: -6px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    range_col1, range_col2, range_col3, range_col4 = st.columns([1, 1, 1, 3])
    with range_col1:
        st.button("1 Week", key="range_1w", on_click=set_graph_range, args=("1 Week",))
    with range_col2:
        st.button("3 Days", key="range_3d", on_click=set_graph_range, args=("3 Days",))
    with range_col3:
        st.button("24 Hours", key="range_24h", on_click=set_graph_range, args=("24 Hours",))
    with range_col4:
        st.caption(f"Showing: {st.session_state['graph_range']}")

    sensor_fig = build_sensor_figure(
        sensor_data[selected_location],
        selected_location,
        sensor_y_range[selected_location],
        st.session_state["graph_range"]
    )

    st.plotly_chart(sensor_fig, width='stretch')

    # --- CSV Download Section ---
    st.markdown("<p style='margin-top: 10px; font-weight: 600;'>Download Data</p>", unsafe_allow_html=True)
    
    # Get current sensor DataFrame
    curr_df = sensor_data[selected_location]
    
    # Pre-filter datasets for all 3 time ranges
    df_1w = filter_by_range(curr_df, "1 Week").reset_index()
    df_3d = filter_by_range(curr_df, "3 Days").reset_index()
    df_24h = filter_by_range(curr_df, "24 Hours").reset_index()

    # Format timestamp column for clean CSV output
    for d in (df_1w, df_3d, df_24h):
        if not d.empty and "timestamp" in d.columns:
            d["timestamp"] = d["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    # Clean file name string (e.g., "Green Bridge" -> "green_bridge")
    safe_name = selected_location.lower().replace(" ", "_").replace("#", "")

    dl_col1, dl_col2, dl_col3, _ = st.columns([1, 1, 1, 3])

    with dl_col1:
        st.download_button(
            label="Download 1 Week CSV",
            data=df_1w.to_csv(index=False).encode('utf-8'),
            file_name=f"{safe_name}_1week_data.csv",
            mime="text/csv",
            key="dl_1w"
        )

    with dl_col2:
        st.download_button(
            label="Download 3 Days CSV",
            data=df_3d.to_csv(index=False).encode('utf-8'),
            file_name=f"{safe_name}_3days_data.csv",
            mime="text/csv",
            key="dl_3d"
        )

    with dl_col3:
        st.download_button(
            label="Download 24 Hours CSV",
            data=df_24h.to_csv(index=False).encode('utf-8'),
            file_name=f"{safe_name}_24hours_data.csv",
            mime="text/csv",
            key="dl_24h"
        )
