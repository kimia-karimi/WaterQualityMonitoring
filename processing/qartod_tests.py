

import yaml
import numpy as np
import pandas as pd

from ioos_qc.qartod import (gross_range_test,spike_test,rate_of_change_test,flat_line_test)


# QARTOD flag meanings
GOOD = 1
UNKNOWN = 2
SUSPECT = 3
FAIL = 4
MISSING = 9


def _to_uint8_flags(flags, missing_mask=None):
    """
    Convert IOOS QC output to clean uint8 flags.
    Handles masked arrays and missing input values.
    """

    if np.ma.isMaskedArray(flags):
        out = np.ma.filled(flags, MISSING).astype("uint8")
    else:
        out = np.asarray(flags).astype("uint8")

    if missing_mask is not None:
        out[missing_mask] = MISSING

    return out


def _datetime_index_to_epoch_seconds(index):
    """
    Convert pandas DatetimeIndex to seconds since epoch.
    Needed for rate_of_change_test and flat_line_test.
    """

    idx = pd.to_datetime(index)
    return (idx.astype("int64") // 10**9).to_numpy(dtype=float)


def _manufacturer_range_test(values, fail_span):
    """
    Simple manufacturer range test.

    GOOD if inside fail_span.
    FAIL if outside fail_span.
    MISSING if NaN.
    """

    values = np.asarray(values, dtype=float)
    flags = np.full(values.shape, GOOD, dtype="uint8")

    missing = ~np.isfinite(values)
    flags[missing] = MISSING

    low, high = fail_span
    fail = (values < low) | (values > high)
    flags[fail & ~missing] = FAIL

    return flags


def _aggregate_flags(test_flag_arrays, values):
    """
    Create one aggregate flag per parameter.

    Logic:
      - if original value is missing -> MISSING
      - if any test FAIL -> FAIL
      - else if any test SUSPECT -> SUSPECT
      - else if any test UNKNOWN -> UNKNOWN
      - else GOOD
    """

    values = np.asarray(values, dtype=float)
    missing = ~np.isfinite(values)

    if not test_flag_arrays:
        out = np.full(values.shape, UNKNOWN, dtype="uint8")
        out[missing] = MISSING
        return out

    flag_matrix = np.vstack(test_flag_arrays)

    out = np.full(values.shape, GOOD, dtype="uint8")

    out[np.any(flag_matrix == UNKNOWN, axis=0)] = UNKNOWN
    out[np.any(flag_matrix == SUSPECT, axis=0)] = SUSPECT
    out[np.any(flag_matrix == FAIL, axis=0)] = FAIL

    out[missing] = MISSING

    return out


def run_qartod(df, qc_dict, include_aggregate=True, verbose=True):
    """
    Run QARTOD tests from qc_config.yml on all matching dataframe columns.

    Parameters
    ----------
    df : pandas.DataFrame
        Time-indexed dataframe. Index must be datetime-like.

    qc_dict : dict
        Parsed YAML dictionary from yaml.safe_load().

    include_aggregate : bool
        If True, creates one aggregate QC column per parameter.

    verbose : bool
        If True, prints missing columns and skipped tests.

    Returns
    -------
    df_qc : pandas.DataFrame
        Original dataframe plus QC flag columns.

    summary : dict
        Information about what ran, what was missing, and what failed.
    """

    df_qc = df.copy()

    # Make sure index is datetime
    df_qc.index = pd.to_datetime(df_qc.index)

    # Numeric time input for time-dependent tests
    tinp = _datetime_index_to_epoch_seconds(df_qc.index)

    streams = qc_dict["contexts"][0]["streams"]
    long_results = []
    summary = {
        "ran": [],
        "missing_columns": [],
        "skipped_tests": [],
        "failed_tests": [],
    }

    for parameter, stream_cfg in streams.items():

        if parameter not in df_qc.columns:
            summary["missing_columns"].append(parameter)

            if verbose:
                print(f"Missing dataframe column, skipping: {parameter}")

            continue

        tests = stream_cfg.get("qartod", {})

        # Convert data to numeric
        values = pd.to_numeric(df_qc[parameter], errors="coerce").to_numpy(dtype=float)
        missing_mask = ~np.isfinite(values)

        parameter_test_flags = []

        if verbose:
            print(f"\nRunning QARTOD for: {parameter}")

        # one dataframe per parameter
        param_result = pd.DataFrame({
            "time": df_qc.index,
            "parameter": parameter,
            "value": values,
        })

        # -------------------------------------------------
        # 1. Gross range test
        # -------------------------------------------------
        if "gross_range_test" in tests:

            gr = tests["gross_range_test"]

            try:
                flags = gross_range_test(
                    inp=values,
                    suspect_span=tuple(gr["suspect_span"]),
                    fail_span=tuple(gr["fail_span"]),
                )

                flags = _to_uint8_flags(flags, missing_mask)

                col = f"{parameter}_gross_range_test_qc"
                #df_qc[col] = flags
                param_result["gross_range_test_qc"] = flags

                parameter_test_flags.append(flags)

                summary["ran"].append((parameter, "gross_range_test"))

            except Exception as exc:
                summary["failed_tests"].append(
                    (parameter, "gross_range_test", repr(exc))
                )
                param_result["gross_range_test_qc"] = UNKNOWN

        # -------------------------------------------------
        # 2. Manufacturer range test
        # Optional custom test, if added to YAML later
        # -------------------------------------------------
        if "manufacturer_range_test" in tests:

            mr = tests["manufacturer_range_test"]

            try:
                flags = _manufacturer_range_test(
                    values=values,
                    fail_span=tuple(mr["fail_span"]),
                )

                col = f"{parameter}_manufacturer_range_test_qc"
                param_result["manufacturer_range_test_qc"] = flags
                df_qc[col] = flags
                parameter_test_flags.append(flags)

                summary["ran"].append((parameter, "manufacturer_range_test"))

            except Exception as exc:
                summary["failed_tests"].append(
                    (parameter, "manufacturer_range_test", repr(exc))
                )
                param_result["manufacturer_range_test_qc"] = UNKNOWN

        # -------------------------------------------------
        # 3. Spike test
        # -------------------------------------------------
        if "spike_test" in tests:

            sp = tests["spike_test"]

            try:
                flags = spike_test(
                    inp=values,
                    suspect_threshold=sp["suspect_threshold"],
                    fail_threshold=sp["fail_threshold"],
                )

                flags = _to_uint8_flags(flags, missing_mask)

                col = f"{parameter}_spike_test_qc"
                df_qc[col] = flags
                param_result["spike_test_qc"] = flags
                parameter_test_flags.append(flags)

                summary["ran"].append((parameter, "spike_test"))

            except Exception as exc:
                summary["failed_tests"].append(
                    (parameter, "spike_test", repr(exc))
                )
                param_result["spike_test_qc"] = UNKNOWN
        # -------------------------------------------------
        # 4. Rate of change test
        # -------------------------------------------------
        if "rate_of_change_test" in tests:

            roc = tests["rate_of_change_test"]

            try:
                flags = rate_of_change_test(
                    inp=values,
                    tinp=tinp,
                    threshold=roc["threshold"],
                )

                flags = _to_uint8_flags(flags, missing_mask)

                col = f"{parameter}_rate_of_change_test_qc"
                #df_qc[col] = flags
                param_result["rate_of_change_test_qc"] = flags
                parameter_test_flags.append(flags)

                summary["ran"].append((parameter, "rate_of_change_test"))
                

            except Exception as exc:
                summary["failed_tests"].append(
                    (parameter, "rate_of_change_test", repr(exc))
                )
                param_result["rate_of_change_test_qc"] = UNKNOWN

        # -------------------------------------------------
        # 5. Flat line test
        # -------------------------------------------------
        if "flat_line_test" in tests:

            fl = tests["flat_line_test"]

            try:
                flags = flat_line_test(
                    inp=values,
                    tinp=tinp,
                    tolerance=fl["tolerance"],
                    suspect_threshold=fl["suspect_threshold"],
                    fail_threshold=fl["fail_threshold"],
                )

                flags = _to_uint8_flags(flags, missing_mask)

                #col = f"{parameter}_flat_line_test_qc"
                #df_qc[col] = flags
                
                param_result["flat_line_test_qc"] = flags

                parameter_test_flags.append(flags)

                summary["ran"].append((parameter, "flat_line_test"))

            except Exception as exc:
                summary["failed_tests"].append(
                    (parameter, "flat_line_test", repr(exc))
                )
                
                param_result["flat_line_test_qc"] = UNKNOWN


        # -------------------------------------------------
        # 6. Aggregate flag
        # -------------------------------------------------
        if include_aggregate:

            aggregate_flags = _aggregate_flags(
                test_flag_arrays=parameter_test_flags,
                values=values,
            )

            param_result["aggregate_qc"] = aggregate_flags
        long_results.append(param_result)

    if long_results:
        qc_long = pd.concat(long_results, ignore_index=True)
    else:
        qc_long = pd.DataFrame(
            columns=[
                "time",
                "parameter",
                "value",
                "gross_range_test_qc",
                "manufacturer_range_test_qc",
                "spike_test_qc",
                "rate_of_change_test_qc",
                "flat_line_test_qc",
                "aggregate_qc",
            ]
        )


    return qc_long, summary



with open(r"T:\CoastalScience\Users\KKarimi\Git\WaterQualityMonitoring\config\qc_config.yml", "r", encoding="utf-8") as f:
    qc_dict = yaml.safe_load(f)
print(qc_dict["contexts"][0]["streams"]["Temperature (C)"]["qartod"])

df = (
    pd.read_csv(r"C:\Users\kkarimi\OneDrive - The State of Texas, acting by and through the Department of Information Resources-5173968-TX-WDB\HydroVU\Output\Corpus_Christi_Bay_Buoy_5094472985673728.csv", parse_dates=["Date Time"])
      .rename(columns={
          "Date Time":"time",
          "Specific Conductivity (ÂµS/cm)":"Specific Conductivity (µS/cm)",
          "Actual Conductivity (ÂµS/cm)":"Actual Conductivity (µS/cm)",
          "Chl-a Fluorescence (RFU)":"Chl-a Fluorescence (RFU)"
          
      })
      index= False 
      
)

df.index = pd.to_datetime(df.index)

df.columns = df.columns.str.strip()


# Run all configured QARTOD tests
df_qc, summary = run_qartod(
    df=df,
    qc_dict=qc_dict,
    include_aggregate=True,
    verbose=True,
)

# Save output
df_qc.to_csv(r"T:\CoastalScience\Users\KKarimi\Git\WaterQualityMonitoring\Corpus_Christi_Bay_Buoy_5094472985673728_qartod.csv",index=False)


# Print run summary
print("\nTests successfully run:")
for item in summary["ran"]:
    print(item)

print("\nMissing columns:")
print(summary["missing_columns"])

print("\nFailed tests:")
print(summary["failed_tests"])

print("\nOutput preview:")
print(df_qc.head())
