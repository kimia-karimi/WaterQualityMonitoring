from geopy.distance import geodesic
from datetime import datetime, timedelta
import hydrovu_api 
from coastal.models import Deployment, DataValue, Parameter, Sensor, DeploymentSensor, Station, Instrument
import pytz
from coastal import models, config
from coastal.database.database import db_session
from coastal.util import sonde_utils
import io
import os
import csv
from logging import getLogger
from wdft.log import cloudwatch

import wqdatalive

from coastal.util.at500_timeseries_ingest import ingest_timeseries_rows #utils?

logger = getLogger(__name__)
logger.setLevel(cloudwatch.default_level)
logger.addHandler(cloudwatch.get_file_handler(subdir = 'coastal_data'))
logger.addHandler(cloudwatch.get_console_handler())
# logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

def process_hydrovu(oauth_session, location_id, wdft_station):
    payload = hydrovu_api.get_timeseries_payload(
        oauth_session, location_id
    )

    ingest_timeseries_rows(
        source_label=f"HydroVu{location_id}",
        wdft_station_id=wdft_station,
        instrument_id=654,
        filename="HydroVu Auto",
        comments="HydroVu API ingestion",
        **payload
    )


def process_wqlive(device_id, mapping, start, end):
    payload = wqdatalive.get_timeseries_payload(
        api_key=WQLIVE_API_KEY,
        device_id=device_id,
        start=start,
        end=end,
        column_map=wqdatalive.COLUMN_MAP,
    )

    ingest_timeseries_rows(
        source_label=f"WQLive{device_id}",
        wdft_station_id=mapping["station_id"],
        instrument_id=mapping["instrument_id"],
        filename="WQLive Auto",
        comments="WQ Live API ingestion",
        **payload
    )

WQLIVE_API_KEY = config.WQLIVE_API_KEY
#Need to fix after the serial numbers have been added by Mark
WQLIVE_DEVICES = {
    4956: {"station_id": 123, "instrument_id": 10},
    4969: {"station_id": 124, "instrument_id": 10},
}       

#def retrieve_wqlive_data_for_deployment(start_time=None, end_time=None):
    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
    end_str   = end_time.strftime("%Y-%m-%d %H:%M:%S")

    for device_id, mapping in WQLIVE_DEVICES.items():
        df_std = wqdatalive.fetch_station_dataframe(
            api_key=config.WQLIVE_API_KEY,
            device_id=device_id,
            start=start_str,
            end=end_str,
            COLUMN_MAP=wqdatalive.COLUMN_MAP,
        )  

        rows, parameters = wqdatalive.df_to_rows_and_parameters(df_std)

        meta = wqdatalive.station_metadata.get(device_id, {})
        ingest_timeseries_rows(
            source_label=f"WQLive{device_id}",
            wdft_station_id=mapping["station_id"],
            instrument_id=mapping["instrument_id"],
            location_meta={"name": meta.get("site", "Unknown"), "id": device_id},
            latitude=meta.get("latitude"),
            longitude=meta.get("longitude"),
            rows_by_ts=rows,
            parameters=parameters,
            filename="WQLive Auto",
            comments="WQ Live API ingestion",
        )
if __name__ == "__main__":
    retrieve_hydrovu_data_for_deployment()
    retrieve_wqlive_data_for_deployment()
