import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import folium
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from streamlit_folium import st_folium
from PIL import Image, ImageOps

# Define Eastern Time Zone (handles both EST and EDT automatically)
EASTERN_TZ = ZoneInfo("America/New_York")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  MAX WINDOW LIMIT  <-- CHANGE THIS TO 30 LATER                   ║
# ║  Max days of data a user can request per live sensor. This also  ║
# ║  controls how much history is fetched from the LI-COR API.       ║
# ╚══════════════════════════════════════════════════════════════════╝
MAX_WINDOW_DAYS = 7

# try:
#     TOKEN = st.secrets["TOKEN"]
# except (KeyError, FileNotFoundError):
#     st.error("Missing TOKEN. Add it to .streamlit/secrets.toml or your Streamlit Cloud secrets.")
#     st.stop()

TOKEN = "5tqw7ssFj2v3jUer2jp3AMENZp1FqIkwUJ0AHhC7ps9ep6gh"

# Live water depth sensors: name -> sensor_sn
SENSOR_CONFIG = {
    "Green Bridge": "22406680-1",
    "Mason Pond": "22406678-1",
    "The Hub": "22508090-1",
    "RAC Sensor": "22308166-1",
    "Lot C #1": "22308168-1",
    "Lot C #2": "22406679-1",
    "Aquatic Center": "22406677-1",
}

# Historical CSV water depth sensors configuration
HISTORICAL_CONFIG = {
    "Eagle Bank": {
        "file": "Eagle_bank.csv",
        "time_col": "Date-Time (EST/EDT)",
        "val_col": "Water Level , ft",
        "convert_m_to_ft": False,
    },
    "Lot J": {
        "file": "Lot_k_j.csv",
        "time_col": "Date",
        "val_col": "Water level Lot J",
        "convert_m_to_ft": False,
    },
    "Lot K": {
        "file": "Lot_k_j.csv",
        "time_col": "Date",
        "val_col": "Water Level Lot K",
        "convert_m_to_ft": False,
    },
    "East Campus Upstream": {
        "file": "East_campus_upstream.csv",
        "time_col": "Date-Time (EST/EDT)",
        "val_col": "Water Level , m",
        "convert_m_to_ft": True,  # Converts meters to feet (* 3.28084)
    },
    "East Campus Downstream": {
        "file": "East_campus_downstream.csv",
        "time_col": "Date-Time (EST/EDT)",
        "val_col": "Water Level , m",
        "convert_m_to_ft": True,  # Converts meters to feet (* 3.28084)
    },
}

