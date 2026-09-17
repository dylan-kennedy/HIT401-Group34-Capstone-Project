"""
HIT401 Group 34 - Item 5: rainfall (residual mass) + river flow + bore water level,
one chart.

Top panel = monthly rainfall bars + residual mass curve (cumulative departure from the
long-term monthly mean), middle panel = Woodforde River daily mean discharge, bottom
panel = bore water level. All three panels are restricted to the date range where all
three datasets actually overlap (printed to console on each run).

Data sources:
- Rainfall: BOM station 015643, Ti-Tree (Territory Grape Farm), ~42km from the basin
  (the previously-used station 014050, Fort Hill Wharf, was ~1,000km away in the Darwin
  area and has been replaced).
- River flow: NT DLPE gauge G0280010, Woodforde River - Arden Soak, ~28km from town.
  Source data is sub-daily (10-min intervals in recent years, sparser earlier) and is
  aggregated to a daily mean below.
- Bore level: RN016682, Water Elevation (AHD), Field Visits. RN017272 is the closest
  bore to the Woodforde gauge (0.658km) but has no water-level time series anywhere in
  the project data - only a registry row in Bores_Ti_Tree.csv / Bores.csv, no
  GroundwaterHeads export. RN016682 is the closest bore that actually has field-visit
  water elevation data (9.5km from the gauge).
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------
RAINFALL_FILE = Path("Datasets/BOM-Datasets/IDCJAC0009_015643_1800_Data.csv")
RAINFALL_STATION_NAME = "Ti-Tree (Territory Grape Farm), station 015643"

STREAMFLOW_FILE = Path(
    "Datasets/StreamflowData/WaterCourseDischarge_G0280010_WoodfordeRiver-ArdenSoak_19740530-20260916.csv"
)
STREAMFLOW_STATION_NAME = "Woodforde River - Arden Soak, station G0280010"

BORE_FILE = Path(
    "Datasets/GroundwaterHeads_20250718/LocationExport-RN016682-20250718020426/"
    "DataSetExport-Water Elevation (AHD).Field Visits@RN016682-20250718020425.csv"
)
BORE_ID = "RN016682"
# RN016682's own long-term trend is method-dependent: gwrc_trends.py found an OLS
# slope of -0.0117 m/yr that is NOT statistically significant (p=0.052), while the
# Mann-Kendall/Sen's slope of -0.0180 m/yr IS highly significant (p=3.3e-06). Both
# point the same direction (decline) but disagree on confidence, so this script plots
# the raw level series only - it does not assert a trend, and the printed "trend
# direction" below is a simple linear-fit description, not a significance test.


def load_rainfall(path):
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(dict(year=df["Year"], month=df["Month"], day=df["Day"]))
    df["Rainfall_mm"] = pd.to_numeric(df["Rainfall amount (millimetres)"], errors="coerce")
    monthly = (
        df.set_index("Date")["Rainfall_mm"]
        .resample("MS")
        .sum(min_count=1)
        .rename("Rainfall_mm")
        .to_frame()
    )
    return monthly.dropna()


def residual_mass_curve(monthly_rainfall):
    """Cumulative departure of each month's rainfall from the long-term monthly mean.

    The mean is computed from the FULL rainfall record (not clipped to the eventual
    overlap window) since a residual mass curve needs a long baseline to be meaningful.
    """
    long_term_mean = monthly_rainfall["Rainfall_mm"].mean()
    departure = monthly_rainfall["Rainfall_mm"] - long_term_mean
    residual_mass = departure.cumsum()
    return residual_mass, long_term_mean


def load_streamflow(path):
    """Load sub-daily discharge readings and aggregate to a daily mean (cumec).

    The source file has 9 metadata lines then a '#Timestamp,Value,Quality Code,
    Interpolation Type' header row - both are skipped and columns assigned manually.
    Quality Code -1 rows (no measurement) are dropped before aggregating.
    """
    df = pd.read_csv(
        path, skiprows=10, header=None,
        names=["Timestamp", "Value", "QualityCode", "InterpolationType"],
    )
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df[(df["QualityCode"] != -1) & df["Value"].notna()].dropna(subset=["Timestamp"])
    if isinstance(df["Timestamp"].dtype, pd.DatetimeTZDtype):
        df["Timestamp"] = df["Timestamp"].dt.tz_localize(None)
    daily_mean = (
        df.set_index("Timestamp")["Value"]
        .resample("D").mean()
        .dropna()
        .rename("Discharge_cumec")
    )
    return daily_mean


def load_bore_level(path):
    df = pd.read_csv(path, skiprows=2)
    df.columns = ["Timestamp", "EventTimestamp", "Value_m"]
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df["Value_m"] = pd.to_numeric(df["Value_m"], errors="coerce")
    df = df.dropna(subset=["Timestamp", "Value_m"]).sort_values("Timestamp")
    return df.set_index("Timestamp")["Value_m"]


def linear_trend_direction(series):
    """Simple linear-fit slope over a series' own index - description only, not a
    significance test. Returns (word, slope_per_year)."""
    x = series.index.map(pd.Timestamp.toordinal).to_numpy(dtype=float)
    y = series.to_numpy(dtype=float)
    slope_per_day, _ = np.polyfit(x, y, 1)
    slope_per_year = slope_per_day * 365.25
    if slope_per_year > 0.001:
        word = "rising"
    elif slope_per_year < -0.001:
        word = "declining"
    else:
        word = "roughly flat"
    return word, slope_per_year


def main():
    monthly_rain = load_rainfall(RAINFALL_FILE)
    residual_mass, mean_rain = residual_mass_curve(monthly_rain)
    streamflow_daily = load_streamflow(STREAMFLOW_FILE)
    bore_level = load_bore_level(BORE_FILE)

    # --- Restrict all three panels to the date range all three datasets share ---
    overlap_start = max(monthly_rain.index.min(), streamflow_daily.index.min(), bore_level.index.min())
    overlap_end = min(monthly_rain.index.max(), streamflow_daily.index.max(), bore_level.index.max())

    monthly_rain_clip = monthly_rain.loc[overlap_start:overlap_end]
    residual_mass_clip = residual_mass.loc[overlap_start:overlap_end]
    streamflow_clip = streamflow_daily.loc[overlap_start:overlap_end]
    bore_level_clip = bore_level.loc[overlap_start:overlap_end]

    fig, (ax_rain, ax_flow, ax_bore) = plt.subplots(
        3, 1, figsize=(11, 10), sharex=False,
        gridspec_kw={"height_ratios": [1, 1, 1]},
    )

    # --- Panel 1: rainfall bars + residual mass curve (twin axis) ---
    ax_rain.bar(monthly_rain_clip.index, monthly_rain_clip["Rainfall_mm"], width=25,
                color="#7fb3d5", label="Monthly rainfall (mm)")
    ax_rain.set_ylabel("Monthly rainfall (mm)", color="#2e6d9e")
    ax_rain.tick_params(axis="y", labelcolor="#2e6d9e")

    ax_rm = ax_rain.twinx()
    ax_rm.plot(residual_mass_clip.index, residual_mass_clip.values, color="#c0392b",
               lw=1.5, label="Residual mass curve (mm)")
    ax_rm.set_ylabel("Residual mass (mm, cum. departure from mean)", color="#c0392b")
    ax_rm.tick_params(axis="y", labelcolor="#c0392b")
    ax_rain.set_title(
        f"Rainfall + residual mass curve - {RAINFALL_STATION_NAME}\n"
        f"(long-term monthly mean = {mean_rain:.1f} mm, full record)",
        fontsize=10,
    )
    ax_rain.set_xlim(overlap_start, overlap_end)

    # --- Panel 2: river flow. Linear axis on purpose - this creek is ephemeral
    # (mostly zero flow with sharp wet-season spikes), and a log scale would visually
    # hide the zero-flow periods, which are themselves the important signal here. ---
    ax_flow.plot(streamflow_clip.index, streamflow_clip.values, color="#117864", lw=1)
    ax_flow.set_ylabel("Discharge (m3/s, daily mean)")
    ax_flow.set_title(f"Watercourse discharge - {STREAMFLOW_STATION_NAME}", fontsize=10)
    ax_flow.set_xlim(overlap_start, overlap_end)

    # --- Panel 3: bore water level ---
    ax_bore.plot(bore_level_clip.index, bore_level_clip.values, color="#1a5276", marker="o", ms=3, lw=1)
    ax_bore.set_ylabel("Water elevation, AHD (m)")
    ax_bore.set_title(f"Bore water level - {BORE_ID} (field visits)", fontsize=10)
    ax_bore.set_xlabel("Date")
    ax_bore.set_xlim(overlap_start, overlap_end)

    fig.suptitle(
        "Item 5: rainfall / residual mass / river flow / bore level",
        fontsize=12, y=1.02,
    )
    fig.tight_layout()
    fig.savefig("residual_mass_demo.png", dpi=150, bbox_inches="tight")
    print("Saved residual_mass_demo.png")

    zero_pct_full = (streamflow_daily == 0).mean() * 100
    zero_pct_overlap = (streamflow_clip == 0).mean() * 100
    trend_word, trend_slope = linear_trend_direction(bore_level_clip)

    print()
    print(f"Overlap date range used for all 3 panels: {overlap_start.date()} to {overlap_end.date()}")
    print(f"  Rainfall record (full):    {monthly_rain.index.min().date()} to {monthly_rain.index.max().date()}  ({len(monthly_rain)} months)")
    print(f"  Streamflow record (full):  {streamflow_daily.index.min().date()} to {streamflow_daily.index.max().date()}  ({len(streamflow_daily)} daily means)")
    print(f"  Bore record (full):        {bore_level.index.min().date()} to {bore_level.index.max().date()}  ({len(bore_level)} readings)")
    print()
    print(f"Long-term mean rainfall (full record): {mean_rain:.1f} mm/month")
    print(f"Zero-flow days at Woodforde gauge: {zero_pct_full:.1f}% of full record, {zero_pct_overlap:.1f}% within the overlap window")
    print(f"Bore {BORE_ID} raw trend over overlap window: {trend_word} ({trend_slope:+.4f} m/yr, simple linear fit - see CONFIG comment on trend significance)")


if __name__ == "__main__":
    main()
