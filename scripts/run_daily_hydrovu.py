from datetime import datetime, timedelta
from config.station_map import build_output_filename, STATION_NAME_MAP

from processing.payload_to_csv import rows_to_csv_payload
from APIs.hydrovu_api import get_oauth_session
from APIs.hydrovu_api import get_timeseries_payload
from APIs.hydrovu_api import get_access_token
from APIs.hydrovu_api import fetch_friendly_names
import os
import logging
logging.basicConfig(level=logging.INFO)


CLIENT_ID = os.environ.get("HYDROVU_CLIENT_ID")
CLIENT_SECRET = os.environ.get("HYDROVU_CLIENT_SECRET")

STATIONS = list(STATION_NAME_MAP.keys())


def main():
    # ✅ time window: last 24 hours
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=1)

    start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ✅ authenticate once
    session = get_oauth_session(CLIENT_ID)
    get_access_token(session, CLIENT_ID, CLIENT_SECRET)

    # ✅ cache friendly names once
    friendly_names = fetch_friendly_names(session)

    for location_id in STATIONS:
        print(f"Processing {location_id}...")

        payload = get_timeseries_payload(
            session,
            location_id=location_id,
            start_time=start,
            end_time=end,
            meta={
                "name": STATION_NAME_MAP.get(location_id),
                "id": location_id
            },
            friendly_names=friendly_names
        )

        # ✅ check if data exists
        if not payload["rows_by_ts"]:
            print(f"No data for {location_id}, skipping...")
            continue

        # ✅ generate CSV
        csv_buffer = rows_to_csv_payload(payload, default_depth_m=None)

        # ✅ build filename
        filename = build_output_filename(location_id, start, end)

        with open(filename, "wb") as f:
            f.write(csv_buffer.getvalue())

        print(f"Saved: {filename}")


if __name__ == "__main__":
    main()
