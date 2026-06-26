from APIs import hydrovu_api
from processing.payload_to_csv import rows_to_csv_payload
CLIENT_ID= "TWDB"
CLIENT_SECRET= "65af7106c92646bf9249d4e7d92f8f61"
oauth = hydrovu_api.get_oauth_session(CLIENT_ID)
hydrovu_api.get_access_token(oauth, CLIENT_ID, CLIENT_SECRET)

results = run_hydrovu_for_targets(session, HYDROVU_TARGETS)

# Print / save
for r in results:
    print(f"\n--- Station {r['id']} ---\n")
    print(r["csv"].getvalue().decode("utf-8"))


for site in HYDROVU_TARGETS:
    payload = hydrovu_api.get_timeseries_payload(
        session,
        location_id=site["id"], 
        start_time=None,   # or "2025-01-01T00:00:00Z"
        end_time=None
    )

csv_buffer = rows_to_csv_payload(payload, default_depth_m=1.5)

print(csv_buffer.getvalue().decode("utf-8"))



