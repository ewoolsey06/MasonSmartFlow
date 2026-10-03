# fetch_data.py
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests

EASTERN_TZ = ZoneInfo("America/New_York")
TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"
headers = {"Authorization": f"Bearer {TOKEN}"}


def fetch_devices():
    try:
        res = requests.get(
            "https://licor.cloud", headers=headers, timeout=30
        )
        if res.status_code == 200:
            return res.json().get("devices", [])
        print(f"Devices API warning: Status code {res.status_code}")
    except Exception as e:
        print(f"Error fetching devices list: {e}")
    return []


def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt,
    }
    try:
        res = requests.get(
            "https://licor.cloud",
            headers=headers,
            params=params,
            timeout=30,
        )

        if res.status_code == 200:
            # Safely attempt to parse JSON to avoid crashing on empty or HTML text strings
            return res.json().get("data", [])
        else:
            print(
                f"Device {serial} warning: Status {res.status_code} for timeframe {start_dt} to {end_dt}"
            )
    except requests.exceptions.JSONDecodeError:
        print(
            f"Device {serial} skipped: API did not return valid JSON data for timeframe {start_dt} to {end_dt}"
        )
    except Exception as e:
        print(f"Network error on device {serial}: {e}")
    return []


def daterange_chunks(start_dt: datetime, end_dt: datetime, chunk_days=1):
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
    return (
        pd.concat(picked_frames, ignore_index=True)
        if picked_frames
        else df_chunk.iloc[0:0]
    )


def main():
    print("Starting bulletproof background data fetch...")
    end = datetime.now(EASTERN_TZ)
    start = end - timedelta(days=8)

    devices = fetch_devices()
    if not devices:
        print("No active devices found. Background script exiting early.")
        return

    all_devices_data = []
    chunks = daterange_chunks(start, end, chunk_days=1)

    for d in devices:
        serial = d.get("deviceSerialNumber")
        if not serial:
            continue

        for chunk_start, chunk_end in chunks:
            chunk_start_str = chunk_start.strftime("%Y-%m-%d %H:%M:%S")
            chunk_end_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")

            data = fetch_device_data(serial, chunk_start_str, chunk_end_str)
            if not data:
                continue

            df_chunk = pd.DataFrame(data)
            df_chunk = keep_half_hour_marks(df_chunk)

            if not df_chunk.empty:
                all_devices_data.append(df_chunk)

    if all_devices_data:
        df = pd.concat(all_devices_data, ignore_index=True)
        df["timestamp"] = df["timestamp"].astype(str)
        df.to_csv("latest_sensor_data.csv", index=False)
        print("Successfully updated latest_sensor_data.csv without crashes.")
    else:
        print("No new data points retrieved during this hour.")


if __name__ == "__main__":
    main()
