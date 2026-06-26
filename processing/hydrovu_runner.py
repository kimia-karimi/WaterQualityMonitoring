#from APIs.hydrovu_api import hydrovu_api
from processing.payload_to_csv import rows_to_csv_payload
from APIs.hydrovu_api import get_timeseries_payload
def run_hydrovu_for_targets(session, targets, start=None, end=None):
    results = []

    for site in targets:
        location_id = site["id"]

        print(f"Processing HydroVu location {location_id}")

        payload = get_timeseries_payload(
            session,
            location_id=site["id"],
            start_time=start,
            end_time=end
        )

        results.append({
            "id": site["id"],
            "payload": payload
        })

    return results
