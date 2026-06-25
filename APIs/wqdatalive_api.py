import http.client
import requests
import pandas as pd
import io
import os
import csv
import re

def df_to_rows_and_parameters(df_std):
    """
    Convert WQ Live standardized wide DF to:
      rows_by_ts: dict timestamp_str -> list(values)
      parameters: dict col_index -> {"parameterName": ..., "unitName": ...}
    Timestamp strings match HydroVu: '%Y-%m-%d %H:%M:%S'
    """
    cols = list(df_std.columns)

    parameters = {}
    for i, col in enumerate(cols):
        m = re.match(r"^(.*?)(?:\\s*\\((.*)\\))?$", str(col))
        pname = (m.group(1) or str(col)).strip()
        unit  = (m.group(2) or "").strip()
        parameters[i] = {"parameterName": pname, "unitName": unit}

    rows_by_ts = {}
    for ts, row in df_std.iterrows():
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        rows_by_ts[ts_str] = [row[c] for c in cols]

    return rows_by_ts, parameters


#Get parameter metadata (ID → name)
def get_parameter_lookup(api_key, device_id):
    url = f"https://www.wqdatalive.com/api/v1/devices/{device_id}/parameters"
    params = {"apiKey": api_key}

    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()

    # Build lookup: parameter_id -> parameter_name
    return {
        p["id"]: p["name"]
        for p in data.get("parameters", [])
        if p.get("visible", True)
    }

