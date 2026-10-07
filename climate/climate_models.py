"""
climate_models.py - water-year rainfall from CMIP6 model runs, for HIT401 Group 34.

This module reads the small per-cell NetCDF files written by download_cmip6_pr.py
(data/climate/) and turns them into the numbers behind A/Prof Dylan Irvine's slides:

  * monthly rainfall in mm              -> load_monthly_pr()
  * water-year totals (1 Sep - 31 Aug)  -> water_year_totals()
  * difference from the 1985-2014 mean  -> anomalies()
  * 10-year trailing mean               -> trailing_mean()
  * 2070-2099 vs 1985-2014 % change     -> pct_change()

It is importable (from climate_models import ...) and also runs on its own:

    python climate/climate_models.py    # prints what data is present and a summary table

Nothing here downloads data or changes any existing file. If model files are missing the
functions say so clearly and return empty results rather than raising.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# ---------------------------------------------------------
# SHARED CONSTANTS (single place to change them)
# ---------------------------------------------------------

# Colours sampled from the pixels of the supervisor's slides 28-31.
COLOUR_WETTER = "#3B87CA"     # blue  = wetter than the reference average
COLOUR_DRIER = "#BB274E"      # magenta = drier than the reference average
COLOUR_REFERENCE_SHADE = "#E6E6E6"   # grey block behind the reference period
COLOUR_LINE = "#000000"       # black moving-mean line / median tick
COLOUR_GRID = "#D9D9D9"       # light grey gridlines
COLOUR_SUBTITLE = "#666666"   # grey subtitle text
COLOUR_CREDIT = "#CCCCCC"     # faint grey credit, bottom right

# Credit line. Dylan's name is NOT used as the author of our charts: the design is his,
# the numbers are ours. Change or blank this string to change every chart.
CREDIT_TEXT = "Data: CMIP6 (ESGF). Chart design after D. Irvine, CDU."

# The slides compare everything with the mean of the 1985-2014 water years, and the
# slide-31 future window is 2070-2099. Water years are labelled by the year they START in.
REFERENCE_PERIOD = (1985, 2014)
FUTURE_PERIOD = (2070, 2099)
MOVING_MEAN_WINDOW = 10       # years, trailing (see trailing_mean)
FIRST_PLOT_YEAR = 1975        # charts start here; the moving mean is computed before cropping
LAST_WATER_YEAR = 2099        # ssp245 ends Dec 2100, so 2099 is the last COMPLETE water year

WATER_YEAR_START_MONTH = 9    # 1 September

# The CMIP6 historical experiment is defined as ending in December 2014 and ssp245 takes
# over in January 2015. A few models publish historical months BEYOND 2014 as well
# (FGOALS-g3 runs to 2016). Those extra months would double up with ssp245, so the
# historical part is truncated here and the scenario is used from 2015 on.
HISTORICAL_END = "2014-12"

SCENARIO_LABEL = "SSP2-4.5"
EXPERIMENTS = ["historical", "ssp245"]

# This file lives in climate/, so the repository root is one level up. Every data path is
# built from PROJECT_ROOT rather than the working directory, so the module behaves the same
# whether it is imported by the app, run directly, or run from the tests folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data" / "climate"

# Locations must match download_cmip6_pr.py.
LOCATIONS = {
    "Darwin": (-12.46, 130.84),
    "Ti Tree": (-22.1, 133.4),
}

# Model runs, matching download_cmip6_pr.py. `label` is the name used on the slides.
# Two runs use a different variant from the slide default because that is what is published
# in BOTH experiments (see the notes column):
#   CNRM-CM6-1-HR  r1i1p1f2 - only f2 exists on NCI
#   GISS-E2-1-G    r1i1p1f2 - the only same-physics pair available for historical + ssp245
REGISTRY = [
    {"label": "GFDL-ESM4",                "source_id": "GFDL-ESM4",     "member": "r1i1p1f1"},
    {"label": "ACCESS-CM2",               "source_id": "ACCESS-CM2",    "member": "r1i1p1f1"},
    {"label": "EC-Earth3",                "source_id": "EC-Earth3",     "member": "r1i1p1f1"},
    {"label": "MRI-ESM2-0",               "source_id": "MRI-ESM2-0",    "member": "r1i1p1f1"},
    {"label": "MPI-ESM1-2-LR",            "source_id": "MPI-ESM1-2-LR", "member": "r1i1p1f1"},
    {"label": "FGOALS-g3",                "source_id": "FGOALS-g3",     "member": "r1i1p1f1"},
    {"label": "CNRM-CM6-1-HR",            "source_id": "CNRM-CM6-1-HR", "member": "r1i1p1f2"},
    {"label": "GISS-E2-1-G",              "source_id": "GISS-E2-1-G",   "member": "r1i1p1f2"},
    {"label": "CMCC-ESM2",                "source_id": "CMCC-ESM2",     "member": "r1i1p1f1"},
    {"label": "ACCESS-ESM1-5 r6 (v2105)", "source_id": "ACCESS-ESM1-5", "member": "r6i1p1f1"},
    {"label": "NorESM2-MM",               "source_id": "NorESM2-MM",    "member": "r1i1p1f1"},
]

# Slide-31 rows marked "(coupled...)". We could not identify these runs, so they are not built.
UNMATCHED_SLIDE_RUNS = [
    "CNRM-CM6-1-HR (coupled)",
    "ACCESS-ESM1-5 r20 (coupled v2112)",
    "NorESM2-MM (coupled)",
    "ACCESS-ESM1-5 r40 (coupled v2112)",
]

SECONDS_PER_DAY = 86400       # pr is kg m-2 s-1 == mm s-1, so mm/month = pr * 86400 * days


# ---------------------------------------------------------
# FILE LOOKUP
# ---------------------------------------------------------

def _safe_name(text):
    """'Ti Tree' -> 'TiTree' (same rule as download_cmip6_pr.py)."""
    return "".join(ch for ch in text if ch.isalnum() or ch in "-_")


def run_by_label(label):
    """Look a run up in REGISTRY by its slide label. Returns None if unknown."""
    for run in REGISTRY:
        if run["label"] == label:
            return run
    return None


def file_for(run, experiment, location):
    """Path of the saved cell file for one run/experiment/location (may not exist)."""
    return DATA_DIR / f"pr_{run['source_id']}_{run['member']}_{experiment}_{_safe_name(location)}.nc"


def available_runs(location):
    """Slide labels that have BOTH experiments saved for this location."""
    return [r["label"] for r in REGISTRY
            if all(file_for(r, exp, location).exists() for exp in EXPERIMENTS)]


def missing_runs(location):
    """{label: 'which files are missing'} for runs whose saved files are absent."""
    out = {}
    for run in REGISTRY:
        gaps = [exp for exp in EXPERIMENTS if not file_for(run, exp, location).exists()]
        if gaps:
            out[run["label"]] = "missing " + " and ".join(gaps)
    return out


def check_run(label, location, data_dir=None):
    """
    Can this run actually be plotted here? Returns (True, "") or (False, reason).
    Never raises: callers use it to skip a run and explain why.
    """
    run = run_by_label(label)
    if run is None:
        return False, "not in REGISTRY"
    gaps = [exp for exp in EXPERIMENTS if not file_for(run, exp, location).exists()]
    if gaps:
        return False, "missing " + " and ".join(gaps)
    try:
        totals = water_year_totals(load_monthly_pr(label, location, data_dir=data_dir))
    except Exception as exc:                      # unreadable file, gap, overlap...
        return False, str(exc)[:120]
    # The reference and future windows must be fully present, or the percentages would be
    # computed from a different number of years than every other model.
    for name, (start, end) in {"reference": REFERENCE_PERIOD, "future": FUTURE_PERIOD}.items():
        have = totals[(totals.index >= start) & (totals.index <= end)]
        if len(have) < (end - start + 1):
            return False, (f"only {len(have)}/{end - start + 1} water years in the "
                           f"{name} period {start}-{end}")
    return True, ""


def usable_runs(location, data_dir=None):
    """(runs that pass check_run, {label: reason} for the rest) - never raises."""
    good, bad = [], {}
    for run in REGISTRY:
        ok, why = check_run(run["label"], location, data_dir=data_dir)
        (good.append(run["label"]) if ok else bad.update({run["label"]: why}))
    return good, bad


def missing_message(location):
    """A human-readable note about missing data; empty string when nothing is missing."""
    gaps = missing_runs(location)
    if not gaps:
        return ""
    lines = [f"No saved data for {len(gaps)} run(s) at {location}. "
             f"Run:  python download_cmip6_pr.py --download"]
    lines += [f"  - {label}: {why}" for label, why in sorted(gaps.items())]
    return "\n".join(lines)


def cell_info(label, location, experiment="historical"):
    """
    (cell_lat, cell_lon, distance_km) for one run, read from the saved file's attributes.
    The distance is from the requested point to the centre of the model grid cell used.
    Returns None if the file is not there.
    """
    run = run_by_label(label)
    path = file_for(run, experiment, location) if run else None
    if path is None or not path.exists():
        return None
    with xr.open_dataset(path, decode_times=False) as ds:
        return (float(ds.attrs["cell_lat"]), float(ds.attrs["cell_lon"]),
                float(ds.attrs["distance_to_point_km"]))


# ---------------------------------------------------------
# 1. MONTHLY RAINFALL IN MM
# ---------------------------------------------------------

def _monthly_mm(path):
    """
    Read one saved file and convert pr to mm per month.

    pr is in kg m-2 s-1, which for water is the same as mm per second, so
        mm in a month = pr * 86400 seconds * (number of days in THAT month).
    The day count comes from the file's own time axis, so a model on a 'noleap'
    calendar correctly gets 28 days every February and a 360-day model gets 30.
    Returns a pandas Series indexed by a period-like 'YYYY-MM' string index.
    """
    with xr.open_dataset(path, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True)) as ds:
        pr = ds["pr"]
        days = pr["time"].dt.days_in_month          # model calendar, not the Gregorian one
        mm = (pr * SECONDS_PER_DAY * days).values.astype(float)
        times = pr["time"].values
    index = pd.Index([f"{t.year:04d}-{t.month:02d}" for t in times], name="month")
    return pd.Series(mm, index=index, name="rain_mm")


def load_monthly_pr(model_run, location, data_dir=None):
    """
    Monthly rainfall (mm) for one model run at one location, historical + ssp245 joined.

    model_run : slide label, e.g. "GFDL-ESM4"
    location  : "Darwin" or "Ti Tree"

    Raises FileNotFoundError only if asked for a run whose files are absent; callers that
    want a soft failure should check available_runs() first.
    The join at 2014/2015 is verified: the two experiments must not overlap and must not
    leave a gap (historical ends 2014-12, ssp245 starts 2015-01).
    """
    run = run_by_label(model_run)
    if run is None:
        raise KeyError(f"Unknown model run {model_run!r}. Known: {[r['label'] for r in REGISTRY]}")

    folder = Path(data_dir) if data_dir else DATA_DIR
    parts = {}
    for exp in EXPERIMENTS:
        path = folder / file_for(run, exp, location).name
        if not path.exists():
            raise FileNotFoundError(f"No saved data: {path}. Run download_cmip6_pr.py --download")
        parts[exp] = _monthly_mm(path)

    historical, future = parts["historical"], parts["ssp245"]

    # Keep historical to its defined end (see HISTORICAL_END) so extra published months
    # cannot double up with the scenario run.
    historical = historical[historical.index <= HISTORICAL_END]
    future = future[future.index > HISTORICAL_END]

    # --- check the join at 2014/2015 ---
    overlap = historical.index.intersection(future.index)
    if len(overlap):
        raise ValueError(f"{model_run} {location}: historical and ssp245 overlap at {list(overlap)[:3]}")
    joined = pd.concat([historical, future]).sort_index()
    gaps = _missing_months(joined.index)
    if gaps:
        raise ValueError(f"{model_run} {location}: gap in the monthly series at {gaps[:3]}")
    return joined


def _missing_months(index):
    """Return any calendar months absent between the first and last month of `index`."""
    expected = pd.period_range(index[0], index[-1], freq="M").strftime("%Y-%m")
    return sorted(set(expected) - set(index))


# ---------------------------------------------------------
# 2. WATER YEARS
# ---------------------------------------------------------

def water_year_totals(series, last_year=LAST_WATER_YEAR):
    """
    Total rainfall per water year. A water year runs 1 September to 31 August and is
    LABELLED BY THE YEAR IT STARTS IN, so September 2000 to August 2001 is water year 2000.

    Incomplete water years are dropped: only years with all 12 months are kept. That
    always removes the first partial year (Jan-Aug of the first calendar year) and any
    final partial year. `last_year` additionally trims anything after 2099 (some models
    publish past 2100, and 2100 has no complete water year inside our data).

    Returns a Series indexed by the integer water year.
    """
    years = np.array([int(m[:4]) for m in series.index])
    months = np.array([int(m[5:7]) for m in series.index])
    # Months from September onwards belong to the water year of the CURRENT calendar year;
    # January to August belong to the water year that started in the PREVIOUS year.
    water_year = np.where(months >= WATER_YEAR_START_MONTH, years, years - 1)

    frame = pd.DataFrame({"rain_mm": series.values, "water_year": water_year})
    grouped = frame.groupby("water_year")["rain_mm"].agg(["sum", "count"])
    complete = grouped[grouped["count"] == 12]["sum"]
    complete = complete[complete.index <= last_year]
    complete.index.name = "water_year"
    return complete.rename("rain_mm")


def anomalies(wy, ref=REFERENCE_PERIOD):
    """
    Difference (mm) between each water-year total and the mean of the reference period.
    Positive = wetter than the 1985-2014 average, negative = drier.
    """
    baseline = reference_mean(wy, ref)
    return (wy - baseline).rename("anomaly_mm")


def reference_mean(wy, ref=REFERENCE_PERIOD):
    """Mean water-year total over the reference period (default 1985-2014)."""
    window = wy.loc[(wy.index >= ref[0]) & (wy.index <= ref[1])]
    if window.empty:
        raise ValueError(f"No water years inside the reference period {ref}")
    return float(window.mean())


def trailing_mean(series, window=MOVING_MEAN_WINDOW, first_year=FIRST_PLOT_YEAR):
    """
    Trailing (backward-looking) moving mean: each point is the mean of that year and the
    previous `window - 1` years. It is computed on the FULL series (which starts in 1850),
    then cropped to `first_year` onwards, so the line already has a full 10-year window at
    the left edge of the chart instead of starting empty. This matches the slides, whose
    moving-mean line is already well away from zero in 1975.
    """
    rolled = series.rolling(window=window, min_periods=window).mean()
    if first_year is not None:
        rolled = rolled[rolled.index >= first_year]
    return rolled.rename(f"mean_{window}yr")


# ---------------------------------------------------------
# 3. CHANGE BETWEEN TWO PERIODS (slide 31)
# ---------------------------------------------------------

def pct_change(wy, ref=REFERENCE_PERIOD, future=FUTURE_PERIOD):
    """
    How much wetter or drier is the future period than the reference period?

    Returns a dict with:
      mean_pct   - % change in the MEAN of the water-year totals (the bar on slide 31)
      median_pct - % change in the MEDIAN water-year total (the separate black tick;
                   it can fall on the other side of zero from the bar)
      plus the underlying mm values, for the report.
    """
    ref_years = wy.loc[(wy.index >= ref[0]) & (wy.index <= ref[1])]
    future_years = wy.loc[(wy.index >= future[0]) & (wy.index <= future[1])]
    if ref_years.empty or future_years.empty:
        raise ValueError(f"Not enough water years for {ref} vs {future}")

    ref_mean, future_mean = float(ref_years.mean()), float(future_years.mean())
    ref_median, future_median = float(ref_years.median()), float(future_years.median())
    return {
        "mean_pct": (future_mean - ref_mean) / ref_mean * 100.0,
        "median_pct": (future_median - ref_median) / ref_median * 100.0,
        "ref_mean_mm": ref_mean,
        "future_mean_mm": future_mean,
        "ref_median_mm": ref_median,
        "future_median_mm": future_median,
        "n_ref_years": int(ref_years.size),
        "n_future_years": int(future_years.size),
    }


def change_table(location, ref=REFERENCE_PERIOD, future=FUTURE_PERIOD, data_dir=None):
    """
    pct_change() for every run that has data at this location, sorted wettest to driest.
    Runs without data are simply absent; use missing_message(location) to report them.
    """
    rows = []
    good, _ = usable_runs(location, data_dir=data_dir)
    for label in good:
        wy = water_year_totals(load_monthly_pr(label, location, data_dir=data_dir))
        rows.append({"model_run": label, **pct_change(wy, ref, future)})
    if not rows:
        return pd.DataFrame(columns=["model_run", "mean_pct", "median_pct"])
    return pd.DataFrame(rows).sort_values("mean_pct", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------
# 4. PLOTS (plotly) - replicating the supervisor's slides
# ---------------------------------------------------------

# The grey two-line note that sits under the title on slides 28-30.
ANOMALY_SUBTITLE = (
    "Blue years are wetter than the 1985-2014 average, magenta years are drier. "
    "The model is not forecasting which individual year will be wet; read the spread and the drift<br>"
    "of the moving mean, not any single bar."
)


def _base_layout(figure, credit=CREDIT_TEXT, footnote=None):
    """
    White background, only left and bottom axis lines, the faint credit bottom right and
    an optional plain-language footnote bottom left (used for the grid-cell distance).
    """
    figure.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Helvetica, Arial, sans-serif", size=13, color="#000000"),
        margin=dict(l=90, r=40, t=110, b=70),
    )
    if footnote:
        figure.add_annotation(
            text=footnote, xref="paper", yref="paper", x=0.0, y=-0.16,
            showarrow=False, font=dict(size=10, color=COLOUR_SUBTITLE),
            xanchor="left", yanchor="top",
        )
    if credit:
        figure.add_annotation(
            text=credit, xref="paper", yref="paper", x=1.0, y=-0.16,
            showarrow=False, font=dict(size=10, color=COLOUR_CREDIT),
            xanchor="right", yanchor="top",
        )
    return figure


def plot_anomaly_bars(model_run, location, data_dir=None):
    """
    Replicate slides 28-30: water-year rainfall anomalies for ONE model run.

    Blue bars are water years wetter than the 1985-2014 mean, magenta bars drier.
    The grey block marks the reference period itself and the black line is the 10-year
    TRAILING mean, computed on the full 1850-2099 series then cropped to 1975 so it
    already has a complete window at the left edge (see trailing_mean).
    """
    import plotly.graph_objects as go

    monthly = load_monthly_pr(model_run, location, data_dir=data_dir)
    totals = water_year_totals(monthly)
    anomaly = anomalies(totals)
    rolling = trailing_mean(totals)

    # Charts start at 1975 (the moving mean was computed on the full series first).
    anomaly = anomaly[anomaly.index >= FIRST_PLOT_YEAR]

    figure = go.Figure()

    # Grey block behind the reference period. 1984.5-2014.5 so it covers the whole bars
    # of 1985 and 2014, exactly as on the slides.
    figure.add_shape(
        type="rect", xref="x", yref="paper",
        x0=REFERENCE_PERIOD[0] - 0.5, x1=REFERENCE_PERIOD[1] + 0.5, y0=0, y1=1,
        fillcolor=COLOUR_REFERENCE_SHADE, line_width=0, layer="below",
    )

    # One bar per water year, coloured by sign.
    figure.add_trace(go.Bar(
        x=anomaly.index, y=anomaly.values, width=0.6, showlegend=False,
        marker_color=[COLOUR_WETTER if v >= 0 else COLOUR_DRIER for v in anomaly.values],
        hovertemplate="Water year %{x}<br>%{y:.0f} mm vs the 1985-2014 average<extra></extra>",
    ))

    # Black 10-year trailing mean. This is the only trace with a legend entry.
    figure.add_trace(go.Scatter(
        x=rolling.index, y=(rolling - reference_mean(totals)).values,
        mode="lines", name=f"{MOVING_MEAN_WINDOW}-year moving mean",
        line=dict(color=COLOUR_LINE, width=1.8),
        hovertemplate="%{x}: %{y:.0f} mm<extra></extra>",
    ))

    title = f"{location}: water-year rainfall, {model_run}, {SCENARIO_LABEL}"
    figure.update_layout(
        title=dict(
            text=f"<span style='font-size:17px'>{title}</span><br>"
                 f"<span style='font-size:11.5px;color:{COLOUR_SUBTITLE}'>{ANOMALY_SUBTITLE}</span>",
            x=0.01, xanchor="left", y=0.96, yanchor="top",
        ),
        bargap=0.35,
        legend=dict(orientation="h", x=0.02, y=1.0, xanchor="left", yanchor="top",
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
        xaxis=dict(
            title="Water year (1 September start)",
            tick0=1980, dtick=20, showgrid=False,
            showline=True, linecolor="#000000", linewidth=1, ticks="outside", ticklen=4,
        ),
        yaxis=dict(
            title="Difference from the<br>1985-2014 average (mm)",
            showgrid=True, gridcolor=COLOUR_GRID, gridwidth=1,
            zeroline=True, zerolinecolor="#000000", zerolinewidth=1,
            showline=True, linecolor="#000000", linewidth=1, ticks="outside", ticklen=4,
        ),
        height=520, width=1000,
    )

    # "Reference period 1985-2014" is plain text on the slides, with no colour swatch.
    figure.add_annotation(
        text=f"Reference period {REFERENCE_PERIOD[0]}-{REFERENCE_PERIOD[1]}",
        xref="paper", yref="paper", x=0.30, y=0.995,
        showarrow=False, font=dict(size=12.5, color="#000000"), xanchor="left", yanchor="top",
    )
    # Footnote: how far the model cell centre is from the place we asked for, plus the
    # moving-mean convention. Both matter when reading the chart.
    cell = cell_info(model_run, location)
    distance = (f"Model grid cell centre {cell[0]:.2f}, {cell[1]:.2f} is {cell[2]:.0f} km "
                f"from {location}. " if cell else "")
    footnote = (f"{distance}The {MOVING_MEAN_WINDOW}-year moving mean is trailing, computed on "
                f"the full series from 1850 and then cropped to {FIRST_PLOT_YEAR}.")
    return _base_layout(figure, footnote=footnote)


def plot_wetter_or_drier(location, ref=REFERENCE_PERIOD, future=FUTURE_PERIOD, data_dir=None):
    """
    Replicate slide 31: one horizontal bar per model run, sorted wettest to driest.

    The bar is the % change in the MEAN water-year total; the separate black tick is the
    change in the MEDIAN (typical) year, which can sit on the other side of zero.
    Every number in the subtitle is computed from our own data.
    """
    import plotly.graph_objects as go

    table = change_table(location, ref=ref, future=future, data_dir=data_dir)
    if table.empty:
        raise ValueError(missing_message(location) or f"No model data for {location}")

    # Plotly draws the first category at the bottom, so reverse for wettest-at-top.
    rows = table.iloc[::-1].reset_index(drop=True)
    labels = rows["model_run"].tolist()
    means = rows["mean_pct"].tolist()
    medians = rows["median_pct"].tolist()

    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=means, y=labels, orientation="h", width=0.62, showlegend=False,
        marker_color=[COLOUR_WETTER if v >= 0 else COLOUR_DRIER for v in means],
        hovertemplate="%{y}<br>mean %{x:+.1f}%<extra></extra>",
    ))

    # Black tick for the median year (a short vertical dash, as on the slide).
    figure.add_trace(go.Scatter(
        x=medians, y=labels, mode="markers", name="Change in the typical (median) year",
        marker=dict(symbol="line-ns", size=13, line=dict(color=COLOUR_LINE, width=2)),
        hovertemplate="%{y}<br>median %{x:+.1f}%<extra></extra>",
    ))

    # Value labels sit just beyond whichever reaches further, the bar or the tick.
    span = max(max(abs(v) for v in means), max(abs(v) for v in medians))
    pad = span * 0.04
    for label, mean_pct, median_pct in zip(labels, means, medians):
        if mean_pct >= 0:
            x = max(mean_pct, median_pct) + pad
            anchor = "left"
        else:
            x = min(mean_pct, median_pct) - pad
            anchor = "right"
        figure.add_annotation(x=x, y=label, text=f"{mean_pct:+.1f}%", showarrow=False,
                              xanchor=anchor, font=dict(size=12, color="#000000"))

    # Subtitle numbers, all from our data.
    wetter = int((table["mean_pct"] > 0).sum())
    total = len(table)
    subtitle = (
        f"{SCENARIO_LABEL}, {future[0]}-{future[1]} compared with the {ref[0]}-{ref[1]} average, "
        f"using the mean of the water-year totals. Each bar is one climate model, shown on its own: "
        f"no averaging<br>across models. {wetter} of {total} project more rain, and the models span "
        f"{table['mean_pct'].min():.1f}% to {table['mean_pct'].max():+.1f}%. "
        f"The disagreement between the models is itself part of the answer."
    )

    # Keep the slide's -30..20 window unless our numbers need more room.
    low = min(-30.0, min(means + medians) - 4 * pad)
    high = max(20.0, max(means + medians) + 4 * pad)

    figure.update_layout(
        title=dict(
            text=f"<span style='font-size:17px'>Is {location} getting wetter or drier?</span><br>"
                 f"<span style='font-size:11.5px;color:{COLOUR_SUBTITLE}'>{subtitle}</span>",
            x=0.01, xanchor="left", y=0.97, yanchor="top",
        ),
        legend=dict(orientation="h", x=0.99, y=-0.08, xanchor="right", yanchor="top",
                    bgcolor="rgba(0,0,0,0)", borderwidth=0),
        xaxis=dict(
            title="Change in average water-year rainfall (%)", range=[low, high],
            showgrid=True, gridcolor=COLOUR_GRID, dtick=10,
            zeroline=True, zerolinecolor="#000000", zerolinewidth=1,
            showline=True, linecolor="#000000", linewidth=1, ticks="outside", ticklen=4,
        ),
        yaxis=dict(showgrid=False, showline=False, ticks="", automargin=True),
        bargap=0.3,
        height=560, width=1050,
    )
    distances = [cell_info(label, location)[2] for label in labels if cell_info(label, location)]
    footnote = (f"Each model has its own grid; the cell centres used are "
                f"{min(distances):.0f}-{max(distances):.0f} km from {location}." if distances else None)
    return _base_layout(figure, footnote=footnote)


# ---------------------------------------------------------
# 5. OBSERVED DATA: RESIDUAL MASS CURVES
# ---------------------------------------------------------
#
# Residual mass (Cat's formula, after the BOM AWRA technical supplement,
# https://www.bom.gov.au/water/awra/2010/documents/technical_supplement.pdf):
#
#   for each month:  residual = that month's total - the long-term average for that
#                               SAME calendar month (so the seasonal cycle is removed)
#   then plot the RUNNING TOTAL of those residuals.
#
# A rising curve means a run of months wetter than normal, a falling curve a run of
# drier-than-normal months. The slope is what matters, not the height.

BOM_DIR = PROJECT_ROOT / "Datasets" / "BOM-Datasets"
FLOW_DIR = PROJECT_ROOT / "Datasets" / "StreamflowData"

# A month is treated as MISSING if more than this many of its days have no value.
# Missing months are excluded from the long-term averages and add 0 to the running total.
MAX_BLANK_DAYS = 5

# BOM daily rainfall stations present in Datasets/BOM-Datasets (station number -> name).
# Only 015643 is anywhere near Ti Tree; the others are interstate or Darwin.
TI_TREE_STATION = "015643"
STATION_NAMES = {
    "015643": "Territory Grape Farm",   # NT, lat -22.45, about 42 km from Ti Tree
    "014050": "Fort Hill Wharf",        # NT, but Darwin
}

FLOW_STATION = "G0280010"               # Woodforde River - Arden Soak


def load_station_daily(station=TI_TREE_STATION, folder=None):
    """
    Read one BOM daily rainfall file (product IDCJAC0009) into a tidy DataFrame.

    Data quality for station 015643 (Territory Grape Farm), checked 7 Oct 2026:
      * record runs 1 Jan 1987 to 17 Sep 2026, with no missing calendar DATES
      * about 5% of days (750 of 14,505) have a blank rainfall value
      * 159 of 477 months contain at least one blank day, though most are short by
        only one or two days; Mar-Apr 1996, Mar-May 2017 and Sep 2025 are entirely blank
      * the Quality flag is mostly "N" (not quality controlled): 8,359 N against 5,396 Y
    These gaps are the reason for the MAX_BLANK_DAYS rule below.
    """
    folder = Path(folder) if folder else BOM_DIR
    path = folder / f"IDCJAC0009_{station}_1800_Data.csv"
    if not path.exists():
        raise FileNotFoundError(f"No BOM rainfall file at {path}")
    raw = pd.read_csv(path)
    rain_column = [c for c in raw.columns if c.startswith("Rainfall amount")][0]
    frame = pd.DataFrame({
        "date": pd.to_datetime(dict(year=raw["Year"], month=raw["Month"], day=raw["Day"]),
                               errors="coerce"),
        "rain_mm": pd.to_numeric(raw[rain_column], errors="coerce"),
        "quality": raw.get("Quality"),
    }).dropna(subset=["date"])
    return frame.sort_values("date").reset_index(drop=True)


def monthly_totals_from_daily(daily, max_blank_days=MAX_BLANK_DAYS):
    """
    Daily values -> monthly totals, with a 'complete' flag.

    A month is complete when it has no more than `max_blank_days` days without a value.
    Days absent from the file count as blank too, so a month that is short of rows is
    judged the same way as one full of empty cells.
    Returns a DataFrame indexed by 'YYYY-MM' with total, blank_days and complete.
    """
    work = daily.copy()
    work["month"] = work["date"].dt.to_period("M")
    grouped = work.groupby("month").agg(
        total=("rain_mm", "sum"),            # sum skips blanks
        present=("rain_mm", "count"),        # days that DO have a value
    )
    # Re-index onto every calendar month, so months missing from the file appear as blank.
    months = pd.period_range(work["month"].min(), work["month"].max(), freq="M")
    grouped = grouped.reindex(months)
    days_in_month = pd.Series([m.days_in_month for m in months], index=months)
    grouped["present"] = grouped["present"].fillna(0)
    grouped["blank_days"] = (days_in_month - grouped["present"]).astype(int)
    grouped["complete"] = grouped["blank_days"] <= max_blank_days
    grouped["total"] = grouped["total"].where(grouped["complete"])   # incomplete -> NaN
    grouped.index = grouped.index.strftime("%Y-%m")
    grouped.index.name = "month"
    return grouped[["total", "blank_days", "complete"]]


def residual_mass(monthly, value_column="total"):
    """
    Residual mass curve from a monthly table (the output of monthly_totals_from_daily
    or the river-flow equivalent).

    * the long-term average for each calendar month uses COMPLETE months only
    * residual = this month's total - the average for that calendar month
    * cumulative = the running total of the residuals
    * a missing month has residual 0, so the curve goes flat rather than jumping

    Returns the table with month_average, residual and cumulative columns added.
    """
    out = monthly.copy()
    calendar_month = pd.Index(out.index).str.slice(5, 7)
    out["calendar_month"] = calendar_month

    complete = out[out["complete"]]
    averages = complete.groupby(complete.index.str.slice(5, 7))[value_column].mean()
    out["month_average"] = calendar_month.map(averages)

    out["residual"] = out[value_column] - out["month_average"]
    out["residual"] = out["residual"].fillna(0.0)        # a gap adds nothing
    out["cumulative"] = out["residual"].cumsum()
    return out


def gap_bands(table):
    """List of (first_month, last_month) runs of incomplete months, for shading a chart."""
    bands, start, previous = [], None, None
    for month, complete in zip(table.index, table["complete"]):
        if not complete and start is None:
            start = month
        elif complete and start is not None:
            bands.append((start, previous))
            start = None
        previous = month
    if start is not None:
        bands.append((start, previous))
    return bands


def _month_to_timestamp(month):
    """'1987-03' -> a Timestamp at the middle of that month, for plotting."""
    return pd.Period(month, freq="M").to_timestamp(how="start") + pd.Timedelta(days=14)


def plot_residual_mass(table, title, value_label="Monthly rainfall (mm)",
                       cumulative_label="Cumulative residual (mm)", credit=CREDIT_TEXT,
                       footnote=None):
    """
    One residual mass figure: monthly totals as bars, the running residual as a line
    on a second y axis, and light bands over the months treated as missing.
    """
    import plotly.graph_objects as go

    x = [_month_to_timestamp(m) for m in table.index]
    figure = go.Figure()

    figure.add_trace(go.Bar(
        x=x, y=table["total"], name=value_label, marker_color=COLOUR_WETTER, opacity=0.55,
        hovertemplate="%{x|%b %Y}<br>%{y:.1f}<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=x, y=table["cumulative"], name=cumulative_label, yaxis="y2",
        mode="lines", line=dict(color=COLOUR_LINE, width=1.8),
        hovertemplate="%{x|%b %Y}<br>running total %{y:.0f}<extra></extra>",
    ))

    # Light bands where months were treated as missing (they add 0 to the running total).
    for first, last in gap_bands(table):
        figure.add_shape(
            type="rect", xref="x", yref="paper", layer="below", line_width=0,
            fillcolor=COLOUR_DRIER, opacity=0.10,
            x0=_month_to_timestamp(first) - pd.Timedelta(days=15),
            x1=_month_to_timestamp(last) + pd.Timedelta(days=15), y0=0, y1=1,
        )

    figure.update_layout(
        title=dict(text=f"<span style='font-size:16px'>{title}</span>",
                   x=0.01, xanchor="left", y=0.95, yanchor="top"),
        xaxis=dict(title="", showgrid=False, showline=True, linecolor="#000000",
                   ticks="outside", ticklen=4),
        yaxis=dict(title=value_label, showgrid=True, gridcolor=COLOUR_GRID,
                   showline=True, linecolor="#000000", ticks="outside", ticklen=4),
        yaxis2=dict(title=cumulative_label, overlaying="y", side="right",
                    showgrid=False, zeroline=True, zerolinecolor="#999999"),
        legend=dict(orientation="h", x=0.01, y=1.0, xanchor="left", yanchor="bottom",
                    bgcolor="rgba(0,0,0,0)"),
        bargap=0.1, height=460, width=1000,
    )
    note = footnote or (f"Shaded bands are months with more than {MAX_BLANK_DAYS} blank days; "
                        f"they add 0 to the running total.")
    return _base_layout(figure, credit=credit, footnote=note)


# --- observed water years ---------------------------------------------------

# A water year is dropped if more than this many of its 12 months are missing.
MAX_MISSING_MONTHS_IN_WATER_YEAR = 2


def observed_water_year_totals(monthly, max_missing=MAX_MISSING_MONTHS_IN_WATER_YEAR):
    """
    Water-year totals from an observed monthly table (the output of
    monthly_totals_from_daily), which unlike the model data has gaps.

    Rules:
      * a water year runs 1 Sep to 31 Aug and is labelled by its starting year
      * a year with more than `max_missing` missing months is DROPPED
      * a year with 1 or 2 missing months is kept, and each missing month is filled
        with the long-term average for that calendar month. Filling with the average
        rather than zero keeps the year from looking artificially dry; such years are
        flagged so they can be marked on a chart.
      * the first and last partial years (fewer than 12 months of record) are dropped

    Returns (totals, dropped_years, part_estimated_years).
    """
    table = residual_mass(monthly)        # gives month_average per calendar month
    years = pd.Index(table.index).str.slice(0, 4).astype(int)
    months = pd.Index(table.index).str.slice(5, 7).astype(int)
    water_year = np.where(months >= WATER_YEAR_START_MONTH, years, years - 1)

    filled = table["total"].where(table["complete"], table["month_average"])
    frame = pd.DataFrame({
        "value": filled.values,
        "missing": (~table["complete"]).values,
        "water_year": water_year,
    })

    grouped = frame.groupby("water_year").agg(
        total=("value", "sum"),
        months=("value", "size"),
        missing=("missing", "sum"),
    )
    whole = grouped[grouped["months"] == 12]          # drop the partial first/last years
    keep = whole[whole["missing"] <= max_missing]
    dropped = sorted(whole[whole["missing"] > max_missing].index.tolist())
    part_estimated = sorted(keep[keep["missing"] > 0].index.tolist())
    totals = keep["total"].rename("rain_mm")
    totals.index.name = "water_year"
    return totals, dropped, part_estimated


def plot_observed_anomaly_bars(station=TI_TREE_STATION, folder=None, place=None):
    """
    Observed water-year rainfall as anomalies, drawn like slides 28-30 but for a real
    rain gauge: blue years above the station's long-term mean, magenta below, with the
    10-year trailing mean shown on the same axis.

    The reference here is the station's own long-term mean over the water years kept,
    not 1985-2014, because the record only starts in 1987.
    """
    import plotly.graph_objects as go

    monthly = monthly_totals_from_daily(load_station_daily(station, folder))
    totals, dropped, part_estimated = observed_water_year_totals(monthly)
    if totals.empty:
        raise ValueError(f"No complete water years for station {station}")

    baseline = float(totals.mean())
    anomaly = totals - baseline
    rolling = totals.rolling(window=MOVING_MEAN_WINDOW,
                             min_periods=MOVING_MEAN_WINDOW).mean() - baseline

    name = place or STATION_NAMES.get(station, station)
    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=anomaly.index, y=anomaly.values, width=0.6, showlegend=False,
        marker_color=[COLOUR_WETTER if v >= 0 else COLOUR_DRIER for v in anomaly.values],
        # Years that needed a month filled are outlined so they are not read as solid fact.
        marker_line=dict(
            color=["#000000" if y in part_estimated else "rgba(0,0,0,0)" for y in anomaly.index],
            width=[1.2 if y in part_estimated else 0 for y in anomaly.index]),
        hovertemplate="Water year %{x}<br>%{y:+.0f} mm vs the long-term mean<extra></extra>",
    ))
    figure.add_trace(go.Scatter(
        x=rolling.index, y=rolling.values, mode="lines",
        name=f"{MOVING_MEAN_WINDOW}-year moving mean",
        line=dict(color=COLOUR_LINE, width=1.8),
        hovertemplate="%{x}: %{y:+.0f} mm<extra></extra>",
    ))

    subtitle = (f"Blue years are wetter than the {totals.index.min()}-{totals.index.max()} "
                f"average of {baseline:.0f} mm, magenta years are drier. Observed rainfall, "
                f"not a model: this is what the gauge recorded.")
    figure.update_layout(
        title=dict(
            text=f"<span style='font-size:17px'>{name} ({station}): observed water-year "
                 f"rainfall</span><br>"
                 f"<span style='font-size:11.5px;color:{COLOUR_SUBTITLE}'>{subtitle}</span>",
            x=0.01, xanchor="left", y=0.96, yanchor="top"),
        bargap=0.35,
        legend=dict(orientation="h", x=0.02, y=1.0, xanchor="left", yanchor="top",
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title="Water year (1 September start)", dtick=5, showgrid=False,
                   showline=True, linecolor="#000000", ticks="outside", ticklen=4),
        yaxis=dict(title=f"Difference from the<br>long-term average (mm)",
                   showgrid=True, gridcolor=COLOUR_GRID,
                   zeroline=True, zerolinecolor="#000000",
                   showline=True, linecolor="#000000", ticks="outside", ticklen=4),
        height=520, width=1000,
    )

    pieces = [f"Water years with more than {MAX_MISSING_MONTHS_IN_WATER_YEAR} missing months "
              f"are excluded"]
    pieces.append(f"excluded: {', '.join(str(y) for y in dropped)}" if dropped
                  else "none were excluded")
    if part_estimated:
        pieces.append(f"outlined bars had 1-2 months filled with that month's long-term "
                      f"average: {', '.join(str(y) for y in part_estimated)}")
    return _base_layout(figure, footnote=". ".join(pieces) + ".")


# --- river flow -------------------------------------------------------------
#
# The flow file is NOT on a fixed time step, so "seconds in the interval" has to be
# worked out per reading:
#   * units are cubic metres per second (from the file header)
#   * 1974-2009 is sparse spot readings (a few thousand in 35 years, gaps up to 438 days)
#   * 2010-2026 is 10-minute telemetry (median interval 600 s), which is 98% of the rows
#   * interpolation type is 102 (linear) for all but 2 rows, so the volume between two
#     readings is the trapezoid between them: (q1 + q2) / 2 * seconds between them
# Because of that split, only the telemetry years produce trustworthy monthly volumes;
# the early years are flagged missing by the coverage rule below.

# A day counts as covered when no gap longer than this sits inside or across it.
MAX_FLOW_GAP_HOURS = 24


def load_flow(station=FLOW_STATION, folder=None):
    """
    Read the NT water-course discharge export (header lines start with '#').

    Columns: Timestamp, Value (m3/s), Quality Code, Interpolation Type.
    Quality codes (from Datasets/StreamflowData/disclaimer.txt):
      10 = A (best available), 90 = B (compromised), 110 = C (estimate),
      140 = E (ability to represent unknown), 210 = F (not release quality / missing).
    Timestamps carry a +09:30 offset; they are converted to naive NT local time.
    """
    folder = Path(folder) if folder else FLOW_DIR
    matches = sorted(folder.glob(f"*{station}*.csv"))
    if not matches:
        raise FileNotFoundError(f"No flow file for {station} in {folder}")
    frame = pd.read_csv(matches[0], comment="#", header=None,
                        names=["timestamp", "flow_cumecs", "quality", "interpolation"])
    frame["timestamp"] = (pd.to_datetime(frame["timestamp"], format="ISO8601", utc=True)
                          .dt.tz_convert("Australia/Darwin").dt.tz_localize(None))
    frame["flow_cumecs"] = pd.to_numeric(frame["flow_cumecs"], errors="coerce")
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)


def monthly_flow_volumes(flow, max_blank_days=MAX_BLANK_DAYS,
                         max_gap_hours=MAX_FLOW_GAP_HOURS):
    """
    Irregular m3/s readings -> monthly volume in megalitres, with a 'complete' flag.

    Volume uses the trapezoidal rule over the ACTUAL seconds between readings, which is
    what interpolation type 102 (linear) means. Each interval's volume is credited to the
    month its midpoint falls in. 1 ML = 1000 m3.

    A month is complete when no more than `max_blank_days` of its days are uncovered, where
    a day is uncovered if a gap longer than `max_gap_hours` falls inside or across it.
    The share of each month's volume that carries quality code 210 ("not of release
    quality") is reported as quality_210_share, because that code dominates this file.
    """
    work = flow.dropna(subset=["flow_cumecs"]).reset_index(drop=True)
    times = work["timestamp"].to_numpy()
    values = work["flow_cumecs"].to_numpy()

    seconds = (times[1:] - times[:-1]) / np.timedelta64(1, "s")
    volume_m3 = (values[1:] + values[:-1]) / 2.0 * seconds          # trapezoid
    midpoints = times[:-1] + (times[1:] - times[:-1]) / 2
    # An interval counts as quality 210 when either end carries that code.
    quality = work["quality"].to_numpy()
    is_210 = (quality[1:] == 210) | (quality[:-1] == 210)

    intervals = pd.DataFrame({
        "month": pd.PeriodIndex(pd.DatetimeIndex(midpoints), freq="M"),
        "volume_ML": volume_m3 / 1000.0,
        "seconds": seconds,
        "gap": seconds > max_gap_hours * 3600,
        "volume_210": np.where(is_210, volume_m3 / 1000.0, 0.0),
    })
    grouped = intervals.groupby("month").agg(
        total=("volume_ML", "sum"),
        volume_210=("volume_210", "sum"),
    )

    # Count uncovered days per month: every day touched by a too-long gap, plus any day
    # outside the readings altogether.
    uncovered = {}
    gaps = intervals[intervals["gap"]]
    for start, length in zip(times[:-1][intervals["gap"].to_numpy()],
                             gaps["seconds"].to_numpy()):
        for day in pd.date_range(pd.Timestamp(start).normalize(),
                                 pd.Timestamp(start) + pd.Timedelta(seconds=length),
                                 freq="D"):
            uncovered[day.to_period("M")] = uncovered.get(day.to_period("M"), 0) + 1

    months = pd.period_range(intervals["month"].min(), intervals["month"].max(), freq="M")
    grouped = grouped.reindex(months)
    days_in_month = pd.Series([m.days_in_month for m in months], index=months)
    blank = pd.Series({m: uncovered.get(m, 0) for m in months})
    # A month with no readings at all is entirely uncovered.
    blank = blank.where(grouped["total"].notna(), days_in_month)
    grouped["blank_days"] = blank.clip(upper=days_in_month).astype(int)
    grouped["complete"] = grouped["blank_days"] <= max_blank_days
    grouped["quality_210_share"] = (grouped["volume_210"] / grouped["total"]).where(
        grouped["total"] > 0)
    grouped["total"] = grouped["total"].where(grouped["complete"])
    grouped.index = grouped.index.strftime("%Y-%m")
    grouped.index.name = "month"
    return grouped[["total", "blank_days", "complete", "quality_210_share"]]


def flow_residual_mass(station=FLOW_STATION, folder=None):
    """Flow file -> monthly volumes (ML) -> residual mass table."""
    return residual_mass(monthly_flow_volumes(load_flow(station, folder)))


# --- bore water levels ------------------------------------------------------

BORE_DIR = PROJECT_ROOT / "Datasets" / "GroundwaterHeads_20250718"
BORE_DISTANCES = PROJECT_ROOT / "bore_gauge_distances_G0280010.csv"

# A bore series is only worth plotting against the flow record if it actually spans the
# telemetry years rather than being a handful of spot readings across a long period.
BORE_MIN_YEARS_SINCE_2010 = 10
BORE_MIN_MONTHS_SINCE_2010 = 40
BORE_PREFERRED_KM = 10


def _read_export_series(path):
    """
    Read one DataSetExport CSV from Datasets/GroundwaterHeads_20250718.

    These files have a '#' title line and a free-text disclaimer line before the real
    header, so the header row is found by looking for the line starting with 'Timestamp'.
    Timestamps are written in NT local time (the header says UTC+09:30) with no offset
    attached, so they are read as naive local time, matching the rainfall and flow data.
    """
    with open(path, errors="replace") as handle:
        header_row = None
        for number, line in enumerate(handle):
            if line.startswith("Timestamp"):
                header_row = number
                break
    if header_row is None:
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, skiprows=header_row)
    value_columns = [c for c in frame.columns if c.startswith("Value")]
    if not value_columns:
        return pd.Series(dtype=float)
    times = pd.to_datetime(frame[frame.columns[0]], errors="coerce")
    values = pd.to_numeric(frame[value_columns[0]], errors="coerce")
    series = pd.Series(values.to_numpy(), index=times)
    return series[series.index.notna()].dropna().sort_index()


def bore_catalogue(kind="Water Elevation (AHD)", series="Publish"):
    """
    What bore series exist, how far each bore is from gauge G0280010, and how much data
    each one has since 2010. Returns a DataFrame sorted by distance.

    kind   - "Water Elevation (AHD)" (metres on a common datum, comparable between bores)
             or "Depth Below Ground"
    series - "Publish" (approved/telemetry, densely sampled) or "Field Visits" (manual
             spot readings, typically a handful a year)
    """
    if not BORE_DIR.exists():
        return pd.DataFrame()
    distances = {}
    if BORE_DISTANCES.exists():
        table = pd.read_csv(BORE_DISTANCES).drop_duplicates("id_or_name")
        distances = dict(zip(table["id_or_name"], table["distance_km"]))

    tag = ".Publish@" if series == "Publish" else ".Field Visits@"
    rows, seen = [], set()
    for folder in sorted(BORE_DIR.glob("LocationExport-*")):
        bore = folder.name.split("-")[1]
        for path in sorted(folder.glob("DataSetExport-*.csv")):
            if kind not in path.name or tag not in path.name:
                continue
            if bore in seen:            # one bore is exported twice; keep the first
                continue
            values = _read_export_series(path)
            if values.empty:
                continue
            seen.add(bore)
            recent = values[values.index >= "2010-01-01"]
            months = recent.index.to_period("M").nunique() if len(recent) else 0
            rows.append({
                "bore": bore,
                "distance_km": distances.get(bore),
                "readings": len(values),
                "start": values.index.min().date(),
                "end": values.index.max().date(),
                "years": round((values.index.max() - values.index.min()).days / 365.25, 1),
                "readings_since_2010": len(recent),
                "months_since_2010": months,
                "years_since_2010": (round((recent.index.max() - recent.index.min()).days / 365.25, 1)
                                     if len(recent) > 1 else 0.0),
                "path": path,
            })
    frame = pd.DataFrame(rows)
    return frame.sort_values("distance_km", na_position="last").reset_index(drop=True)


def choose_bores(limit=3, kind="Water Elevation (AHD)", series="Publish"):
    """
    Pick up to `limit` bores: nearest to gauge G0280010 first, keeping only those whose
    record actually spans BORE_MIN_YEARS_SINCE_2010 years since 2010 with data in at
    least BORE_MIN_MONTHS_SINCE_2010 separate months.

    Returns (chosen DataFrame, full catalogue). The chosen frame is empty if none qualify.
    """
    catalogue = bore_catalogue(kind=kind, series=series)
    if catalogue.empty:
        return catalogue, catalogue
    qualifies = (
        (catalogue["years_since_2010"] >= BORE_MIN_YEARS_SINCE_2010)
        & (catalogue["months_since_2010"] >= BORE_MIN_MONTHS_SINCE_2010)
    )
    return catalogue[qualifies].head(limit).reset_index(drop=True), catalogue


def load_bore_series(bore, kind="Water Elevation (AHD)", series="Publish"):
    """The water-level series for one bore, as a pandas Series indexed by timestamp."""
    catalogue = bore_catalogue(kind=kind, series=series)
    match = catalogue[catalogue["bore"] == bore]
    if match.empty:
        raise FileNotFoundError(f"No {series} {kind} series for bore {bore}")
    return _read_export_series(match.iloc[0]["path"])


def bore_monthly_level(bore, kind="Water Elevation (AHD)", series="Publish"):
    """
    Monthly mean water level for one bore. Months with no reading are left as NaN, so a
    chart drawn from this shows a break rather than a straight line across a gap.
    """
    values = load_bore_series(bore, kind=kind, series=series)
    monthly = values.groupby(values.index.to_period("M")).mean()
    full = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
    monthly = monthly.reindex(full)
    monthly.index = monthly.index.strftime("%Y-%m")
    monthly.index.name = "month"
    return monthly.rename("level_m")


def plot_rainfall_and_flow(rain_table, flow_table, rain_title, flow_title,
                           caption=None, credit=CREDIT_TEXT):
    """
    Two stacked residual mass panels sharing one x axis: rainfall on top, river flow
    below, restricted to the months both records cover.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    shared = sorted(set(rain_table.index) & set(flow_table.index))
    if not shared:
        raise ValueError("The rainfall and flow records do not overlap")
    rain = rain_table.loc[shared]
    flow = flow_table.loc[shared]
    # Recompute the running totals over the shared window only, so both curves start at 0.
    rain = rain.assign(cumulative=rain["residual"].cumsum())
    flow = flow.assign(cumulative=flow["residual"].cumsum())
    x = [_month_to_timestamp(m) for m in shared]

    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.11,
                           subplot_titles=(rain_title, flow_title),
                           specs=[[{"secondary_y": True}], [{"secondary_y": True}]])

    for row, (table, bar_name, line_name, bar_colour) in enumerate(
            [(rain, "Monthly rainfall (mm)", "Cumulative residual (mm)", COLOUR_WETTER),
             (flow, "Monthly flow (ML)", "Cumulative residual (ML)", "#6BA4CF")], start=1):
        figure.add_trace(go.Bar(x=x, y=table["total"], name=bar_name, marker_color=bar_colour,
                                opacity=0.55, showlegend=False), row=row, col=1,
                         secondary_y=False)
        figure.add_trace(go.Scatter(x=x, y=table["cumulative"], name=line_name, mode="lines",
                                    line=dict(color=COLOUR_LINE, width=1.8), showlegend=False),
                         row=row, col=1, secondary_y=True)
        for first, last in gap_bands(table):
            figure.add_shape(type="rect", xref="x", yref="y domain", row=row, col=1,
                             layer="below", line_width=0, fillcolor=COLOUR_DRIER, opacity=0.10,
                             x0=_month_to_timestamp(first) - pd.Timedelta(days=15),
                             x1=_month_to_timestamp(last) + pd.Timedelta(days=15), y0=0, y1=1)
        figure.update_yaxes(title_text=bar_name, row=row, col=1, secondary_y=False,
                            gridcolor=COLOUR_GRID, showline=True, linecolor="#000000")
        figure.update_yaxes(title_text=line_name, row=row, col=1, secondary_y=True,
                            showgrid=False)

    figure.update_xaxes(showline=True, linecolor="#000000", showgrid=False, ticks="outside")
    figure.update_layout(height=760, width=1000, bargap=0.1)
    for note in figure.layout.annotations:
        note.font.size = 13
    return _base_layout(figure, credit=credit, footnote=caption)


