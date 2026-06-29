# WaterQualityMonitoring
Sonde Data retrieval

# HydroVu Data Retrieval (CSV Generator)

This repository provides a clean, reproducible pipeline to retrieve time series data from the HydroVu API and export it into a CSV format compatible with WDfT ingestion workflows.

---

## Features

- Retrieve data for:
  - All HydroVu stations (`-all`)
  - Specific stations (`-site`)
- Optional time filtering (`-start`, `-end`)
- Outputs standardized CSV (no database dependency)
- Efficient API usage 
---



## Run for all stations:
python -m scripts.run_hydrovu -all

## Run for specific stations:
python -m scripts.run_hydrovu -site 6387509350170624 5106941840719872

- with time filtering:
python -m scripts.run_hydrovu -site 6387509350170624 5106941840719872 -start 2026-01-01 -end 2026-06-02
