import io
import csv

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
    buff.seek(0)

    return buff