def plot_rain_flow_bores(rain_table, flow_table, bore_levels, start="2010-01",
                         caption=None, credit=CREDIT_TEXT):
    """
    Three stacked panels on one x axis: rainfall residual mass, river flow residual mass,
    and bore water level. `bore_levels` is {bore: monthly Series of level in m AHD}.

    Gaps are shown as BREAKS in the lines, not filled: a month with no reading is left as
    NaN and plotly leaves the line open there.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    rain = rain_table[rain_table.index >= start].copy()
    flow = flow_table[flow_table.index >= start].copy()
    # Restart the running totals at the window, so both curves begin at zero here.
    rain["cumulative"] = rain["residual"].cumsum()
    flow["cumulative"] = flow["residual"].cumsum()

    figure = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("Rainfall residual mass - Territory Grape Farm (015643)",
                        "River flow residual mass - Woodforde River at Arden Soak (G0280010)",
                        "Bore water level (m AHD) - gaps left open, not filled"),
        specs=[[{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": False}]],
        row_heights=[0.32, 0.32, 0.36],
    )

    for row, (table, bar_name, line_name, colour) in enumerate(
            [(rain, "Monthly rainfall (mm)", "Cumulative residual (mm)", COLOUR_WETTER),
             (flow, "Monthly flow (ML)", "Cumulative residual (ML)", "#6BA4CF")], start=1):
        x = [_month_to_timestamp(m) for m in table.index]
        figure.add_trace(go.Bar(x=x, y=table["total"], name=bar_name, marker_color=colour,
                                opacity=0.5, showlegend=False), row=row, col=1,
                         secondary_y=False)
        figure.add_trace(go.Scatter(x=x, y=table["cumulative"], name=line_name, mode="lines",
                                    line=dict(color=COLOUR_LINE, width=1.6), showlegend=False),
                         row=row, col=1, secondary_y=True)
        for first, last in gap_bands(table):
            figure.add_shape(type="rect", xref="x", yref="y domain", row=row, col=1,
                             layer="below", line_width=0, fillcolor=COLOUR_DRIER, opacity=0.10,
                             x0=_month_to_timestamp(first) - pd.Timedelta(days=15),
                             x1=_month_to_timestamp(last) + pd.Timedelta(days=15), y0=0, y1=1)
        figure.update_yaxes(title_text=bar_name, row=row, col=1, secondary_y=False,
                            gridcolor=COLOUR_GRID, showline=True, linecolor="#000000")
        figure.update_yaxes(title_text=line_name, row=row, col=1, secondary_y=True,
                            showgrid=False)

    palette = ["#1B6CA8", "#C2567A", "#4F8F3A"]
    for number, (bore, levels) in enumerate(bore_levels.items()):
        part = levels[levels.index >= start]
        figure.add_trace(go.Scatter(
            x=[_month_to_timestamp(m) for m in part.index], y=part.values,
            name=bore, mode="lines+markers", connectgaps=False,     # gaps stay open
            line=dict(color=palette[number % len(palette)], width=1.5),
            marker=dict(size=3),
            hovertemplate=f"{bore}<br>%{{x|%b %Y}}<br>%{{y:.2f}} m AHD<extra></extra>",
        ), row=3, col=1)
    figure.update_yaxes(title_text="Water level (m AHD)", row=3, col=1,
                        gridcolor=COLOUR_GRID, showline=True, linecolor="#000000")

    figure.update_xaxes(showline=True, linecolor="#000000", showgrid=False, ticks="outside")
    figure.update_layout(height=980, width=1020, bargap=0.1,
                         legend=dict(orientation="h", x=0.01, y=-0.04, xanchor="left",
                                     yanchor="top", bgcolor="rgba(0,0,0,0)"))
    for note in figure.layout.annotations:
        note.font.size = 12.5
    return _base_layout(figure, credit=credit, footnote=caption)


def plot_rainfall_and_bores(rain_table, bore_levels, caption=None, credit=CREDIT_TEXT):
    """
    Two panels over the whole shared record (from 1987): rainfall residual mass on top,
    bore water levels below. Gaps in the bore series are left open.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
        subplot_titles=("Rainfall residual mass - Territory Grape Farm (015643), 1987 onwards",
                        "Bore water level (m AHD), full record - gaps left open"),
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )
    x = [_month_to_timestamp(m) for m in rain_table.index]
    figure.add_trace(go.Bar(x=x, y=rain_table["total"], marker_color=COLOUR_WETTER,
                            opacity=0.5, showlegend=False), row=1, col=1, secondary_y=False)
    figure.add_trace(go.Scatter(x=x, y=rain_table["cumulative"], mode="lines",
                                line=dict(color=COLOUR_LINE, width=1.6), showlegend=False),
                     row=1, col=1, secondary_y=True)
    for first, last in gap_bands(rain_table):
        figure.add_shape(type="rect", xref="x", yref="y domain", row=1, col=1, layer="below",
                         line_width=0, fillcolor=COLOUR_DRIER, opacity=0.10,
                         x0=_month_to_timestamp(first) - pd.Timedelta(days=15),
                         x1=_month_to_timestamp(last) + pd.Timedelta(days=15), y0=0, y1=1)
    figure.update_yaxes(title_text="Monthly rainfall (mm)", row=1, col=1, secondary_y=False,
                        gridcolor=COLOUR_GRID, showline=True, linecolor="#000000")
    figure.update_yaxes(title_text="Cumulative residual (mm)", row=1, col=1, secondary_y=True,
                        showgrid=False)

    palette = ["#1B6CA8", "#C2567A", "#4F8F3A"]
    for number, (bore, levels) in enumerate(bore_levels.items()):
        figure.add_trace(go.Scatter(
            x=[_month_to_timestamp(m) for m in levels.index], y=levels.values, name=bore,
            mode="lines+markers", connectgaps=False,
            line=dict(color=palette[number % len(palette)], width=1.5), marker=dict(size=3),
            hovertemplate=f"{bore}<br>%{{x|%b %Y}}<br>%{{y:.2f}} m AHD<extra></extra>",
        ), row=2, col=1)
    figure.update_yaxes(title_text="Water level (m AHD)", row=2, col=1,
                        gridcolor=COLOUR_GRID, showline=True, linecolor="#000000")
    figure.update_xaxes(showline=True, linecolor="#000000", showgrid=False, ticks="outside")
    figure.update_layout(height=760, width=1020, bargap=0.1,
                         legend=dict(orientation="h", x=0.01, y=-0.06, xanchor="left",
                                     yanchor="top", bgcolor="rgba(0,0,0,0)"))
    for note in figure.layout.annotations:
        note.font.size = 12.5
    return _base_layout(figure, credit=credit, footnote=caption)


