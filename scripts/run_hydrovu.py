import argparse
#from config.hydrovu_targets import HYDROVU_TARGETS
from processing.payload_to_csv import rows_to_csv_payload
#from processing.hydrovu_runner import run_hydrovu_for_targets
from APIs.hydrovu_api import get_oauth_session
from APIs.hydrovu_api import get_timeseries_payload
from APIs.hydrovu_api import get_access_token
from APIs.hydrovu_api import fetch_friendly_names

from APIs.hydrovu_api import fetch_all_locations

def get_all_locations(session):
    return fetch_all_locations(session)


def filter_locations(all_locs, ids):
    lookup = {loc["id"]: loc for loc in all_locs}
    return [lookup[i] for i in ids if i in lookup]



def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("-all", action="store_true", help="Process all HydroVu locations")
    parser.add_argument("-site", nargs="+", type=int, help="Specify location IDs")

    parser.add_argument("-start", type=str, required=True, help="Start time in ISO format (e.g., 2025-01-01T00:00:00Z)")
    parser.add_argument("-end", type=str, required=True, help="End time in ISO format (e.g., 2025-01-02T00:00:00Z)")
    args = parser.parse_args()
    CLIENT_ID= "TWDB"
    CLIENT_SECRET= "65af7106c92646bf9249d4e7d92f8f61"
    oauth = get_oauth_session(CLIENT_ID)
    get_access_token(oauth, CLIENT_ID, CLIENT_SECRET)
    friendly_names = fetch_friendly_names(oauth)
    if args.all:
        print("Running for ALL locations...")
        locations = get_all_locations(oauth)

    elif args.site:
        print(f"Running for specified sites: {args.site}")
        all_locs = get_all_locations(oauth)
        locations = filter_locations(all_locs, args.site)

    else:
        raise ValueError("Must specify -all or -site")
    #Loop through selected locations and run the HydroVu processing
    for loc in locations:
        location_id = loc["id"]
        print(f"\n--- Processing {location_id} ---")
        
        payload = get_timeseries_payload(
                oauth,
                location_id=location_id, 
                start_time=start,   # or "2025-01-01T00:00:00Z"
                end_time=end,
            meta={
                "name": loc.get("name"),
                "id": location_id,
                "latitude": loc.get("gps", {}).get("latitude"),
                "longitude": loc.get("gps", {}).get("longitude"),
            }, friendly_names=friendly_names 

            )
        csv_buffer = rows_to_csv_payload(payload, default_depth_m=None)

        with open(f"hydrovu_{loc['id']}.csv", "wb") as f:
                f.write(csv_buffer.getvalue())


    


if __name__ == "__main__":
    main()