#Get data for all parameters
def get_parameter_data(api_key, device_id, start, end):
    url = f"https://www.wqdatalive.com/api/v1/devices/{device_id}/parameters/data"
    params = {
        "apiKey": api_key,
        "from": start,  # YYYY-MM-DD HH:MM:SS (UTC)
        "to": end
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()
##Get data for all parameters and all the times (with pagination)  
def get_parameter_data_paginated(api_key, device_id, start, end, parameter_ids=None, verbose=True):
    """
    Fetch all data between start/end by following WQData LIVE paging rules:
    - max ~5000 points per response
    - if info.more == True, repeat with from=info.lastDataPointTimestamp
    """
    url = f"https://www.wqdatalive.com/api/v1/devices/{device_id}/parameters/data"
    all_data = []
    cur_from = start

    while True:
        params = {"apiKey": api_key, "from": cur_from, "to": end}
        if parameter_ids:
            params["parameterIds"] = ",".join(map(str, parameter_ids))

        r = requests.get(url, params=params)
        r.raise_for_status()
        payload = r.json()

        # append this page of records
        page_data = payload.get("data", [])
        all_data.extend(page_data)

        info = payload.get("info", {})  # per API doc: total/count/more/lastDataPointTimestamp [1](https://www.nexsens.com/knowledge-base-v2/software/wqdatalive/user-guide/wqdata-live-data-api-doc)
        #if verbose:
            #print(
                #f"Fetched {info.get('count')} points (total so far={len(all_data)}), "
                #f"more={info.get('more')}, last={info.get('lastDataPointTimestamp')}"
            #)

        # stop if done
        if not info.get("more"):
            break

        # advance start cursor
        last_ts = info.get("lastDataPointTimestamp")
        if not last_ts:
            # safety: if API says more but doesn't provide timestamp, stop to avoid infinite loop
            break

        # add 1 second to avoid re-downloading the same last point on the next request
        last_dt = pd.to_datetime(last_ts, utc=True)
        cur_from = (last_dt + pd.Timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")

    # return in the same structure your downstream code expects
    return {"data": all_data, "info": {"count": len(all_data)}}

#Convert API output to a DataFrame
def build_timeseries_dataframe(raw_data, param_lookup):
    rows = []

    for record in raw_data.get("data", []):
        # record is a dict with keys: "timestamp", "values"
        timestamp = pd.to_datetime(record["timestamp"], utc=True)

        for item in record.get("values", []):
            param_id = item["parameterId"]
            value = item["value"]

            rows.append({
                "datetime": timestamp,
                "parameter": param_lookup.get(param_id, f"param_{param_id}"),
                "value": pd.to_numeric(value, errors="coerce")
            })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Long → wide format
    df = (
        df.pivot(index="datetime", columns="parameter", values="value")
          .sort_index()
    )

    return df


#function to apply mapping
def standardize_columns(df, column_map):
    # keep only columns that exist in the df
    available_map = {
        old: new
        for old, new in column_map.items()
        if old in df.columns
    }
    available_map = {
        old: f'{meta["parameterName"]} ({meta["unitName"]})'
        for old, new in column_map.items()
        if old in df.columns
    }

    df_out = df.rename(columns=available_map)

    # keep columns in mapped order
    ordered_cols = list(available_map.values())
    df_out = df_out[ordered_cols]

    return df_out

station_metadata = {
    4969: {
        "site": "LM2",
        "latitude": 26.600317,
        "longitude": -97.4018,
        "name": "X3-4G-01179"
    },
    4956: {
        "site": "LM1",
        "latitude": 26.69125,
        "longitude": -97.446217,
        "name": "X3-4G-01199"
    }

}





def fetch_station_dataframe(api_key, device_id, start, end, COLUMN_MAP):
    param_lookup = get_parameter_lookup(api_key, device_id)
    raw_data = get_parameter_data_paginated(api_key, device_id, start, end)
    df = build_timeseries_dataframe(raw_data, param_lookup)
    valid_params = set(COLUMN_MAP.keys())
    df = df[[col for col in df.columns if col in valid_params]]
    df_std = standardize_columns(df, COLUMN_MAP)
    #name datetime index correctly
    df_std.index.name = "Date Time"

    return df_std

COLUMN_MAP = {
    "AT500, DO Conc.": {
        "parameterName": "DO",
        "unitName": "mg/L"
    },

    "AT500, DO Sat.": {
        "parameterName": "% Saturation O₂",
        "unitName": "% sat"
    },

    "AT500, DO Partial Pressure": {
        "parameterName": "Partial Pressure O₂",
        "unitName": "psi"
    },

    "AT500, SpC": {
        "parameterName": "Specific Conductivity",
        "unitName": "µS/cm"
    },

    "AT500, Conductivity": {
        "parameterName": "Actual Conductivity",
        "unitName": "µS/cm"
    },

    "AT500, Salinity": {
        "parameterName": "Salinity",
        "unitName": "psu"
    },

    "AT500, Resistivity": {
        "parameterName": "Resistivity",
        "unitName": "Ω-cm"
    },

    "AT500, Water Temp": {
        "parameterName": "Temperature",
        "unitName": "C"
    },

    "AT500, Water Density": {
        "parameterName": "Density",
        "unitName": "g/cm³"
    },

    "AT500, pH": {
        "parameterName": "pH",
        "unitName": "pH"
    },

    "AT500, pH mV": {
        "parameterName": "pH MV",
        "unitName": "mV"
    },

    "AT500, ORP": {
        "parameterName": "ORP",
        "unitName": "mV"
    },

    "AT500_Voltage": {
        "parameterName": "External Voltage",
        "unitName": "V"
    },
}


def get_timeseries_payload(api_key, device_id, start, end, column_map):
    """
    Returns canonical payload for ingestion / CSV generation
    """

    param_lookup = get_parameter_lookup(api_key, device_id)

    raw_data = get_parameter_data_paginated(api_key, device_id, start, end)

    df = build_timeseries_dataframe(raw_data, param_lookup)

    # filter BEFORE mapping
    valid_params = set(column_map.keys())
    df = df[[col for col in df.columns if col in valid_params]]

    df_std = standardize_columns(df, column_map)

    rows_by_ts, parameters = df_to_rows_and_parameters(df_std)

    meta = station_metadata.get(device_id, {})

    return {
        "rows_by_ts": rows_by_ts,
        "parameters": parameters,
        "location_meta": {
            "name": meta.get("site", "Unknown"),
            "id": device_id,
        },
        "latitude": meta.get("latitude"),
        "longitude": meta.get("longitude"),
    }