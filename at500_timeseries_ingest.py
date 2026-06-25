import io
import csv
from datetime import datetime, timedelta
import pytz

from coastal import models
from coastal.database.database import db_session
from coastal.models import Deployment, Station, Instrument
from coastal.util import sonde_utils


def build_metadata_block(location_meta: dict, latitude, longitude):
    return [
        "Location Properties",
        f'Location Name = {location_meta.get("name", "Unknown")}',
        f'Location ID = {location_meta.get("id", "Unknown")}',
        f'Latitude = {latitude} °',
        f'Longitude = {longitude} °',
        "Time shown in UTC",
        "",
        "",
    ]


def build_columns_from_parameters(parameters: dict):
    # parameters: dict -> {"parameterName": ..., "unitName": ...}
    cols = ["Date Time"]
    for p in parameters.values():
        cols.append(f'{p["parameterName"]} ({p["unitName"]})')
    return cols


def ensure_depth(columns, rows_by_ts: dict, parameters: dict, default_depth_m=1.5):
    has_depth = any("Depth" in p["parameterName"] for p in parameters.values())
    if has_depth:
        return columns, rows_by_ts

    columns = list(columns) + ["Depth (m)"]
    for ts in rows_by_ts:
        rows_by_ts[ts].append(default_depth_m)
    return columns, rows_by_ts


def rows_to_inmemory_csv(metadata_lines, columns, rows_by_ts: dict):
    buff = io.BytesIO()
    text = io.TextIOWrapper(buff, encoding="utf-8", newline="")
    writer = csv.writer(text, quoting=csv.QUOTE_ALL)

    for line in metadata_lines:
        writer.writerow([line])

    writer.writerow(columns)

    for ts in sorted(rows_by_ts.keys()):
        writer.writerow([ts] + rows_by_ts[ts])

    text.flush()
    buff.seek(0)
    return buff


def derive_times(rows_by_ts: dict, tz_name="America/Chicago"):
    first_ts = sorted(rows_by_ts.keys())[0]
    last_ts = sorted(rows_by_ts.keys())[-1]

    # timestamps are written as UTC text; parse then localize/convert
    dt_utc = pytz.UTC.localize(datetime.strptime(first_ts, "%Y-%m-%d %H:%M:%S"))
    tz = pytz.timezone(tz_name)
    deployment_dt = dt_utc.astimezone(tz)

    setup_program = deployment_dt - timedelta(days=1)
    setup_loggstart = deployment_dt
    return first_ts, last_ts, deployment_dt, setup_program, setup_loggstart

def create_deployment(station_id, instrument_id, telemetry_id=None,
                      setup_datetime_loggstart=None, setup_datetime_program=None,
                      deployment_datetime=None, deployment_staff_name=None,
                      deployment_comments=None, deployment_dist_sedtosensor=None,
                      deployment_depth_total=None, retrieval_datetime=None,
                      retrieval_comments=None, retrieval_staff_name=None,
                      retrieval_dist_sedtosensor=None, retrieval_depth_total=None,
                      setup_staff_name=None, setup_notes=None, filename=None):
    
    deployment = models.Deployment()
    
    # Required relationships
    deployment.station = db_session.get(Station, station_id)
    deployment.instrument = db_session.get(Instrument, instrument_id)
    deployment.project = models.Project.query.filter_by(name="datasonde").first()
    deployment.deployment_user =  models.User.query.filter_by(full_name='Kim Karimi').first() #"API response"

    # Optional relationships
    deployment.telemetry = None

    # Setup phase
    deployment.setup_datetime_loggstart = setup_datetime_loggstart
    deployment.setup_datetime_program = setup_datetime_program
    deployment.setup_staff_name = setup_staff_name
    deployment.setup_notes = setup_notes
    deployment.filename = filename

    # Deployment phase
    deployment.deployment_datetime = deployment_datetime
    deployment.deployment_staff_name = deployment_staff_name
    deployment.deployment_comments = deployment_comments
    deployment.deployment_dist_sedtosensor = 0.5  # Example default
    deployment.deployment_depth_total =  2.0  # Example default

    # Retrieval phase
    deployment.retrieval_datetime = retrieval_datetime
    deployment.retrieval_comments = retrieval_comments
    deployment.retrieval_staff_name = retrieval_staff_name
    deployment.retrieval_dist_sedtosensor = 0.5  # Example default
    deployment.retrieval_depth_total = 2.0  # Example default

    # Mark as loaded if you're ingesting data via API
    deployment.file_loaded = True
    try:
        db_session.add(deployment)
        db_session.commit()
        return deployment
    except Exception:
        db_session.rollback()
        raise
        