# Campus Watershed GeoJSON Layers Configuration
WATERSHED_LAYERS = {
    "Campus Boundary": {
        "file": "LAYERS/Campus Boundar_FeaturesToJSO.geojson",
        "geom_type": "polygon",
        "color": "#333333",
        "fill_color": "#999999",
        "fill_opacity": 0.08,
        "weight": 2.5,
        "dash_array": "6, 4",
        "legend_symbol": (
            "<span style='display:inline-block;width:16px;height:12px;"
            "background:rgba(153,153,153,0.18);border:2px dashed #333333;"
            "vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
   "Stormwater BMPs": {
        "file": "LAYERS/BMPS.geojson",
        "geom_type": "polygon",
        "color": "#00096d",
        "fill_color": "#2b8cbe",
        "fill_opacity": 0.65,
        "weight": 2.0,
        "dash_array": None,
        "tooltip_fields": ["Name", "Type"],
        "legend_symbol": (
            "<span style='display:inline-block;width:16px;height:12px;"
            "background:rgba(43,140,190,0.55);border:2px solid #006d2c;"
            "vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
    "Campus Streams": {
        "file": "LAYERS/Streams.geojson",
        "geom_type": "line",
        "color": "#08519c",
        "weight": 3.0,
        "dash_array": None,
        "legend_symbol": (
            "<span style='display:inline-block;width:18px;height:0;"
            "border-top:3.5px solid #08519c;vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
    "Culverts": {
        "file": "LAYERS/Culverts.geojson",
        "geom_type": "line",
        "color": "#88419d",
        "weight": 3.5,
        "dash_array": None,
        "legend_symbol": (
            "<span style='display:inline-block;width:18px;height:0;"
            "border-top:3.5px solid #88419d;vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
    "Storm Pipes": {
        "file": "LAYERS/Storm_Pipes.geojson",
        "geom_type": "line",
        "color": "#636363",
        "weight": 1.8,
        "dash_array": "4, 4",
        "legend_symbol": (
            "<span style='display:inline-block;width:18px;height:0;"
            "border-top:2.5px dashed #636363;vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
    "Storm Inlets": {
        "file": "LAYERS/Inlets.geojson",
        "geom_type": "point",
        "color": "#7f2704",
        "fill_color": "#eca137",
        "radius": 1.5,
        "tooltip_fields": ["Inlet_ID", "Type"],
        "legend_symbol": (
            "<span style='display:inline-block;width:10px;height:10px;"
            "background:#fdae6b;border:1.5px solid #7f2704;"
            "vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
    "Storm Outlets": {
        "file": "LAYERS/Outlets.geojson",
        "geom_type": "point",
        "color": "#015655",
        "fill_color": "#06d2b0",
        "radius":  1.5,
        "tooltip_fields": ["Type", "StrType"],
        "legend_symbol": (
            "<span style='display:inline-block;width:10px;height:10px;"
            "background:#06d2b0;border:1.5px solid #015655;"
            "vertical-align:middle;margin-right:6px;'></span>"
        ),
    },
}

# Image mapping for each sensor
SENSOR_IMAGES = {
    "Green Bridge": "pictures/Green Bridge.png",
    "Mason Pond": "pictures/Mason Pond.png",
    "The Hub": "pictures/The Hub.png",
    "RAC Sensor": "pictures/The RAC.png",
    "Lot C #1": "pictures/Lot C1.png",
    "Lot C #2": "pictures/Lot C2.png",
    "Aquatic Center": "pictures/Aquatic Center.png",
}

RAIN_SENSORS = ["22334782-1", "22334782-2"]
NEEDED_SERIALS = {sn.rsplit("-", 1)[0] for sn in [*SENSOR_CONFIG.values(), *RAIN_SENSORS]}

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

if "data_window" not in st.session_state:
    now = datetime.now(EASTERN_TZ)
    end = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
    start = end - timedelta(days=MAX_WINDOW_DAYS + 1)
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


MAX_WORKERS = 4
API_DATA_URL = "https://api.licor.cloud/v1/data"


def fetch_device_data(session: requests.Session, serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt
    }

    for attempt in range(3):
        response = session.get(API_DATA_URL, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        break

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


@st.cache_data(ttl=3600, show_spinner="Live data will be available momentarily.")
def load_all_device_data(start_dt: datetime, end_dt: datetime):
    devices = fetch_devices()

    wanted = [d for d in devices if d["deviceSerialNumber"] in NEEDED_SERIALS]
    devices = wanted or devices

    chunks = daterange_chunks(start_dt, end_dt, chunk_days=1)
    tasks = [
        (
            d["deviceSerialNumber"],
            cs.strftime("%Y-%m-%d %H:%M:%S"),
            ce.strftime("%Y-%m-%d %H:%M:%S"),
        )
        for d in devices
        for cs, ce in chunks
    ]

    session = requests.Session()

    def work(task):
        try:
            return fetch_device_data(session, *task), None
        except (RuntimeError, requests.RequestException) as exc:
            return [], str(exc)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(work, tasks))

    frames = []
    for data, err in results:
        if err:
            st.warning(err)
        elif data:
            frames.append(pd.DataFrame(data))

    if not frames:
        return pd.DataFrame()

    return keep_half_hour_marks(pd.concat(frames, ignore_index=True))


@st.cache_data
def load_historical_data():
    """Load and standardize water depth data from local historical CSV files."""
    hist_data = {}
    for name, cfg in HISTORICAL_CONFIG.items():
        filepath = cfg["file"]
        if not os.path.exists(filepath):
            hist_data[name] = pd.DataFrame(columns=["value"])
            continue

        raw = pd.read_csv(filepath)
        t_col = cfg["time_col"]
        v_col = cfg["val_col"]

        if t_col == "Date":
            ts = pd.to_datetime(
                raw[t_col], format="%y-%m-%d %H:%M:%S %z", utc=True
            ).dt.tz_convert(EASTERN_TZ)
        else:
            ts = pd.to_datetime(
                raw[t_col], format="%m/%d/%Y %H:%M:%S"
            ).dt.tz_localize(EASTERN_TZ, ambiguous="NaT", nonexistent="shift_forward")

        vals = pd.to_numeric(raw[v_col], errors="coerce")
        if cfg.get("convert_m_to_ft"):
            vals = vals * 3.28084

        sdf = pd.DataFrame({"timestamp": ts, "value": vals}).dropna(subset=["timestamp", "value"])
        sdf = sdf.sort_values("timestamp").set_index("timestamp")
        hist_data[name] = sdf

    return hist_data


@st.cache_data
def load_geojson(filename: str):
    """Load and cache a GeoJSON file from the current directory or 'layers/' subfolder."""
    for candidate in [filename, os.path.join("layers", filename)]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


try:
    df = load_all_device_data(start, end)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if df.empty:
    st.text("No data returned from any devices.")
    st.stop()

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

    if range_label == "All Data":
        return sensor_df

    if range_label == "Custom":
        custom = st.session_state.get("custom_range")
        if custom:
            c_start, c_end = custom
            return sensor_df[(sensor_df.index >= c_start) & (sensor_df.index <= c_end)]
        range_label = DEFAULT_RANGE

    latest = sensor_df.index.max()
    cutoff = latest - RANGE_OPTIONS.get(range_label, RANGE_OPTIONS[DEFAULT_RANGE])
    return sensor_df[sensor_df.index >= cutoff]


def describe_range(range_label: str, sensor_df: pd.DataFrame = None) -> str:
    if range_label == "Custom" and st.session_state.get("custom_range"):
        c_start, c_end = st.session_state["custom_range"]
        return f"{c_start:%b %d %H:%M} – {c_end:%b %d %H:%M}"
    if range_label == "All Data" and sensor_df is not None and not sensor_df.empty:
        return f"All Data ({sensor_df.index.min():%b %d} – {sensor_df.index.max():%b %d})"
    return range_label


def range_file_suffix(range_label: str) -> str:
    if range_label == "Custom" and st.session_state.get("custom_range"):
        c_start, c_end = st.session_state["custom_range"]
        return f"{c_start:%Y%m%d_%H%M}_to_{c_end:%Y%m%d_%H%M}"
    return range_label.lower().replace(" ", "_")


def build_sensor_figure(
    sensor_df: pd.DataFrame, name: str, y_range, range_label: str, is_historical: bool = False
) -> go.Figure:
    filtered = filter_by_range(sensor_df, range_label)
    display_label = describe_range(range_label, sensor_df)
    line_color = "#E06D06" if is_historical else "#005138"

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=filtered.index,
        y=filtered["value"] if "value" in filtered else [],
        mode='lines',
        name=name,
        line=dict(color=line_color, width=0.85)
    ))
    fig.update_layout(
        title=f"{name} {'Historical ' if is_historical else ''}Data ({display_label}) - Eastern Time",
        xaxis_title=f"Time ({display_label} EST/EDT)",
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

# Load live sensors
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

# Load historical sensors
historical_sensor_data = load_historical_data()
for h_name, hdf in historical_sensor_data.items():
    sensor_data[h_name] = hdf
    sensor_y_range[h_name] = compute_y_range(hdf["value"]) if not hdf.empty else [-0.01, 0.8]

# Live Map Locations
locations_df = pd.DataFrame({
    'name': ['Green Bridge', 'Mason Pond', 'The Hub', 'RAC Sensor', 'Lot C #1', 'Lot C #2', 'Aquatic Center'],
    'lat': [38.827153, 38.829022, 38.83019, 38.830625, 38.825383, 38.825994, 38.826328],
    'lon': [-77.30703, -77.310372, -77.30398, -77.310689, -77.303769, -77.304797, -77.303419]
})

# Historical Map Locations
historical_locations_df = pd.DataFrame({
    'name': [
        'Eagle Bank',
        'Lot J',
        'Lot K',
        'East Campus Upstream',
        'East Campus Downstream',
    ],
    'lat': [
        38.827209,
        38.828452,
        38.828107,
        38.830417,
        38.831483,
    ],
    'lon': [
        -77.307573,
        -77.311759,
        -77.311557,
        -77.303741,
        -77.303637,
    ]
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

# Session state defaults
if "selected_location" not in st.session_state:
    st.session_state["selected_location"] = None
if "button_clicked" not in st.session_state:
    st.session_state["button_clicked"] = False
if "graph_range" not in st.session_state:
    st.session_state["graph_range"] = DEFAULT_RANGE
if "custom_range" not in st.session_state:
    st.session_state["custom_range"] = None
if "custom_error" not in st.session_state:
    st.session_state["custom_error"] = None
if "show_historical" not in st.session_state:
    st.session_state["show_historical"] = False

# Initialize all watershed layer checkboxes to False (off by default)
for layer_name in WATERSHED_LAYERS:
    state_key = f"layer_{layer_name}"
    if state_key not in st.session_state:
        st.session_state[state_key] = False

# Universal CSS targeting `.stButton button` (works across all Streamlit versions)
st.markdown(
    """
    <style>
    :root {
        --st-primary-color: #005138 !important;
    }

    /* Force all Streamlit buttons to allow multi-line text wrapping with compact height */
    .stButton > button,
    div[data-testid="stButton"] > button {
        height: auto !important;
        min-height: 40px !important;
        padding: 4px 6px !important;
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        line-height: 1.15 !important;
    }

    /* Target all inner elements (div, p, span) inside Streamlit buttons so ellipsis/nowrap is disabled */
    .stButton > button *,
    div[data-testid="stButton"] > button * {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
        overflow-wrap: break-word !important;
        overflow: visible !important;
        text-overflow: clip !important;
        line-height: 1.15 !important;
        font-size: 0.8rem !important;
        text-align: center !important;
        margin: 0 !important;
    }

    /* Keep download button on single line */
    .stDownloadButton > button,
    div[data-testid="stDownloadButton"] > button {
        white-space: nowrap !important;
        width: auto !important;
        min-width: 100% !important;
    }
    .stDownloadButton > button *,
    div[data-testid="stDownloadButton"] > button * {
        white-space: nowrap !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_btn_label(name: str) -> str:
    """Insert a clean line break for multi-word sensor names so they stack neatly on 2 lines."""
    explicit_breaks = {
        "Green Bridge": "Green\nBridge",
        "Mason Pond": "Mason\nPond",
        "RAC Sensor": "RAC\nSensor",
        "Aquatic Center": "Aquatic\nCenter",
        "Eagle Bank": "Eagle\nBank",
        "East Campus Upstream": "East Campus\nUpstream",
        "East Campus Downstream": "East Campus\nDownstream",
    }
    return explicit_breaks.get(name, name)


def toggle_historical():
    st.session_state["show_historical"] = not st.session_state["show_historical"]
    st.session_state["button_clicked"] = True
    if (
        not st.session_state["show_historical"]
        and st.session_state.get("selected_location") in HISTORICAL_CONFIG
    ):
        st.session_state["selected_location"] = None


def on_layer_toggle():
    """Prevent old map click coordinates from re-firing when toggling watershed layers."""
    st.session_state["button_clicked"] = True


def set_selected(location: str):
    st.session_state["selected_location"] = location
    if location in HISTORICAL_CONFIG:
        st.session_state["graph_range"] = "All Data"
    else:
        st.session_state["graph_range"] = DEFAULT_RANGE
    st.session_state["custom_range"] = None
    st.session_state["custom_error"] = None
    st.session_state["button_clicked"] = True
    st.session_state["scroll_to_plot"] = True


def set_graph_range(range_label: str):
    st.session_state["graph_range"] = range_label
    st.session_state["custom_error"] = None
    st.session_state["button_clicked"] = True


def apply_custom_range(key: str, is_historical: bool = False):
    s = st.session_state
    s["button_clicked"] = True

    start_dt = datetime.combine(s[f"{key}_sd"], s[f"{key}_st"], tzinfo=EASTERN_TZ)
    end_dt = datetime.combine(s[f"{key}_ed"], s[f"{key}_et"], tzinfo=EASTERN_TZ)

    if end_dt <= start_dt:
        s["custom_error"] = "End time must be after start time."
    elif not is_historical and (end_dt - start_dt > timedelta(days=MAX_WINDOW_DAYS)):
        s["custom_error"] = f"Please request a timeframe within the {MAX_WINDOW_DAYS} days or less."
    else:
        s["custom_error"] = None
        s["custom_range"] = (start_dt, end_dt)
        s["graph_range"] = "Custom"


st.subheader("Fairfax Campus Sensor Location Map")
st.write(
    "Click on any marker on the map or use the buttons below to view the sensor's name "
    "and to display its specific water depth data."
)

# ─── Top Control Bar: Legend + Bold/Outlined Historical Toggle Button ───
ctrl_left, ctrl_right = st.columns([3.0, 1.4])
with ctrl_left:
    st.markdown(
        "<div style='display:flex; gap:16px; align-items:center; padding-top:6px; font-size:0.9rem;'>"
        "<span><span style='display:inline-block;width:12px;height:12px;border-radius:50%;background:#23631B;border:1px solid #01090F;margin-right:5px;'></span>Live Water Sensor</span>"
        "<span><span style='display:inline-block;width:12px;height:12px;border-radius:50%;background:#E06D06;border:1px solid #01090F;margin-right:5px;'></span>Historical Water Sensor</span>"
        "<span><span style='display:inline-block;width:12px;height:12px;border-radius:50%;background:#318ece;border:1px solid #01090F;margin-right:5px;'></span>Rainfall Sensor</span>"
        "</div>",
        unsafe_allow_html=True,
    )
with ctrl_right:
    hist_btn_label = (
        "**Hide Historical Data**"
        if st.session_state["show_historical"]
        else "**See Historical Data**"
    )
    st.button(
        hist_btn_label,
        key="toggle_hist_btn",
        on_click=toggle_historical,
        type="primary" if st.session_state["show_historical"] else "secondary",
        use_container_width=True,
    )

# JS hook to ensure the "See/Hide Historical Data" button gets a bold 2.5px outline
hist_outline_color = "#E06D06" if st.session_state["show_historical"] else "#005138"
components.html(
    f"""
    <script>
    const styleHistBtn = () => {{
        const btns = window.parent.document.querySelectorAll('button');
        btns.forEach(btn => {{
            if (btn.innerText.includes('Historical Data')) {{
                btn.style.setProperty('border', '2.5px solid {hist_outline_color}', 'important');
                btn.style.setProperty('font-weight', '800', 'important');
                btn.style.setProperty('box-shadow', '0 2px 5px rgba(0,0,0,0.18)', 'important');
            }}
        }});
    }};
    styleHistBtn();
    setTimeout(styleHistBtn, 150);
    </script>
    """,
    height=0,
)

# ─── Live Sensor Buttons (Green Title + Horizontal Row on Top) ───
st.markdown(
    "<p style='margin: 8px 0 4px 0; font-size: 0.95rem; font-weight: 600; color: #23631B;'>Live Sensors</p>",
    unsafe_allow_html=True,
)
live_names = list(SENSOR_CONFIG.keys())
live_cols = st.columns(len(live_names))
for col, s_name in zip(live_cols, live_names):
    safe_key = s_name.lower().replace(" ", "_").replace("#", "")
    with col:
        st.button(
            format_btn_label(s_name),
            key=f"top_{safe_key}",
            on_click=set_selected,
            args=(s_name,),
            use_container_width=True,
        )

# ─── Historical Sensor Buttons (Separate Horizontal Row on Top when Toggled) ───
if st.session_state["show_historical"]:
    st.markdown(
        "<p style='margin: 10px 0 4px 0; font-size: 0.95rem; font-weight: 600; color: #E06D06;'>Historical Sensors</p>",
        unsafe_allow_html=True,
    )
    hist_names = list(HISTORICAL_CONFIG.keys())
    hist_cols = st.columns(len(hist_names))
    for col, h_name in zip(hist_cols, hist_names):
        safe_key = h_name.lower().replace(" ", "_")
        with col:
            st.button(
                format_btn_label(h_name),
                key=f"hist_{safe_key}",
                on_click=set_selected,
                args=(h_name,),
                use_container_width=True,
            )

# Placeholder to display currently selected sensor right above the map
selection_placeholder = st.empty()

# ─── Full-Width Map ───
active_locations_df = (
    pd.concat([locations_df, historical_locations_df], ignore_index=True)
    if st.session_state["show_historical"]
    else locations_df
)

center_lat = active_locations_df["lat"].mean()
center_lon = active_locations_df["lon"].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=16,
    tiles="OpenStreetMap"
)

# 1. Add Checked Campus Watershed Layers FIRST (so sensor markers stay on top)
for layer_name, lcfg in WATERSHED_LAYERS.items():
    if st.session_state.get(f"layer_{layer_name}", False):
        gj_data = load_geojson(lcfg["file"])
        if gj_data is None:
            st.warning(f"GeoJSON file '{lcfg['file']}' not found for {layer_name}.")
            continue

        gtype = lcfg["geom_type"]
        if gtype in ("polygon", "line"):
            style_dict = {
                "color": lcfg["color"],
                "weight": lcfg["weight"],
                "opacity": 0.9,
            }
            if gtype == "polygon":
                style_dict["fillColor"] = lcfg["fill_color"]
                style_dict["fillOpacity"] = lcfg["fill_opacity"]
            if lcfg.get("dash_array"):
                style_dict["dashArray"] = lcfg["dash_array"]

            tooltip_obj = (
                folium.GeoJsonTooltip(fields=lcfg["tooltip_fields"])
                if lcfg.get("tooltip_fields")
                else layer_name
            )
            folium.GeoJson(
                gj_data,
                name=layer_name,
                style_function=lambda feature, s=style_dict: s,
                tooltip=tooltip_obj,
            ).add_to(m)

        elif gtype == "point":
            for feat in gj_data.get("features", []):
                geom = feat.get("geometry") or {}
                coords = geom.get("coordinates", [])
                if len(coords) >= 2:
                    lon_pt, lat_pt = coords[0], coords[1]
                    props = feat.get("properties") or {}
                    t_fields = lcfg.get("tooltip_fields", [])
                    t_parts = [f"{f}: {props.get(f)}" for f in t_fields if props.get(f) not in (None, "", -999)]
                    tip_text = f"{layer_name} ({', '.join(t_parts)})" if t_parts else layer_name

                    folium.CircleMarker(
                        location=[lat_pt, lon_pt],
                        radius=lcfg.get("radius", 4),
                        color=lcfg["color"],
                        weight=1.2,
                        fill=True,
                        fill_color=lcfg["fill_color"],
                        fill_opacity=0.85,
                        tooltip=tip_text,
                    ).add_to(m)

# 2. Live sensor markers (Green)
for _, row in locations_df.iterrows():
    folium.CircleMarker(
        location=[row['lat'], row['lon']],
        radius=8,
        popup=row['name'],
        tooltip=f"Click to view {row['name']} (Live)",
        color="#01090F",
        fill=True,
        fill_color="#23631B",
        fill_opacity=0.7
    ).add_to(m)

# 3. Historical sensor markers (Orange - shown only when Historical Data is toggled on)
if st.session_state["show_historical"]:
    for _, row in historical_locations_df.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=f"{row['name']} (Historical)",
            tooltip=f"Click to view {row['name']} (Historical)",
            color="#01090F",
            fill=True,
            fill_color="#E06D06",
            fill_opacity=0.85
        ).add_to(m)

# 4. Rainfall sensor marker (Blue)
folium.CircleMarker(
    location=[38.825153, -77.303136],
    radius=8,
    popup="Rainfall Sensor",
    tooltip="Scroll down to view campus rainfall data.",
    color="#01090F",
    fill=True,
    fill_color="#318ece",
    fill_opacity=0.7
).add_to(m)

map_data = st_folium(m, width="100%", height=500, key="map")

# ─── Campus Watershed Layers (Checkboxes + Visual Legend Below Map) ───
st.markdown(
    "<p style='margin: 6px 0 6px 0; font-size: 1.05rem; font-weight: 650;'>Campus Watershed Layers</p>",
    unsafe_allow_html=True,
)

layer_items = list(WATERSHED_LAYERS.items())
row1_items = layer_items[:4]
row2_items = layer_items[4:]

row1_cols = st.columns(4)
for col, (lname, lcfg) in zip(row1_cols, row1_items):
    with col:
        chk_col, sym_col = st.columns([0.18, 0.82])
        with chk_col:
            st.checkbox(
                lname,
                key=f"layer_{lname}",
                on_change=on_layer_toggle,
                label_visibility="collapsed",
            )
        with sym_col:
            st.markdown(
                f"<div style='padding-top:3px; font-size:0.88rem; white-space:nowrap;'>"
                f"{lcfg['legend_symbol']}<b>{lname}</b></div>",
                unsafe_allow_html=True,
            )

row2_cols = st.columns(4)
for col, (lname, lcfg) in zip(row2_cols[:len(row2_items)], row2_items):
    with col:
        chk_col, sym_col = st.columns([0.18, 0.82])
        with chk_col:
            st.checkbox(
                lname,
                key=f"layer_{lname}",
                on_change=on_layer_toggle,
                label_visibility="collapsed",
            )
        with sym_col:
            st.markdown(
                f"<div style='padding-top:3px; font-size:0.88rem; white-space:nowrap;'>"
                f"{lcfg['legend_symbol']}<b>{lname}</b></div>",
                unsafe_allow_html=True,
            )


if st.session_state["button_clicked"]:
    st.session_state["button_clicked"] = False
else:
    if map_data and map_data.get("last_object_clicked"):
        loc = map_data["last_object_clicked"]

        active_with_dist = active_locations_df.copy()
        active_with_dist["dist"] = (
            (active_with_dist["lat"] - loc.get("lat", 0)) ** 2
            + (active_with_dist["lon"] - loc.get("lng", 0)) ** 2
        ) ** 0.5
        matches = active_with_dist[active_with_dist["dist"] < 0.0005].sort_values("dist")

        if not matches.empty:
            clicked_name = matches.iloc[0]["name"]
            if clicked_name != st.session_state.get("selected_location"):
                st.session_state["graph_range"] = (
                    "All Data" if clicked_name in HISTORICAL_CONFIG else DEFAULT_RANGE
                )
                st.session_state["custom_range"] = None
                st.session_state["custom_error"] = None
                st.session_state["scroll_to_plot"] = True
            st.session_state["selected_location"] = clicked_name


if st.session_state.get("selected_location"):
    sel_name = st.session_state["selected_location"]
    badge = " (Historical)" if sel_name in HISTORICAL_CONFIG else ""
    selection_placeholder.markdown(
        f"<p style='margin: 4px 0 6px 0; font-size: 0.95rem;'><b>Selected:</b> {sel_name}{badge}</p>",
        unsafe_allow_html=True,
    )


selected_location = st.session_state.get("selected_location")

if selected_location is not None:
    is_hist = selected_location in HISTORICAL_CONFIG

    st.markdown(
        "<div id='sensor-plot-anchor' style='scroll-margin-top: 60px;'></div>",
        unsafe_allow_html=True,
    )
    st.subheader(
        f"{selected_location} {'Historical ' if is_hist else ''}Water Depth"
    )

    if st.session_state.pop("scroll_to_plot", False):
        components.html(
            f"""
            <script>
            const tryScroll = (n) => {{
                const el = window.parent.document.getElementById("sensor-plot-anchor");
                if (el) {{
                    el.scrollIntoView({{behavior: "smooth", block: "start"}});
                }} else if (n > 0) {{
                    setTimeout(() => tryScroll(n - 1), 100);
                }}
            }};
            tryScroll(20);
            </script>
            """,
            height=0,
        )

    curr_df = sensor_data[selected_location]
    key = "cw_" + selected_location.lower().replace(" ", "_").replace("#", "")

    if is_hist:
        r_col0, r_col1, r_col2, r_col3, r_col4 = st.columns([1, 1, 1, 1, 2.5])
        with r_col0:
            st.button("All Data", key="range_all", on_click=set_graph_range, args=("All Data",))
        with r_col1:
            st.button("1 Week", key="range_1w", on_click=set_graph_range, args=("1 Week",))
        with r_col2:
            st.button("3 Days", key="range_3d", on_click=set_graph_range, args=("3 Days",))
        with r_col3:
            st.button("24 Hours", key="range_24h", on_click=set_graph_range, args=("24 Hours",))
        with r_col4:
            st.caption(f"Showing: {describe_range(st.session_state['graph_range'], curr_df)}")
    else:
        range_col1, range_col2, range_col3, range_col4 = st.columns([1, 1, 1, 3])
        with range_col1:
            st.button("1 Week", key="range_1w", on_click=set_graph_range, args=("1 Week",))
        with range_col2:
            st.button("3 Days", key="range_3d", on_click=set_graph_range, args=("3 Days",))
        with range_col3:
            st.button("24 Hours", key="range_24h", on_click=set_graph_range, args=("24 Hours",))
        with range_col4:
            st.caption(f"Showing: {describe_range(st.session_state['graph_range'], curr_df)}")

    # --- Custom time window ---
    with st.expander(
        "Custom time window (Eastern Time)",
        expanded=(st.session_state["graph_range"] == "Custom"),
    ):
        if curr_df.empty:
            st.info("No data available for this sensor.")
        else:
            earliest, latest = curr_df.index.min(), curr_df.index.max()
            def_start = earliest if is_hist else max(latest - timedelta(days=3), earliest)

            with st.form(f"{key}_form"):
                c1, c2, c3, c4 = st.columns(4)
                c1.date_input("Start date", value=def_start.date(),
                              min_value=earliest.date(), max_value=latest.date(), key=f"{key}_sd")
                c2.time_input("Start time", value=def_start.time(),
                              step=timedelta(minutes=30), key=f"{key}_st")
                c3.date_input("End date", value=latest.date(),
                              min_value=earliest.date(), max_value=latest.date(), key=f"{key}_ed")
                c4.time_input("End time", value=latest.time(),
                              step=timedelta(minutes=30), key=f"{key}_et")

                if is_hist:
                    st.caption(
                        f"Available historical record: {earliest:%b %d, %Y %H:%M} to {latest:%b %d, %Y %H:%M}"
                    )
                else:
                    st.caption(f"Maximum window: Past {MAX_WINDOW_DAYS} days")

                st.form_submit_button(
                    "Apply custom window",
                    on_click=apply_custom_range,
                    args=(key, is_hist),
                )

            if st.session_state.get("custom_error"):
                st.error(st.session_state["custom_error"])

    sensor_fig = build_sensor_figure(
        curr_df,
        selected_location,
        sensor_y_range[selected_location],
        st.session_state["graph_range"],
        is_historical=is_hist,
    )

    selected_df = filter_by_range(curr_df, st.session_state["graph_range"])
    if selected_df.empty:
        st.warning("No readings in the selected window.")

    st.plotly_chart(sensor_fig, width='stretch')

    # --- CSV Download & Sensor Photo Section ---
    current_range = st.session_state["graph_range"]
    download_df = selected_df.reset_index()

    if not download_df.empty and "timestamp" in download_df.columns:
        download_df["timestamp"] = download_df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    if "value" in download_df.columns:
        download_df = download_df.rename(columns={"value": "water_depth_ft"})

    safe_name = selected_location.lower().replace(" ", "_").replace("#", "")

    left_dl_col, img_col = st.columns([5, 1])

    with left_dl_col:
        st.markdown("<p style='margin: 0 0 8px 0; font-weight: 650;'>Download Data</p>", unsafe_allow_html=True)
        st.download_button(
            label=f"Download CSV ({describe_range(current_range, curr_df)})",
            data=download_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{safe_name}_{range_file_suffix(current_range)}_data.csv",
            mime="text/csv",
            key="dl_selected",
            disabled=download_df.empty,
            use_container_width=True,
        )
    with img_col:
        image_path = SENSOR_IMAGES.get(selected_location)
        if image_path:
            try:
                img = Image.open(image_path)
                square_img = ImageOps.fit(img, (400, 400), Image.Resampling.LANCZOS)
                st.image(square_img, caption=selected_location, use_container_width=True)
            except Exception:
                st.caption("Photo unavailable")
        else:
            st.caption("No image set")

st.subheader("Campus Rainfall Data")
st.write("These charts show rainfall measured by the campus rain sensor over the past week.")
acc_tab, rain_tab = st.tabs(["Accumulated Rain", "Total Rain"])

with rain_tab:
    st.plotly_chart(rt_fig, width='stretch')

with acc_tab:
    st.plotly_chart(ra_fig, width='stretch')

