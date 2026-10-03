# fetch_data.py
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests

EASTERN_TZ = ZoneInfo("America/New_York")
TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"
headers = {"Authorization": f"Bearer {TOKEN}"}


def fetch_devices():
    response = requests.get(
        "https://licor.cloud", headers=headers, timeout=30
    )
    if response.status_code != 200:
        raise RuntimeError(f"Could not retrieve devices list. Status: {response.status_code}")
    return response.json().get("devices", [])


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

    if "timestamp" not in df_chunk.columns or "sensor_sn" not in df_chunk.columns:
        print("Data parsing warning: Required columns missing from payload chunk.")
        return df_chunk.iloc[0:0]

    df_chunk = df_chunk.copy()
    
    df_chunk["timestamp"] = pd.to_datetime(df_chunk["timestamp"], utc=True)
    df_chunk["timestamp"] = df_chunk["timestamp"].dt.tz_convert(EASTERN_TZ)

    picked_frames = []
    for sensor, group in df_chunk.groupby("sensor_sn"):
        sorted_group = group.sort_values("timestamp").set_index("timestamp")
        resampled = (
            sorted_group.resample("30min")
            .first()
            .dropna(how="all")
        )
        resampled["sensor_sn"] = sensor
        picked_frames.append(resampled.reset_index())

    if not picked_frames:
        return df_chunk.iloc[0:0]

    return pd.concat(picked_frames, ignore_index=True)


def main():
    print("Initializing background transformation pipeline...")
    end = datetime.now(EASTERN_TZ)
    start = end - timedelta(days=8)

    try:
        devices = fetch_devices()
        print(f"Successfully discovered {len(devices)} active logging units.")
    except Exception as exc:
        print(f"Critical execution error during initialization phase: {exc}")
        return

    all_devices_data = []
    chunks = daterange_chunks(start, end, chunk_days=1)

    for d in devices:
        serial = d.get("deviceSerialNumber")
        if not serial:
            continue

        print(f"Querying sensor data patterns for hardware signature: {serial}")
        for chunk_start, chunk_end in chunks:
            # Enforce strict ISO-8601 formatting format containing the clear 'T' delimiter rule
            chunk_start_str = chunk_start.strftime("%Y-%m-%dT%H:%M:%S")
            chunk_end_str = chunk_end.strftime("%Y-%m-%dT%H:%M:%S")

            try:
                data = fetch_device_data(serial, chunk_start_str, chunk_end_str)
                if not data:
                    continue

                df_chunk = pd.DataFrame(data)
                df_chunk = keep_half_hour_marks(df_chunk)

                if not df_chunk.empty:
                    all_devices_data.append(df_chunk)
            except Exception as exc:
                print(f"Skipped intermittent network request failure: {exc}")
                continue

    if not all_devices_data:
        print("Completed tracking evaluation: Zero data payloads recorded.")
        return

    df = pd.concat(all_devices_data, ignore_index=True)
    df["timestamp"] = df["timestamp"].astype(str)
    
    df.to_csv("latest_sensor_data.csv", index=False)
    print("Success: latest_sensor_data.csv dataset refreshed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as global_error:
        print(f"Fatal transformation processing error: {global_error}")
        import traceback
        traceback.print_exc()
        exit(1)