# --- lag analysis -----------------------------------------------------------
#
# Why anomalies and differences rather than the raw series:
#   * raw monthly rainfall and raw bore level both carry a strong seasonal cycle, so
#     correlating them mostly measures "both go up in summer", not a real response
#   * a bore level that drifts down for years will correlate with anything else that
#     drifts, which is spurious
# So we use the rainfall ANOMALY (monthly total minus that calendar month's mean) against
# the CHANGE in bore level from one month to the next. Both have the seasonal cycle and
# the slow trend largely removed, so what is left is "did an unusually wet month coincide
# with the water table rising".

MAX_LAG_MONTHS = 12

# A correlation from a handful of months means nothing: with 4 paired months an r of -0.9
# is easy to get by chance. Lags with fewer than this many pairs are shown but are never
# chosen as the strongest, and are called out on the chart.
MIN_PAIRED_MONTHS = 24


def monthly_anomaly(table, value_column="total"):
    """Monthly value minus the long-term average for that calendar month (missing -> NaN)."""
    filled = residual_mass(table, value_column=value_column)
    anomaly = filled[value_column] - filled["month_average"]
    return anomaly.where(filled["complete"]).rename("anomaly")


def level_change(levels):
    """
    Month-to-month change in bore level (metres).

    Only consecutive months count: if a month is missing, the change across that gap is
    left as NaN rather than spreading several months of movement over one step.
    """
    index = pd.PeriodIndex(levels.index, freq="M")
    ordered = pd.Series(levels.to_numpy(), index=index).sort_index()
    change = ordered.diff()
    consecutive = ordered.index.to_series().diff().apply(lambda d: getattr(d, "n", None) == 1)
    change = change.where(consecutive.to_numpy())
    change.index = change.index.strftime("%Y-%m")
    change.index.name = "month"
    return change.rename("level_change_m")


