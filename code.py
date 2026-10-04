import os
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

# SECURE CONFIGURATION: Pulls the token safely from Streamlit Secrets
if "LICOR_TOKEN" in st.secrets:
    TOKEN = st.secrets["LICOR_TOKEN"]
else:
    # Fallback to hardcoded value if secret is not configured yet
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


# GLOBAL APP CACHE: Shared across all users worldwide. Refreshes once per hour.
@st.cache_data(ttl=3600, show_spinner="Downloading latest sensor records from LI-COR Cloud...")
def fetch_devices():
    response = requests.get(
        "https://licor.cloud",
        headers=headers,
        timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError("Could not retrieve devices.")
    return response.json().get("devices", [])


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt
    }
    response = requests.get(
        "https://licor.cloud",
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


# GLOBAL DATA CACHE: Caches the final processed dataframe for all viewers
@st.cache_data(ttl=3600, show_spinner="Processing and resampling timeline matrices...")
def load_all_device_data(start_dt: datetime, end_dt: datetime):
    try:
        devices = fetch_devices()
    except Exception as e:
        # Fallback handle if the API blips temporarily
        return pd.DataFrame()

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
    return pd.concat(all_devices_data, ignore_index=True)


# Execute tracking data parsing
df = load_all_device_data(start, end)

if df.empty:
    st.error("The dashboard is currently unable to read live API streams. Retrying link handshake...")
    if st.button("🔄 Force App Reconnect"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

# --- Your exact visual, map, and plotting code resumes safely below this line ---
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
rain_total = df[df["sensor_sn"] == "22334782-1"].copy()
if not rain_total.empty:
    rain_total = rain_total.sort_values("timestamp")
    rain_total["timestamp"] = pd.to_datetime(rain_total["timestamp"])
    rain_total = rain_total.set_index("timestamp")

rt_fig = go.Figure()
if not rain_total.empty:
    rt_fig.add_trace(go.Bar(
        x=rain_total.index,
        y=rain_total["value"],
        name='Rainfall',
        marker=dict(color='#005138', line=dict(color='#005138', width=1))
    ))
rt_fig.update_layout(
    title="Rainfall Totals (Eastern Time)",
    xaxis_title="Day (last week EST/EDT)",
    yaxis_title="Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white'
)

# Accumulated Rain sensor
rain_acc = df[df["sensor_sn"] == "22334782-2"].copy()
if not rain_acc.empty:
    rain_acc = rain_acc.sort_values("timestamp")
    rain_acc["timestamp"] = pd.to_datetime(rain_acc["timestamp"])
    rain_acc = rain_acc.set_index("timestamp")

ra_fig = go.Figure()
if not rain_acc.empty:
    ra_fig.add_trace(go.Bar(
        x=rain_acc.index,
        y=rain_acc["value"],
        name='Rainfall',
        marker=dict(color='#005138', line=dict(color='#005138', width=1))
    ))
ra_fig.update_layout(
    title="Accumulated Rainfall Totals (Eastern Time)",
    xaxis_title="Day (last week EST/EDT)",
    yaxis_title="Accumulated Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white'
)

st.markdown("<style>:root {--st-primary-color: #005138 !important;}</style>", unsafe_allow_html=True)
st.subheader("Fairfax Campus Sensor Location Map")

center_lat = locations_df["lat"].mean()
center_lon = locations_df["lon"].mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=16)

for _, row in locations_df.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lon']],
        radius=8,
        popup=row['name'],
        tooltip=row['name'],
        color="#01090F",
        fill=True,
        fill_color="#318ece"
    ).add_to(m)

if "selected_location" not in st.session_state:
    st.session_state["selected_location"] = None
if "button_clicked" not in st.session_state:
    st.session_state["button_clicked"] = False
if "graph_range" not in st.session_state:
    st.session_state["graph_range"] = DEFAULT_RANGE


def set_selected(location: str):
    st.session_state["selected_location"] = location
    st.session_state["graph_range"] = DEFAULT_RANGE
    st.session_state["button_clicked"] = True


def set_graph_range(range_label: str):
    st.session_state["graph_range"] = range_label
    st.session_state["button_clicked"] = True


left_col, right_col = st.columns([1, 3])

with left_col:
    # 1. Update session state if a map selection match is found
    if not matches.empty:
        st.session_state["selected_location"] = matches.iloc[0]["name"]
    
    # 2. Safely read out the selected location variable
    selected_location = st.session_state.get("selected_location")
    if selected_location:
        selection_placeholder.write(f"**Selected:** {selected_location}")

# 3. Render the interactive graphing section conditionally based on selection state
if selected_location:
    st.subheader(f"{selected_location} Water Depth")
    
    # Set proportional column structures for the date range toggle buttons
    r_col1, r_col2, r_col3, r_col4 = st.columns([1, 1, 1, 3])
    with r_col1: 
        st.button("1 Week", key="r_1w", on_click=set_graph_range, args=("1 Week",))
    with r_col2: 
        st.button("3 Days", key="r_3d", on_click=set_graph_range, args=("3 Days",))
    with r_col3: 
        st.button("24 Hours", key="r_24h", on_click=set_graph_range, args=("24 Hours",))
    with r_col4: 
        st.caption(f"Showing: {st.session_state['graph_range']}")

    # Render the targeted depth visualization profile
    fig = build_sensor_figure(
        sensor_data[selected_location], 
        selected_location, 
        sensor_y_range[selected_location], 
        st.session_state["graph_range"]
    )
    st.plotly_chart(fig, use_container_width=True)

# 4. Display general rain telemetry dashboards globally below the map components
st.subheader("Rainfall / Device Analytics")
tab1, tab2 = st.tabs(["Total Rain", "Accumulated Rain"])
with tab1: 
    st.plotly_chart(rt_fig, use_container_width=True)
with tab2: 
    st.plotly_chart(ra_fig, use_container_width=True)