def attach_deployment_sensors(deployment):
    sensors = models.Sensor.query.filter_by(instrument_id=deployment.instrument_id).all()
    for sens in sensors:
        db_session.add(models.DeploymentSensor(sensor=sens, deployment=deployment))
    db_session.commit()


def ingest_timeseries_rows(
    *,
    source_label: str,
    wdft_station_id: int,
    instrument_id: int,
    location_meta: dict,
    latitude,
    longitude,
    rows_by_ts: dict,
    parameters: dict,
    filename: str,
    comments: str,
    default_depth_m=1.5,
):
    """
    The one reusable "post API" ingestion pipeline:
      rows/parameters -> metadata/depth -> in-memory CSV -> create deployment -> sonde3 upload -> attach sensors
    """
    if not rows_by_ts:
        logger.info(f"No data for {source_label}")
        return None

    metadata_lines = build_metadata_block(location_meta, latitude, longitude)
    columns = build_columns_from_parameters(parameters)
    columns, rows_by_ts = ensure_depth(columns, rows_by_ts, parameters, default_depth_m=default_depth_m)
    in_memory_csv = rows_to_inmemory_csv(metadata_lines, columns, rows_by_ts)

    first_ts, last_ts, dep_dt, setup_prog, setup_logg = derive_times(rows_by_ts)

    deployment = None
    try:
        deployment = create_deployment(
            station_id=wdft_station_id,
            instrument_id=instrument_id,
            deployment_datetime=dep_dt,
            setup_datetime_loggstart=setup_logg,
            setup_datetime_program=setup_prog,
            filename=filename,
            deployment_comments=comments,
        )

        observation_depth = deployment.deployment_depth_total - deployment.deployment_dist_sedtosensor

        # Uses the existing ingestion implementation (sonde3 + QC + upsert) [1](https://loop.cloud.microsoft/p/eyJ1IjoiaHR0cHM6Ly90d2RiLnNoYXJlcG9pbnQuY29tL2NvbnRlbnRzdG9yYWdlL0NTUF80ODljOGVkNC01MDRhLTQ0OGYtOTliOC0wNGFhNmJkNTM1NzE%2FbmF2PWN6MGxNa1pqYjI1MFpXNTBjM1J2Y21GblpTVXlSa05UVUNVMVJqUTRPV000WldRMEpUSkVOVEEwWVNVeVJEUTBPR1lsTWtRNU9XSTRKVEpFTURSaFlUWmlaRFV6TlRjeEptUTlZaVV5TVRGSk5tTlRSWEJSYWpCVFduVkJVM0ZoT1ZVeFkyRTVlblV3V0RaTWFHeEVjMEpEY1VKaVIxWk5TemQwYm1oME9UbEROQ1UxUmxOd2NqUnVkV051TkRONk15Wm1QVEF4UWtkTFYxWkxSa2xCVlVOYVUwRkVWMFphUjBsUVNrNUtORUZIV2xwRlVWSW1ZejBsTWtZIn0%3D)
        sonde_utils.sonde_upload_helper_auto(
            deployment,
            in_memory_csv,
            vertical_offset=deployment.deployment_dist_sedtosensor,
            observation_depth=observation_depth,
            twdbparams=True,
        )

        attach_deployment_sensors(deployment)
        return deployment

    except Exception as e:
        logger.error(f"{source_label} ingestion failed for station {wdft_station_id}: {e}",exc_info=True)
        db_session.rollback()
        if deployment is not None:
            db_session.query(Deployment).filter(
                Deployment.id == deployment.id,
                Deployment.station_id == wdft_station_id,
            ).delete()
            db_session.commit()
        raise None
    
