"""
Build Power BI-ready import tables from QARTOD long CSV outputs.

Inputs:
    *_qartod_long_all.csv

Outputs:
    powerbi/fact_qartod_long.csv
    powerbi/fact_qartod_daily_summary.csv
    powerbi/dim_station.csv
    powerbi/dim_parameter.csv
    powerbi/dim_qc_flag.csv

Example:
    python -m scripts.powerbi_export

Optional:
    python -m scripts.powerbi_export --input-dir . --output-dir powerbi
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


DEFAULT_QC_FLAG_LOOKUP = pd.DataFrame(
    [
        {
            "qc_code": 1,
            "qc_label": "pass",
            "qc_category": "good",
            "sort_order": 1,
        },
        {
            "qc_code": 2,
            "qc_label": "not_evaluated",
            "qc_category": "neutral",
            "sort_order": 2,
        },
        {
            "qc_code": 3,
            "qc_label": "suspect",
            "qc_category": "warning",
            "sort_order": 3,
        },
        {
            "qc_code": 4,
            "qc_label": "fail",
            "qc_category": "critical",
            "sort_order": 4,
        },
    ]
)


QC_TEST_COLUMNS = [
    "gross_range_test_qc",
    "spike_test_qc",
    "rate_of_change_test_qc",
    "flat_line_test_qc",
]


REQUIRED_COLUMNS = [
    "station_id",
    "station_name",
    "time",
    "parameter",
    "value",
    "aggregate_qc",
]


def find_qartod_files(input_dir: Path) -> list:
   """
    Find station-level QARTOD long files.

    Expected pattern:
        *_qartod_long_all.csv
    """
   files = sorted(input_dir.glob("*_qartod_long_all.csv"))

   if not files:
      logging.warning(
            "No QARTOD long files found in %s using pattern *_qartod_long_all.csv",
            input_dir,
        )
   return files


def read_qartod_file(path: Path) -> pd.DataFrame:
    """
    Read one QARTOD long CSV and normalize columns/types.
    """

    logging.info("Reading %s", path)

    df = pd.read_csv(path)

    if df.empty:
        logging.warning("File is empty: %s", path)
        return pd.DataFrame()

    missing_required = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_required:
        raise ValueError(
            f"{path} is missing required columns: {missing_required}"
        )

    # Normalize names
    df.columns = [str(c).strip() for c in df.columns]

    # Normalize time to UTC-aware datetime, then store as ISO-like string later
    df["time"] = pd.to_datetime(
        df["time"],
        utc=True,
        errors="coerce",
    )

    df = df.dropna(subset=["time"])

    # Standardize station/parameter text
    df["station_name"] = df["station_name"].astype(str).str.strip()
    df["parameter"] = df["parameter"].astype(str).str.strip()

    # Numeric conversions
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["aggregate_qc"] = pd.to_numeric(df["aggregate_qc"], errors="coerce").astype("Int64")

    for col in QC_TEST_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        else:
            # Keep a stable schema even if a test was not present.
            df[col] = pd.Series([pd.NA] * len(df), dtype="Int64")

    # Optional provenance columns if your pipeline adds them later
    optional_cols = [
        "source_hydrovu_id",
        "source_hydrovu_name",
        "source_hydrovu_description",
    ]

    for col in optional_cols:
        if col not in df.columns:
            df[col] = pd.NA

    # Create useful date fields for Power BI slicing
    df["date"] = df["time"].dt.date.astype(str)
    df["year"] = df["time"].dt.year
    df["month"] = df["time"].dt.month
    df["day"] = df["time"].dt.day
    df["hour"] = df["time"].dt.hour

    return df


def build_fact_qartod_long(input_dir: Path) -> pd.DataFrame:
    """
    Combine all station QARTOD long files into one fact table.
    """

    files = find_qartod_files(input_dir)

    frames = []

    for path in files:
        df = read_qartod_file(path)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    fact = pd.concat(frames, ignore_index=True)

    # Remove exact duplicates across reruns/appends
    dedupe_cols = [
        "station_id",
        "station_name",
        "time",
        "parameter",
    ]

    fact = fact.drop_duplicates(
        subset=dedupe_cols,
        keep="last",
    )

    fact = fact.sort_values(
        ["station_name", "parameter", "time"]
    ).reset_index(drop=True)

    # Write time as stable string for CSV/Power BI
    fact["time"] = fact["time"].dt.strftime("%Y-%m-%d %H:%M:%S")

    preferred_order = [
        "station_id",
        "station_name",
        "time",
        "date",
        "year",
        "month",
        "day",
        "hour",
        "parameter",
        "value",
        "gross_range_test_qc",
        "spike_test_qc",
        "rate_of_change_test_qc",
        "flat_line_test_qc",
        "aggregate_qc",
        "source_hydrovu_id",
        "source_hydrovu_name",
        "source_hydrovu_description",
    ]

    existing_order = [c for c in preferred_order if c in fact.columns]
    other_cols = [c for c in fact.columns if c not in existing_order]

    return fact[existing_order + other_cols]


def build_dim_station(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Build station dimension table.
    """

    if fact.empty:
        return pd.DataFrame(
            columns=[
                "station_name",
                "station_id",
                "source_hydrovu_id",
                "source_hydrovu_name",
            ]
        )

    cols = [
        "station_name",
        "station_id",
        "source_hydrovu_id",
        "source_hydrovu_name",
    ]

    available = [c for c in cols if c in fact.columns]

    dim = (
        fact[available]
        .drop_duplicates()
        .sort_values(["station_name"])
        .reset_index(drop=True)
    )

    return dim


