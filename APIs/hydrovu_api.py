from datetime import datetime, timezone
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

TOKEN_URL = "https://www.hydrovu.com/public-api/oauth/token"
BASE_URL = "https://www.hydrovu.com/public-api/v1"
client_id= "TWDB"
client_secret= "65af7106c92646bf9249d4e7d92f8f61"

def get_oauth_session(client_id):
    client = BackendApplicationClient(client_id=client_id)
    return OAuth2Session(client=client)

def get_access_token(oauth_session, client_id, client_secret):
    return oauth_session.fetch_token(token_url=TOKEN_URL, client_id=client_id, client_secret=client_secret)

def fetch_all_locations(oauth_session):
    locations = []
    page = None
    while True:
        response = oauth_session.get(f"{BASE_URL}/locations/list", headers={'X-ISI-Start-Page': page} if page else {})
        locations.extend(response.json())
        page = response.headers.get('X-ISI-Next-Page')
        if not page:
            break
    return locations

session= get_oauth_session(client_id)
session= get_access_token(session, client_id, client_secret)
print(fetch_all_locations(session))
#def fetch_location_info(oauth_session, location_id):
    #response = oauth_session.get(f"{BASE_URL}/locations/{location_id}")
    #return response.json()

def fetch_location_info(oauth_session, station_id):
    # Get all locations
    all_locations = fetch_all_locations(oauth_session)
    
    # Search for the location with the matching 'id'
    for location in all_locations:
        if location.get('id') == station_id:
            return location
    
    # If no match is found
    return None


def fetch_friendly_names(oauth_session):
    return oauth_session.get(f"{BASE_URL}/sispec/friendlynames").json()


def fetch_all_data_for_location(oauth_session, location_id, start_time=None, end_time=None):
    merged_data = {'parameters': []}
    page = None    
    #Convert ISO 8601 to epoch if needed
    if isinstance(start_time, str):
        start_time = int(datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    if isinstance(end_time, str):
        end_time = int(datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
    while True:
        params = {}
        if start_time: params['startTime'] = str(start_time)
        if end_time: params['endTime'] = str(end_time)
        headers = {'X-ISI-Start-Page': page} if page else {}
        response = oauth_session.get(f"{BASE_URL}/locations/{location_id}/data", params=params, headers=headers)#, timeout=(10, 120))
        data = response.json()
        if 'parameters' in data:
            merged_data['parameters'].extend(data['parameters'])
        page = response.headers.get('X-ISI-Next-Page')
        if not page:
            break
    return merged_data

def flatten_into_rows(location_info, friendly_names):
    parameter_col_index = {}
    index_counter = 0
    for parameter in location_info['parameters']:
        if parameter['parameterId'] not in parameter_col_index:
            parameter_name = friendly_names['parameters'].get(parameter['parameterId'], parameter['parameterId'])
            unit_name = friendly_names['units'].get(parameter['unitId'], parameter['unitId'])
            parameter_col_index[parameter['parameterId']] = {
                'parameterName': parameter_name,
                'unitName': unit_name,
                'columnIndex': index_counter,
            }
            index_counter += 1

    data_rows_by_timestamp = {}
    for parameter in location_info['parameters']:
        parameter_id = parameter['parameterId']
        for datum in parameter['readings']:
            timestamp = datum['timestamp']
            if timestamp is None:
                continue
            dt_str = datetime.utcfromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
            if dt_str not in data_rows_by_timestamp:
                data_rows_by_timestamp[dt_str] = [None for _ in parameter_col_index]
            col_info = parameter_col_index[parameter_id]
            data_rows_by_timestamp[dt_str][col_info['columnIndex']] = datum['value']

    return data_rows_by_timestamp, parameter_col_index


def get_timeseries_payload(oauth_session, location_id, start_time=None, end_time=None):
    """
    Returns canonical payload for ingestion / CSV generation
    """

    location_data = fetch_all_data_for_location(
        oauth_session, location_id, start_time, end_time
    )

    friendly_names = fetch_friendly_names(oauth_session)

    rows_by_ts, parameters = flatten_into_rows(location_data, friendly_names)

    location_meta = fetch_location_info(oauth_session, location_id)

    latitude = location_meta.get("gps", {}).get("latitude")
    longitude = location_meta.get("gps", {}).get("longitude")

    return {
        "rows_by_ts": rows_by_ts,
        "parameters": parameters,
        "location_meta": {
            "name": location_meta.get("name", "Unknown"),
            "id": location_id,
        },
        "latitude": latitude,
        "longitude": longitude,
    }
