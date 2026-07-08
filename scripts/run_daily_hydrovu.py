from datetime import datetime, timedelta
from config.station_map import build_output_filename, STATION_NAME_MAP, get_station_names,find_candidate_locations
from processing.payload_to_csv import rows_to_csv_payload, payload_to_dataframe, append_or_replace_timeseries, dataframe_to_wide_output
from APIs.hydrovu_api import get_oauth_session, fetch_all_locations, get_timeseries_payload, get_access_token, fetch_friendly_names, upload_to_s3, append_csv, get_last_timestamp, find_active_location, add_station_metadata_to_qc
from processing.qartod_tests import run_qartod
import os
import logging
logging.basicConfig(level=logging.INFO)
from pathlib import Path

import yaml
import pandas as pd


CLIENT_ID = os.environ.get("HYDROVU_CLIENT_ID")
CLIENT_SECRET = os.environ.get("HYDROVU_CLIENT_SECRET")


CONFIG_PATH = Path("config/qc_config.yml")

OUTPUT_DIR = Path(".")



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
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            qc_config = yaml.safe_load(f)
    STATIONS = get_station_names()
    all_locations = fetch_all_locations(session)


    for location_id in STATIONS:
        #print(f"Processing {location_id}...")
        candidates = find_candidate_locations(
            all_locations,location_id)
        
        filename = Path(f"{location_id}_all.csv")
        if not filename.exists():
             start = "2026-01-01T00:00:00Z"
        else:
             start = get_last_timestamp(filename)

        end = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")



        location,payload = find_active_location(
            session,
            candidates,
            start=start,
            end=end,
            station_name=location_id,
            friendly_names=friendly_names
        )

        # ✅ check if data exists
        if not payload["rows_by_ts"]:
            print(f"No data for {location_id}, skipping...")
            continue
        logging.info(
            "Using HydroVu ID %s for %s",
            {location["id"]},
            location_id,
)


        # ✅ convert payload to wide dataframe (for qaqc)
        df_wide = payload_to_dataframe(payload, default_depth_m=None)
        if df_wide.empty:
            logging.info(
                "Payload converted to empty dataframe for %s (%s), skipping.",
                get_station_names(location_id),
                location_id,
            )
            continue
        
    
        # ✅ generate CSV
        csv_buffer = rows_to_csv_payload(payload, default_depth_m=None)
        print(type(csv_buffer))
        # ✅ build filename
        #filename = build_output_filename(location_id, start, end)
        


        append_csv(filename, csv_buffer)


        print(f"Updated: {filename}")
        #upload_to_s3(filename)
        
        
        #qc_path = f"{get_station_name(location_id)}_qartod_long_all.csv"
        # ✅ run QARTOD and save/append long QC table
        
        


        #df = run_qartod(df, config)
        #df_wide = payload_to_dataframe(payload)
        
        qc_long, summary = run_qartod(
            df=df_wide,
            qc_dict=qc_config,
            include_aggregate=True,
            verbose=True
            )
        qc_long = add_station_metadata_to_qc(
            qc_long=qc_long,
            location_id=location_id,
            station_name=location["id"],
        )

        qc_filename = f"{location_id}_qartod_long_all.csv"
        qc_path = OUTPUT_DIR / qc_filename

        append_or_replace_timeseries(
        new_df=qc_long,
        output_path=qc_path,
        time_col="time",
        subset=["station_id", "parameter", "time"],
    )
        logging.info("Updated QARTOD long file: %s", qc_path)

        



if __name__ == "__main__":
    main()
