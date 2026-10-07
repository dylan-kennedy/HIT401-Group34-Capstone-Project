"""
check_downloaded_data.py - data-quality report for the files in data/climate/.

This is a REPORT, not a unit test: it reads the real downloaded files and prints a table,
so the numbers can be quoted in the write-up. Run it after any download:

    ~/venvs/hit401_climate/bin/python -B climate/tests/check_downloaded_data.py

Checks that must pass (exit code 1 if any fails):
  * both experiments present and readable for every run
  * no gap or overlap in the joined monthly series
  * no NaN rainfall
  * the reference (1985-2014) and future (2070-2099) windows are complete
  * the model's own calendar is used for the mm conversion (February is 28 days on
    a noleap calendar even in a leap year)

Reported as INFO, not failures:
  * very large single months. Models produce extremes well above anything observed:
    ACCESS-CM2 reaches 2382 mm in one month at Darwin. That is the model's own output,
    one month in 3012, and is left exactly as published.
  * tiny negative values. EC-Earth3 reports values around -1e-18 mm, which is
    floating-point noise from a spectral model and is physically zero.
"""

import sys
from pathlib import Path

import pandas as pd
import xarray as xr

# climate_models.py and download_cmip6_pr.py live one level up, in climate/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import climate_models as cm

# Above this, a single month is reported as an INFO line rather than a failure.
LARGE_MONTH_MM = 2000
# Negative values smaller than this in size are treated as floating-point noise.
NEGATIVE_NOISE_MM = 1e-6


def main():
    rows, failures, notes = [], [], []

    for run in cm.REGISTRY:
        for location in cm.LOCATIONS:
            label = run["label"]
            usable, why = cm.check_run(label, location)
            if not usable:
                failures.append(f"{label} [{location}]: {why}")
                rows.append({"run": label, "location": location, "ok": False, "note": why})
                continue

            monthly = cm.load_monthly_pr(label, location)
            totals = cm.water_year_totals(monthly)

            with xr.open_dataset(cm.file_for(run, "historical", location),
                                 decode_times=xr.coders.CFDatetimeCoder(use_cftime=True)) as ds:
                time = ds["pr"]["time"]
                calendar = str(time.dt.calendar)
                february_days = int(time.dt.days_in_month.values[1])
                cell = f"{ds.attrs['cell_lat']:.2f},{ds.attrs['cell_lon']:.2f}"
                distance = ds.attrs["distance_to_point_km"]

            nan_count = int(monthly.isna().sum())
            negative = monthly[monthly < 0]
            real_negative = negative[negative < -NEGATIVE_NOISE_MM]
            largest = float(monthly.max())

            if nan_count:
                failures.append(f"{label} [{location}]: {nan_count} NaN months")
            if len(real_negative):
                failures.append(f"{label} [{location}]: {len(real_negative)} negative months")
            if february_days != 28:
                failures.append(f"{label} [{location}]: February is {february_days} days")

            if largest > LARGE_MONTH_MM:
                notes.append(f"INFO  {label} [{location}]: largest single month "
                             f"{largest:.0f} mm (model extreme, left as published)")
            if len(negative):
                notes.append(f"INFO  {label} [{location}]: {len(negative)} months at "
                             f"{negative.min():.1e} mm (floating-point noise, physically zero)")

            rows.append({
                "run": label, "location": location, "ok": True, "calendar": calendar,
                "feb_days": february_days, "months": len(monthly),
                "water_years": len(totals),
                "first_wy": int(totals.index.min()), "last_wy": int(totals.index.max()),
                "ref_mean_mm": round(cm.reference_mean(totals)),
                "max_month_mm": round(largest),
                "cell": cell, "dist_km": distance,
            })

    table = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(table.to_string(index=False))

    if notes:
        print("\nInformation (not failures):")
        for note in sorted(set(notes)):
            print(" ", note)

    good = table[table["ok"]]
    for location in cm.LOCATIONS:
        part = good[good["location"] == location]
        if not part.empty:
            print(f"\n{location}: 1985-2014 mean water-year rainfall "
                  f"{part['ref_mean_mm'].min()}-{part['ref_mean_mm'].max()} mm "
                  f"across {len(part)} runs; grid cells {part['dist_km'].min():.0f}-"
                  f"{part['dist_km'].max():.0f} km from the point")

    print("\n" + ("ALL CHECKS PASS" if not failures else "CHECKS FAILED"))
    for failure in failures:
        print("  FAIL", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
