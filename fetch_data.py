# fetch_data.py
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import os
import pandas as pd
import requests

EASTERN_TZ = ZoneInfo("America/New_York")
TOKEN = "DV4iI3rviAxrn48ygbyqsYTIVx7NGTzan0bOewbnM47Y8B42"
headers = {"Authorization": f"Bearer {TOKEN}"}


def fetch_devices():
    res = requests.get(
        "https://licor.cloud", headers=headers, timeout=30
    )
    return res.json().get("devices", []) if res.status_code == 200 else []


def fetch_device_data(serial: str, start_dt: str, end_dt: str):
    params = {
        "loggers": serial,
        "start_date_time": start_dt,
        "end_date_time": end_dt,
    }
    res = requests.get(
        "https://licor.cloud",
        headers=headers,
        params=params,
        timeout=30,
    )
    return res.json().get("data", []) if res.status_code == 200 else []


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
    print("Starting background data fetch...")
    end = datetime.now(EASTERN_TZ)
    start = end - timedelta(days=8)

    devices = fetch_devices()
    all_devices_data = []
    chunks = daterange_chunks(start, end, chunk_days=1)

    for d in devices:
        serial = d["deviceSerialNumber"]
        for chunk_start, chunk_end in chunks:
            try:
                data = fetch_device_data(
                    serial,
                    chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                    chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                )
                if data:
                    df_chunk = pd.DataFrame(data)
                    df_chunk = keep_half_hour_marks(df_chunk)
                    if not df_chunk.empty:
                        all_devices_data.append(df_chunk)
            except Exception as e:
                print(f"Skipping failed chunk for {serial}: {e}")

    if all_devices_data:
        df = pd.concat(all_devices_data, ignore_index=True)
        # Force timestamps to strings so they save cleanly without timezone bugs
        df["timestamp"] = df["timestamp"].astype(str)
        df.to_csv("latest_sensor_data.csv", index=False)
        print("Successfully updated latest_sensor_data.csv")
    else:
        print("No new data fetched.")


if __name__ == "__main__":
    main()
