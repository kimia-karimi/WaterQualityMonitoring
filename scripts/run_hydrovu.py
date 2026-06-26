import hydrovu_api
from processing.payload_to_csv import rows_to_csv_payload

oauth = hydrovu_api.get_oauth_session(CLIENT_ID)
hydrovu_api.get_access_token(oauth, CLIENT_ID, CLIENT_SECRET)


for site in HYDROVU_TARGETS:
    payload = hydrovu_api.get_timeseries_payload(
        session,
        location_id=site["id"]
    )

csv_buffer = rows_to_csv_payload(payload, default_depth_m=1.5)

print(csv_buffer.getvalue().decode("utf-8"))