def lag_correlations(driver, response, max_lag=MAX_LAG_MONTHS):
    """
    Correlate `driver` (rainfall or flow anomaly) leading `response` (bore level change)
    by 0..max_lag months.

    Lag k means: this month's level change is compared with the anomaly k months earlier.
    Returns a DataFrame with the lag, Pearson r, and the number of paired months.
    """
    driver_index = pd.PeriodIndex(driver.index, freq="M")
    driver = pd.Series(driver.to_numpy(), index=driver_index).sort_index()
    response_index = pd.PeriodIndex(response.index, freq="M")
    response = pd.Series(response.to_numpy(), index=response_index).sort_index()

    rows = []
    for lag in range(max_lag + 1):
        shifted = driver.copy()
        shifted.index = shifted.index + lag          # move the driver forward in time
        paired = pd.concat([shifted.rename("driver"), response.rename("response")],
                           axis=1, join="inner").dropna()
        rows.append({
            "lag_months": lag,
            "r": paired["driver"].corr(paired["response"]) if len(paired) > 2 else np.nan,
            "n_months": len(paired),
        })
    return pd.DataFrame(rows)


def plot_lag_correlation(results, title, subtitle="", credit=CREDIT_TEXT):
    """
    Bar chart of correlation against lag, with the strongest lag marked.
    Carries the plain warning that correlation is not causation.
    """
    import plotly.graph_objects as go

    usable = results.dropna(subset=["r"])
    if usable.empty:
        raise ValueError("No lag has enough paired months to correlate")
    # Only lags with enough paired months can be called the strongest.
    reliable = usable[usable["n_months"] >= MIN_PAIRED_MONTHS]
    best = (reliable.loc[reliable["r"].abs().idxmax()] if not reliable.empty else None)

    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=results["lag_months"], y=results["r"],
        marker_color=[COLOUR_WETTER if v >= 0 else COLOUR_DRIER for v in results["r"].fillna(0)],
        marker_line=dict(
            color=["#000000" if (best is not None and lag == best["lag_months"])
                   else "rgba(0,0,0,0)" for lag in results["lag_months"]],
            width=[2 if (best is not None and lag == best["lag_months"]) else 0
                   for lag in results["lag_months"]]),
        # Bars built on too few months are faded, so they are not read as findings.
        opacity=1.0,
        customdata=results["n_months"],
        hovertemplate="Lag %{x} months<br>r = %{y:.3f}<br>%{customdata} paired months<extra></extra>",
        showlegend=False,
    ))
    if best is not None:
        figure.add_annotation(
            x=best["lag_months"], y=best["r"], text=f"strongest: lag {int(best['lag_months'])}, "
            f"r = {best['r']:.2f} (n={int(best['n_months'])})", showarrow=True, arrowhead=0,
            ax=0, ay=-30 if best["r"] >= 0 else 30, font=dict(size=11))

    head = f"<span style='font-size:16px'>{title}</span>"
    if subtitle:
        head += f"<br><span style='font-size:11.5px;color:{COLOUR_SUBTITLE}'>{subtitle}</span>"
    figure.update_layout(
        title=dict(text=head, x=0.01, xanchor="left", y=0.95, yanchor="top"),
        xaxis=dict(title="Rainfall or flow leads the bore by (months)", dtick=1,
                   showgrid=False, showline=True, linecolor="#000000", ticks="outside"),
        yaxis=dict(title="Correlation (Pearson r)", gridcolor=COLOUR_GRID,
                   zeroline=True, zerolinecolor="#000000", showline=True,
                   linecolor="#000000", ticks="outside"),
        height=440, width=900, bargap=0.3,
    )
    thin = results[results["n_months"] < MIN_PAIRED_MONTHS]["lag_months"].tolist()
    note = ("Correlation is not causation; the bore series are short and gappy, so these "
            "numbers are a hint about timing, not proof. Paired months per lag: "
            f"{int(results['n_months'].min())}-{int(results['n_months'].max())}.")
    if thin:
        note += (f" Lags {', '.join(str(int(l)) for l in thin)} rest on fewer than "
                 f"{MIN_PAIRED_MONTHS} paired months and are not treated as findings.")
    if best is None:
        note += (f" No lag reaches {MIN_PAIRED_MONTHS} paired months, so no strongest lag "
                 "is marked.")
    return _base_layout(figure, credit=credit, footnote=note)


