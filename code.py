import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import streamlit as st  
import folium
from streamlit_folium import st_folium

st.title("LI-COR Device Data Dashboard")

TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

if "data_window" not in st.session_state:
    end = datetime.now()
    start = end - timedelta(days=8)
    st.session_state["data_window"] = {
        "start": start,
        "end": end
    }

start = st.session_state["data_window"]["start"]
end = st.session_state["data_window"]["end"]
start_str = start.strftime("%Y-%m-%d %H:%M:%S")
end_str = end.strftime("%Y-%m-%d %H:%M:%S")

@st.cache_data
def fetch_devices():
    response = requests.get(
        "https://api.licor.cloud/v2/devices",
        headers=headers
    )

    if response.status_code != 200:
        raise RuntimeError("Could not retrieve devices.")

    return response.json().get("devices", [])

@st.cache_data
def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt
    }

    response = requests.get(
        "https://api.licor.cloud/v1/data",
        headers=headers,
        params=params
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Device {serial} data request failed: {response.status_code}"
        )

    return response.json().get("data", [])

@st.cache_data
def load_all_device_data(start_dt: str, end_dt: str):
    devices = fetch_devices()
    all_devices_data = []

    for d in devices:
        serial = d["deviceSerialNumber"]
        name = d["deviceName"]

        data = fetch_device_data(serial, start_dt, end_dt)

        if not data:
            continue

        df_tmp = pd.DataFrame(data)
        all_devices_data.append(df_tmp)

        vars_available = (
            df_tmp[
                [
                    "sensor_sn",
                    "sensor_measurement_type",
                    "unit"
                ]
            ]
            .drop_duplicates()
            .sort_values("sensor_measurement_type")
        )

        for _, row in vars_available.iterrows():
            print(
                f"  - {row['sensor_measurement_type']} "
                f"(sensor_sn: {row['sensor_sn']}, "
                f"units: {row['unit']})"
            )

    if all_devices_data:
        return pd.concat(all_devices_data, ignore_index=True)

    return pd.DataFrame()

try:
    df = load_all_device_data(start_str, end_str)
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if df.empty:
    st.text("No data returned from any devices.")
    st.stop()

# Rain sensor
rain_total = df[
    df["sensor_sn"] == "22334782-1"
].copy()

if rain_total.empty:
    st.error("Rain sensor 22334782-1 not found.")
    st.stop()

rain_total = rain_total.sort_values("timestamp")

rain_total["timestamp"] = pd.to_datetime(
    rain_total["timestamp"]
)

rain_total = rain_total.set_index("timestamp")

#Green Bridge Sensor
green_bridge = df[
    df["sensor_sn"] == "22406680-1"
].copy()

if green_bridge.empty:
    st.error("Green Bridge sensor 22406680-1 not found.")
   

green_bridge = green_bridge.sort_values("timestamp")
green_bridge["timestamp"] = pd.to_datetime(
    green_bridge["timestamp"]
)
green_bridge = green_bridge.set_index("timestamp")

gb_fig = go.Figure()

gb_fig.add_trace(go.Scatter(
    x=green_bridge.index,
    y=green_bridge["value"],
    mode='lines',
    name='Green Bridge',
    line=dict(color='#1f77b4', width=0.75)
))

gb_fig.update_layout(
    title="Green Bridge Data",
    xaxis_title="Day (last week)",
    yaxis_title="Water Depth (ft)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white',
    yaxis=dict(range=[-0.01, 0.8])
)


#st.subheader("Green Bridge Sensor Data")
#st.plotly_chart(gb_fig, use_container_width=True)



#Mason Pond Sensor
mason_pond = df[
    df["sensor_sn"] == "22406678-1"
].copy()

if mason_pond.empty:
    st.error("Mason Pond sensor 22406678-1 not found.")
    

mason_pond = mason_pond.sort_values("timestamp")
mason_pond["timestamp"] = pd.to_datetime(
    mason_pond["timestamp"]
)
mason_pond = mason_pond.set_index("timestamp")

