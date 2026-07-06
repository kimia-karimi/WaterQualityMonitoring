import io
import csv
import pandas as pd
from pathlib import Path
def build_metadata_block(location_meta, latitude, longitude):
    return [
        "Location Properties",
        f'Location Name = {location_meta.get("name", "Unknown")}',
        f'Location ID = {location_meta.get("id", "Unknown")}',
        f'Latitude = {latitude} °',
        f'Longitude = {longitude} °',
        "Time shown in UTC",
        "",
        ""
    ]


def build_columns(parameters):
    cols = ["Date Time"]
    for p in parameters.values():
        cols.append(f'{p["parameterName"]} ({p["unitName"]})')
    return cols


def rows_to_csv_payload(payload, default_depth_m=None):
    rows_by_ts = payload["rows_by_ts"]
    parameters = payload["parameters"]
    location_meta = payload["location_meta"]
    lat = payload["latitude"]
    lon = payload["longitude"]

    metadata = build_metadata_block(location_meta, lat, lon)
    columns = build_columns(parameters)

    # optional depth handling
    if default_depth_m is not None:
        columns.append("Depth (m)")
        for ts in rows_by_ts:
            rows_by_ts[ts].append(default_depth_m)

    buff = io.BytesIO()
    text = io.TextIOWrapper(buff, encoding="utf-8", newline="")
    writer = csv.writer(text, quoting=csv.QUOTE_ALL)

    for line in metadata:
        writer.writerow([line])

    writer.writerow(columns)

    for ts in sorted(rows_by_ts.keys()):
        writer.writerow([ts] + rows_by_ts[ts])

    text.flush()
    text.detach()
    buff.seek(0)

    return buff

def payload_to_dataframe(payload, default_depth_m=None):
    
    """
    Convert HydroVu payload into a wide pandas DataFrame.

    Output:
        index = time
        columns = HydroVu parameter names
    """


    rows_by_ts = payload["rows_by_ts"]
    parameters = payload["parameters"]

    columns = build_columns(parameters)

    records = []

    for ts, values in rows_by_ts.items():

        row = dict(zip(columns[1:], values))

        row["timestamp"] = pd.to_datetime(ts)

        if default_depth_m is not None:
            row["Depth (m)"] = default_depth_m

        records.append(row)

    df = pd.DataFrame(records)

    df = df.sort_values("timestamp")

    df = df.set_index("timestamp")

    return df



def append_or_replace_timeseries(new_df, output_path, time_col="time", subset=None):
    """
    Append new data to an existing CSV, remove duplicates, sort by time,
    and write back to disk.

    For wide data:
        subset = ["time"]

    For long QC data:
        subset = ["station_id", "parameter", "time"]
    """

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if new_df.empty:
        return

    new_df = new_df.copy()

    if time_col in new_df.columns:
        new_df[time_col] = pd.to_datetime(new_df[time_col])

    if output_path.exists():
        old_df = pd.read_csv(output_path)

        if time_col in old_df.columns:
            old_df[time_col] = pd.to_datetime(old_df[time_col])

        combined = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined = new_df

    if subset is not None:
        combined = combined.drop_duplicates(subset=subset, keep="last")
    else:
        combined = combined.drop_duplicates(keep="last")

    if time_col in combined.columns:
        combined = combined.sort_values(time_col)

    combined.to_csv(output_path, index=False)



def dataframe_to_wide_output(df, location_id, station_name):
    """
    Convert the payload dataframe into the appendable wide output table.

    Output columns:
        station_id
        station_name
        Date Time
        parameter columns...
    """

    wide_df = df.copy()

    if wide_df.empty:
        return wide_df

    wide_df = wide_df.reset_index()

    # payload_to_dataframe uses index name "timestamp"
    # after reset_index, the column is usually "timestamp"
    if "timestamp" in wide_df.columns:
        wide_df = wide_df.rename(columns={"timestamp": "Date Time"})
    elif "time" in wide_df.columns:
        wide_df = wide_df.rename(columns={"time": "Date Time"})
    elif "index" in wide_df.columns:
        wide_df = wide_df.rename(columns={"index": "Date Time"})

    wide_df.insert(0, "station_id", location_id)
    wide_df.insert(1, "station_name", station_name)

    return wide_df