# --- wet and dry seasons ----------------------------------------------------
#
# In the Ti Tree region almost all rain falls in the summer monsoon months, so splitting
# the year into a wet half and a dry half says more than an annual total. The wet season
# (Nov-Apr) straddles the new year, so it is labelled by the year it STARTS in: the wet
# season labelled 2015 runs Nov 2015 to Apr 2016. The dry season labelled 2015 is
# May-Oct 2015, which falls inside that same water year.

WET_SEASON_MONTHS = [11, 12, 1, 2, 3, 4]
DRY_SEASON_MONTHS = [5, 6, 7, 8, 9, 10]


def _season_frame(index_months, values):
    """Attach a season and a season-year label to a monthly series."""
    months = np.array([int(m[5:7]) for m in index_months])
    years = np.array([int(m[:4]) for m in index_months])
    wet = np.isin(months, WET_SEASON_MONTHS)
    # Nov and Dec belong to the wet season labelled with the current year; Jan-Apr belong
    # to the wet season that started the previous November.
    season_year = np.where(wet & (months <= 4), years - 1, years)
    return pd.DataFrame({"value": values, "wet": wet, "season_year": season_year,
                         "month": months})


def seasonal_totals_observed(station=TI_TREE_STATION, folder=None):
    """
    Observed wet-season (Nov-Apr) and dry-season (May-Oct) rainfall per year.

    A season is kept only if all 6 of its months are present; a season with any missing
    month is still returned but flagged, so it can be marked on the chart rather than
    quietly plotted as if it were complete.
    Returns a DataFrame indexed by season year with wet, dry, wet_missing, dry_missing.
    """
    monthly = monthly_totals_from_daily(load_station_daily(station, folder))
    frame = _season_frame(list(monthly.index), monthly["total"].to_numpy())
    frame["missing"] = ~monthly["complete"].to_numpy()

    out = {}
    for wet_flag, name in [(True, "wet"), (False, "dry")]:
        part = frame[frame["wet"] == wet_flag]
        grouped = part.groupby("season_year").agg(
            total=("value", "sum"), months=("value", "size"), missing=("missing", "sum"))
        grouped = grouped[grouped["months"] == 6]          # drop part-seasons at the ends
        out[name] = grouped["total"]
        out[f"{name}_missing"] = grouped["missing"]
    return pd.DataFrame(out).dropna(how="all")


