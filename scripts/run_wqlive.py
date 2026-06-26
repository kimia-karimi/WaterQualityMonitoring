import wqdatalive_api
from processing.payload_to_csv import rows_to_csv_payload
from config import definitions  # optional later

API_KEY = "1d6f5f7e2560446e96e8465b03ebf342"

payload = wqdatalive_api.get_timeseries_payload(
    api_key=API_KEY,
    device_id=4956,
    start="2026-04-09 00:00:00",
    end="2026-05-18 23:59:59",
    column_map=wqdatalive_api.COLUMN_MAP
)

csv_buffer = rows_to_csv_payload(payload)

print(csv_buffer.getvalue().decode("utf-8"))