mp_fig = go.Figure()
mp_fig.add_trace(go.Scatter(
    x=mason_pond.index,
    y=mason_pond["value"],
    mode='lines',
    name='Mason Pond',
    line=dict(color='#1f77b4', width=0.75)
))
mp_fig.update_layout(
    title="Mason Pond Data",
    xaxis_title="Day (last week)",
    yaxis_title="Water Depth (ft)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white',
    yaxis=dict(range=[-0.01, 0.8])
)
#st.subheader("Mason Pond Sensor Data")
#st.plotly_chart(mp_fig, use_container_width=True)


# The Hub Sensor
the_hub = df[
    df["sensor_sn"] == "22508090-1"
].copy()
the_hub = the_hub.sort_values("timestamp")
the_hub["timestamp"] = pd.to_datetime(
    the_hub["timestamp"]
)
the_hub = the_hub.set_index("timestamp")

th_fig = go.Figure()
th_fig.add_trace(go.Scatter(
    x=the_hub.index,
    y=the_hub["value"],
    mode='lines',
    name='The Hub',
    line=dict(color='#1f77b4', width=0.75)
))
th_fig.update_layout(
    title="The Hub Data",
    xaxis_title="Day (last week)",
    yaxis_title="Water Depth (ft)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white',
    yaxis=dict(range=[-0.01, 0.8])
)
#st.subheader("The Hub Sensor Data")
#st.plotly_chart(th_fig, use_container_width=True)

#Map

locations_df=pd.DataFrame({
        'name': ['Green Bridge', 'Mason Pond', 'The Hub'],
        'lat': [38.827153, 38.829022, 38.83019],
        'lon': [ -77.30703, -77.310372, -77.30398]
    })


st.subheader("Fairfax Campus Sensor Location Map")
st.write("Click on any marker on the map to view the sensor's name and to display its specific water depth data")

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




map_data = st_folium(m, width="100%", height=450, key="map")


def get_clicked_location(data, locations):
    if not data:
        return None

    for key in ["last_clicked", "last_object_clicked"]:
        candidate = data.get(key)
        if not isinstance(candidate, dict):
            continue

        lat = candidate.get("lat") or candidate.get("latitude")
        lon = candidate.get("lng") or candidate.get("lon") or candidate.get("longitude")

        if lat is None or lon is None:
            continue

        matches = locations[
            (locations["lat"].sub(lat).abs() < 0.0005) &
            (locations["lon"].sub(lon).abs() < 0.0005)
        ]

        if not matches.empty:
            return matches.iloc[0]["name"]

    return None


selected_location = get_clicked_location(map_data, locations_df)

if selected_location is not None:
    st.subheader(f"{selected_location} Water Depth")

    if selected_location == "Green Bridge":
        st.plotly_chart(gb_fig, use_container_width=True)
    elif selected_location == "Mason Pond":
        st.plotly_chart(mp_fig, use_container_width=True)
    elif selected_location == "The Hub":
        st.plotly_chart(th_fig, use_container_width=True)





# Plot
rt_fig = go.Figure()

rt_fig.add_trace(go.Scatter(
    x=rain_total.index,
    y=rain_total["value"],
    mode='lines',
    name='Rainfall',
    line=dict(color='#1f77b4')
))

rt_fig.update_layout(
    title="Rainfall Totals",
    xaxis_title="Day (last week)",
    yaxis_title="Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white'
)


# Accumulated Rain sensor
rain_acc = df[
    df["sensor_sn"] == "22334782-2"
].copy()

if rain_acc.empty:
    st.error("Accumulated Rain sensor 22334782-2 not found.")
    st.stop()

rain_acc = rain_acc.sort_values("timestamp")

rain_acc["timestamp"] = pd.to_datetime(
    rain_acc["timestamp"]
)

rain_acc = rain_acc.set_index("timestamp")



# Plot
ra_fig = go.Figure()

ra_fig.add_trace(go.Scatter(
    x=rain_acc.index,
    y=rain_acc["value"],
    mode='lines',
    name='Rainfall',
    line=dict(color='#1f77b4')
))

ra_fig.update_layout(
    title="Accumulated Rainfall Totals",
    xaxis_title="Day (last week)",
    yaxis_title="Accumulated Rain (in)",
    hovermode='x unified',
    width=1000,
    height=400,
    template='plotly_white'
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
    st.plotly_chart(rt_fig, use_container_width=True)

with acc_tab:
    st.plotly_chart(ra_fig, use_container_width=True)