def seasonal_totals_model(model_run, location="Ti Tree", data_dir=None):
    """Wet-season and dry-season rainfall per year for one model run (no gaps to handle)."""
    monthly = load_monthly_pr(model_run, location, data_dir=data_dir)
    frame = _season_frame(list(monthly.index), monthly.to_numpy())
    out = {}
    for wet_flag, name in [(True, "wet"), (False, "dry")]:
        part = frame[frame["wet"] == wet_flag]
        grouped = part.groupby("season_year").agg(total=("value", "sum"),
                                                  months=("value", "size"))
        out[name] = grouped[grouped["months"] == 6]["total"]
    return pd.DataFrame(out)


def plot_seasonal(observed, model_tables, location="Ti Tree", start_year=1987,
                  end_year=2099, credit=CREDIT_TEXT):
    """
    Wet-season against dry-season rainfall per year: observed bars for the gauge, with
    each model's wet season drawn as a line over the top.

    Observed seasons that are short a month are outlined, so a bar that looks dry because
    data is missing can be told apart from a genuinely dry season.
    """
    import plotly.graph_objects as go

    observed = observed[(observed.index >= start_year) & (observed.index <= end_year)]
    figure = go.Figure()

    wet_flag = observed["wet_missing"] > 0
    dry_flag = observed["dry_missing"] > 0
    figure.add_trace(go.Bar(
        x=observed.index, y=observed["wet"], name="Observed wet season (Nov-Apr)",
        marker_color=COLOUR_WETTER,
        marker_line=dict(color=["#000000" if f else "rgba(0,0,0,0)" for f in wet_flag],
                         width=[1.5 if f else 0 for f in wet_flag]),
        hovertemplate="Wet season %{x}-%{customdata}<br>%{y:.0f} mm<extra></extra>",
        customdata=[str(y + 1)[-2:] for y in observed.index],
    ))
    figure.add_trace(go.Bar(
        x=observed.index, y=observed["dry"], name="Observed dry season (May-Oct)",
        marker_color="#C9A227",
        marker_line=dict(color=["#000000" if f else "rgba(0,0,0,0)" for f in dry_flag],
                         width=[1.5 if f else 0 for f in dry_flag]),
        hovertemplate="Dry season %{x}<br>%{y:.0f} mm<extra></extra>",
    ))

    palette = ["#1B6CA8", "#C2567A", "#4F8F3A"]
    for number, (label, table) in enumerate(model_tables.items()):
        part = table[(table.index >= start_year) & (table.index <= end_year)]
        figure.add_trace(go.Scatter(
            x=part.index, y=part["wet"], name=f"{label} wet season", mode="lines",
            line=dict(color=palette[number % len(palette)], width=1.3, dash="solid"),
            opacity=0.85,
            hovertemplate=f"{label}<br>wet season %{{x}}<br>%{{y:.0f}} mm<extra></extra>",
        ))

    missing_years = sorted(set(observed.index[wet_flag]) | set(observed.index[dry_flag]))
    figure.update_layout(
        title=dict(
            text=f"<span style='font-size:16px'>{location}: wet season (Nov-Apr) and dry "
                 f"season (May-Oct) rainfall</span><br>"
                 f"<span style='font-size:11.5px;color:{COLOUR_SUBTITLE}'>Bars are the gauge "
                 f"at Territory Grape Farm (015643); lines are the wet season in three "
                 f"climate models at the Ti Tree grid cell. Seasons are labelled by the year "
                 f"they start in.</span>",
            x=0.01, xanchor="left", y=0.95, yanchor="top"),
        barmode="group", bargap=0.2, bargroupgap=0.05,
        legend=dict(orientation="h", x=0.01, y=1.0, xanchor="left", yanchor="bottom",
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(title="Season start year", dtick=5, showgrid=False, showline=True,
                   linecolor="#000000", ticks="outside"),
        yaxis=dict(title="Rainfall (mm)", gridcolor=COLOUR_GRID, showline=True,
                   linecolor="#000000", ticks="outside"),
        height=520, width=1020,
    )
    note = "Outlined bars are seasons with at least one missing month in the gauge record"
    note += (f": {', '.join(str(y) for y in missing_years)}." if missing_years else ".")
    return _base_layout(figure, credit=credit, footnote=note)


def rainfall_residual_mass(station=TI_TREE_STATION, folder=None):
    """Convenience: BOM daily file -> monthly totals -> residual mass table."""
    return residual_mass(monthly_totals_from_daily(load_station_daily(station, folder)))


# ---------------------------------------------------------
# 6. STREAMLIT TAB
# ---------------------------------------------------------

def render_climate_tab(key_prefix="climate"):
    """
    Draw the whole climate section inside a Streamlit app.

    Designed to be dropped into a tab later:

        import climate_models
        with tab:
            climate_models.render_climate_tab()

    Missing data files produce a plain message, never a traceback. `key_prefix` keeps the
    widget keys unique if this is ever shown twice on one page.
    """
    import streamlit as st

    st.subheader("Climate model projections (CMIP6, SSP2-4.5)")
    st.caption(
        "Water-year rainfall (1 September to 31 August) from CMIP6 climate models, for the "
        "single model grid cell nearest each location. Charts follow the style of A/Prof "
        "Dylan Irvine's slides; the numbers are computed from our own downloads."
    )

    if not DATA_DIR.exists():
        st.warning(
            f"No climate data folder yet ({DATA_DIR}).\n\n"
            "Run this first:  `python climate/download_cmip6_pr.py --download`"
        )
        return

    location = st.selectbox("Location", list(LOCATIONS), key=f"{key_prefix}_location")

    good, bad = usable_runs(location)
    if not good:
        st.warning(f"No usable model runs for {location}.")
        if bad:
            st.write({label: why for label, why in sorted(bad.items())})
        return
    if bad:
        with st.expander(f"{len(bad)} model run(s) not shown for {location}"):
            for label, why in sorted(bad.items()):
                st.write(f"- **{label}**: {why}")
    if UNMATCHED_SLIDE_RUNS:
        with st.expander("Slide runs we could not identify"):
            st.write("These rows on the supervisor's slide 31 are marked \"coupled\". "
                     "We could not tell which published run they are, so they are not shown.")
            for name in UNMATCHED_SLIDE_RUNS:
                st.write(f"- {name}")

    # --- anomaly bars, one model at a time (slides 28-30) ---
    st.markdown("#### Water-year rainfall, one model run at a time")
    default = good.index("ACCESS-ESM1-5 r6 (v2105)") if "ACCESS-ESM1-5 r6 (v2105)" in good else 0
    model_run = st.selectbox("Model run", good, index=default, key=f"{key_prefix}_run")
    try:
        st.plotly_chart(plot_anomaly_bars(model_run, location), use_container_width=True)
    except Exception as exc:                       # never show a traceback to the user
        st.error(f"Could not draw the chart for {model_run} at {location}: {exc}")

    # --- all models together (slide 31) ---
    st.markdown("#### Every model side by side")
    try:
        st.plotly_chart(plot_wetter_or_drier(location), use_container_width=True)
    except Exception as exc:
        st.error(f"Could not draw the model comparison: {exc}")

    # --- observed residual mass ---
    st.markdown("#### Observed records: residual mass")
    st.caption(
        "Residual mass after the BOM AWRA technical supplement: each month's total minus "
        "the long-term average for that same calendar month, accumulated. A rising line is "
        "a wet run, a falling line a dry run. Shaded bands are months treated as missing "
        f"(more than {MAX_BLANK_DAYS} blank days); they add 0 to the running total."
    )
    try:
        rain = rainfall_residual_mass()
        station = STATION_NAMES.get(TI_TREE_STATION, TI_TREE_STATION)
        st.plotly_chart(
            plot_residual_mass(rain, f"Rainfall residual mass - {station} ({TI_TREE_STATION})"),
            use_container_width=True)
    except FileNotFoundError as exc:
        st.info(f"Rainfall residual mass not shown: {exc}")
        rain = None
    except Exception as exc:
        st.error(f"Could not build the rainfall residual mass: {exc}")
        rain = None

    try:
        flow = flow_residual_mass()
    except FileNotFoundError as exc:
        st.info(f"River flow not shown: {exc}")
        flow = None
    except Exception as exc:
        st.error(f"Could not build the river flow residual mass: {exc}")
        flow = None

    # --- observed water years (slide style, real gauge) ---
    if rain is not None:
        try:
            st.plotly_chart(plot_observed_anomaly_bars(), use_container_width=True)
        except Exception as exc:
            st.error(f"Could not draw the observed water-year chart: {exc}")

    if rain is not None and flow is not None:
        only_recent = st.checkbox(
            "Show 2010 onwards only (the gauge is near-continuous from 2010; "
            "earlier years are mostly spot readings)",
            value=True, key=f"{key_prefix}_recent")
        rain_part = rain[rain.index >= "2010-01"] if only_recent else rain
        flow_part = flow[flow.index >= "2010-01"] if only_recent else flow
        try:
            st.plotly_chart(
                plot_rainfall_and_flow(
                    rain_part, flow_part,
                    "Rainfall residual mass - Territory Grape Farm (015643)",
                    "River flow residual mass - Woodforde River at Arden Soak (G0280010)",
                    caption=("Rain station 015643 is about 34 km from gauge G0280010 "
                             "(computed from their coordinates).")),
                use_container_width=True)
        except Exception as exc:
            st.error(f"Could not build the comparison figure: {exc}")

    # --- bores: three-panel figure and the lag charts ---
    st.markdown("#### Bores near the gauge")
    chosen, catalogue = choose_bores()
    if catalogue.empty:
        st.info(f"No bore exports found in {BORE_DIR}.")
    elif chosen.empty:
        st.info(
            f"No bore has at least {BORE_MIN_YEARS_SINCE_2010} years of record since 2010 "
            f"in at least {BORE_MIN_MONTHS_SINCE_2010} separate months, so the bore panels "
            "are not shown."
        )
    else:
        picked = ", ".join(f"{row.bore} ({row.distance_km:.1f} km)"
                           for row in chosen.itertuples())
        st.caption(
            f"Chosen by distance to gauge {FLOW_STATION}, keeping only bores with a long "
            f"enough record since 2010: {picked}. Series used: Water Elevation (AHD), "
            "\"Publish\", which is the approved densely-sampled series on a common datum."
        )
        if chosen["distance_km"].min() > BORE_PREFERRED_KM:
            st.caption(
                f"Note: no bore within {BORE_PREFERRED_KM} km has a long enough record, so "
                f"the nearest usable bore is {chosen['distance_km'].min():.1f} km away."
            )
        levels = {}
        for bore in chosen["bore"]:
            try:
                levels[bore] = bore_monthly_level(bore)
            except Exception as exc:
                st.warning(f"Could not read bore {bore}: {exc}")

        if levels and rain is not None and flow is not None:
            caption = (f"Bores {picked}. Rain station {TI_TREE_STATION} is about 34 km from "
                       f"gauge {FLOW_STATION}. Gaps in the bore lines are left open.")
            try:
                st.plotly_chart(plot_rain_flow_bores(rain, flow, levels, caption=caption),
                                use_container_width=True)
            except Exception as exc:
                st.error(f"Could not build the three-panel figure: {exc}")
            try:
                st.plotly_chart(plot_rainfall_and_bores(rain, levels, caption=caption),
                                use_container_width=True)
            except Exception as exc:
                st.error(f"Could not build the long-period figure: {exc}")

        # --- lag charts ---
        if levels and rain is not None:
            st.markdown("#### How long after rain does the water table move?")
            bore = st.selectbox("Bore", list(levels), key=f"{key_prefix}_bore")
            driver_name = st.radio("Compare against", ["Rainfall", "River flow"],
                                   horizontal=True, key=f"{key_prefix}_driver")
            try:
                source = rain if driver_name == "Rainfall" else flow
                if source is None:
                    st.info(f"{driver_name} is not available.")
                else:
                    driver = monthly_anomaly(source)
                    results = lag_correlations(driver, level_change(levels[bore]))
                    st.plotly_chart(
                        plot_lag_correlation(
                            results, f"{bore} water-level change vs {driver_name.lower()} anomaly",
                            f"Monthly {driver_name.lower()} anomaly leading the month-to-month "
                            "change in bore level."),
                        use_container_width=True)
                    reliable = results[results["n_months"] >= MIN_PAIRED_MONTHS].dropna(subset=["r"])
                    if reliable.empty:
                        st.warning(
                            f"No lag reaches {MIN_PAIRED_MONTHS} paired months for this "
                            "combination, so nothing here should be read as a finding.")
            except Exception as exc:
                st.error(f"Could not build the lag chart: {exc}")

    # --- wet and dry seasons ---
    st.markdown("#### Wet season against dry season")
    try:
        observed = seasonal_totals_observed()
        runs = [r for r in ["ACCESS-ESM1-5 r6 (v2105)", "GFDL-ESM4", "NorESM2-MM"]
                if r in available_runs("Ti Tree")]
        tables = {r: seasonal_totals_model(r, "Ti Tree") for r in runs}
        to_2099 = st.checkbox("Show the model lines out to 2099", value=False,
                              key=f"{key_prefix}_season_future")
        st.plotly_chart(
            plot_seasonal(observed, tables, end_year=2099 if to_2099 else 2025),
            use_container_width=True)
    except FileNotFoundError as exc:
        st.info(f"Seasonal chart not shown: {exc}")
    except Exception as exc:
        st.error(f"Could not build the seasonal chart: {exc}")


# ---------------------------------------------------------
# RUN DIRECTLY: report what data is present
# ---------------------------------------------------------

def _summary():
    print(f"Data folder: {DATA_DIR}")
    for location in LOCATIONS:
        have = available_runs(location)
        print(f"\n{location}: {len(have)}/{len(REGISTRY)} runs have both experiments")
        for label in have:
            wy = water_year_totals(load_monthly_pr(label, location))
            change = pct_change(wy)
            print(f"  {label:28} {wy.index.min()}-{wy.index.max()}  "
                  f"ref mean {change['ref_mean_mm']:7.0f} mm  "
                  f"{change['mean_pct']:+6.1f}% mean  {change['median_pct']:+6.1f}% median")
        note = missing_message(location)
        if note:
            print(note)
    print("\nSlide-31 runs we could not identify (not built):")
    for name in UNMATCHED_SLIDE_RUNS:
        print(f"  {name}")


if __name__ == "__main__":
    _summary()