def split_parameter_unit(parameter: str) -> tuple[str, str]:
    """
    Split labels like:
        Temperature (C)
        Salinity (psu)

    into:
        parameter_base, unit
    """

    text = str(parameter).strip()

    if text.endswith(")") and "(" in text:
        base = text[: text.rfind("(")].strip()
        unit = text[text.rfind("(") + 1 : -1].strip()
        return base, unit

    return text, ""


def build_dim_parameter(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Build parameter dimension table.
    """

    if fact.empty:
        return pd.DataFrame(
            columns=[
                "parameter",
                "parameter_base",
                "unit",
                "parameter_group",
            ]
        )

    dim = (
        fact[["parameter"]]
        .drop_duplicates()
        .sort_values("parameter")
        .reset_index(drop=True)
    )

    parsed = dim["parameter"].apply(split_parameter_unit)

    dim["parameter_base"] = parsed.apply(lambda x: x[0])
    dim["unit"] = parsed.apply(lambda x: x[1])

    # Simple grouping. You can refine later with definitions.csv.
    dim["parameter_group"] = dim["parameter_base"].map(infer_parameter_group)

    return dim


def infer_parameter_group(parameter_base: str) -> str:
    """
    Lightweight grouping for dashboard slicers.

    Keep this simple for the first Power BI version.
    Later, replace with definitions.csv or definitions_semantic.csv.
    """

    p = str(parameter_base).lower()

    if "temp" in p:
        return "Temperature"

    if "salinity" in p:
        return "Salinity"

    if "do" in p or "oxygen" in p:
        return "Dissolved Oxygen"

    if "ph" in p:
        return "pH"

    if "conductivity" in p or "cond" in p:
        return "Conductivity"

    if "chl" in p or "chlorophyll" in p:
        return "Chlorophyll"

    if "orp" in p:
        return "ORP"

    return "Other"


def build_daily_summary(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Build one-row-per-station/parameter/day daily QC summary.

    This table is useful for fast Power BI cards and trend visuals.
    """

    if fact.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "station_name",
                "parameter",
                "total_records",
                "pass_count",
                "not_evaluated_count",
                "suspect_count",
                "fail_count",
                "latest_time",
            ]
        )

    df = fact.copy()

    df["aggregate_qc"] = pd.to_numeric(df["aggregate_qc"], errors="coerce")

    grouped = (
        df.groupby(["date", "station_name", "parameter"], dropna=False)
        .agg(
            total_records=("aggregate_qc", "size"),
            pass_count=("aggregate_qc", lambda s: (s == 1).sum()),
            not_evaluated_count=("aggregate_qc", lambda s: (s == 2).sum()),
            suspect_count=("aggregate_qc", lambda s: (s == 3).sum()),
            fail_count=("aggregate_qc", lambda s: (s == 4).sum()),
            latest_time=("time", "max"),
        )
        .reset_index()
    )

    grouped["fail_percent"] = grouped["fail_count"] / grouped["total_records"]
    grouped["suspect_percent"] = grouped["suspect_count"] / grouped["total_records"]
    grouped["pass_percent"] = grouped["pass_count"] / grouped["total_records"]

    return grouped.sort_values(
        ["station_name", "parameter", "date"]
    ).reset_index(drop=True)


def write_csv(df: pd.DataFrame, path: Path) -> None:
    """
    Write CSV, creating parent directory if needed.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logging.info("Wrote %s (%s rows)", path, len(df))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Power BI-ready CSV tables from QARTOD long outputs."
    )

    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("."),
        help="Directory containing *_qartod_long_all.csv files.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("powerbi"),
        help="Directory where Power BI import CSVs will be written.",
    )

    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir

    fact = build_fact_qartod_long(input_dir)

    if fact.empty:
        logging.warning("No QARTOD data found. No Power BI files created.")
        return

    dim_station = build_dim_station(fact)
    dim_parameter = build_dim_parameter(fact)
    dim_qc_flag = DEFAULT_QC_FLAG_LOOKUP.copy()
    daily_summary = build_daily_summary(fact)

    write_csv(fact, output_dir / "fact_qartod_long.csv")
    write_csv(daily_summary, output_dir / "fact_qartod_daily_summary.csv")
    write_csv(dim_station, output_dir / "dim_station.csv")
    write_csv(dim_parameter, output_dir / "dim_parameter.csv")
    write_csv(dim_qc_flag, output_dir / "dim_qc_flag.csv")

    logging.info("Power BI export complete.")


if __name__ == "__main__":
    main()
