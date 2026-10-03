# fetch_data.py
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests

# 1. Exact configurations from your original app
EASTERN_TZ = ZoneInfo("America/New_York")
TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"
headers = {"Authorization": f"Bearer {TOKEN}"}


# 2. Your exact original fetch_devices logic (minus st elements)
def fetch_devices():
    response = requests.get(
        "https://licor.cloud", headers=headers, timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError("Could not retrieve devices.")
    return response.json().get("devices", [])


# 3. Your exact original fetch_device_data logic
def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt,
    }
    response = requests.get(
        "https://licor.cloud",
        headers=headers,
        params=params,
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Device {serial} data request failed: {response.status_code}"
        )
    return response.json().get("data", [])


# 4. Your exact original daterange_chunks utility
def daterange_chunks(start_dt: datetime, end_dt: datetime, chunk_days: int = 1):
    chunks = []
    current = start_dt
    while current < end_dt:
        chunk_end = min(current + timedelta(days=chunk_days), end_dt)
        chunks.append((current, chunk_end))
        current = chunk_end
    return chunks


# 5. Your exact original keep_half_hour_marks calculations
def keep_half_hour_marks(df_chunk: pd.DataFrame) -> pd.DataFrame:
    if df_chunk.empty:
        return df_chunk
    df_chunk = df_chunk.copy()
    df_chunk["timestamp"] = pd.to_datetime(
        df_chunk["timestamp"], utc=True
    ).dt.tz_convert(EASTERN_TZ)

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


# 6. Main execution engine matching your original app startup steps
def main():
    print("Starting data pre-fetch pipeline...")

    # Mirroring your 8-day original data window anchor
    end = datetime.now(EASTERN_TZ)
    start = end - timedelta(days=8)

    try:
        devices = fetch_devices()
    except RuntimeError as exc:
        print(f"Initialization Failed: {exc}")
        return

    all_devices_data = []
    chunks = daterange_chunks(start, end, chunk_days=1)

    for d in devices:
        serial = d["deviceSerialNumber"]
        for chunk_start, chunk_end in chunks:
            chunk_start_str = chunk_start.strftime("%Y-%m-%d %H:%M:%S")
            chunk_end_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")

            try:
                data = fetch_device_data(serial, chunk_start_str, chunk_end_str)
            except RuntimeError as exc:
                # Replaced st.warning with a python background log print statement
                print(f"Warning skipped: {exc}")
                continue

            if not data:
                continue

            df_chunk = pd.DataFrame(data)
            df_chunk = keep_half_hour_marks(df_chunk)

            if df_chunk.empty:
                continue

            all_devices_data.append(df_chunk)

    if not all_devices_data:
        print("No data returned from any devices during this window loop.")
        return

    # Merge everything and save locally to disk
    df = pd.concat(all_devices_data, ignore_index=True)

    # Convert timestamps back to clean string formatting to preserve file compatibility
    df["timestamp"] = df["timestamp"].astype(str)
    df.to_csv("latest_sensor_data.csv", index=False)
    print("Successfully built and updated latest_sensor_data.csv!")


if __name__ == "__main__":
    main()

