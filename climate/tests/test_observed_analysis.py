"""
Tests for the Batch 3 analysis functions: the observed water-year rule, the lag alignment,
the month-to-month level change, and the wet/dry season split.

Run with:
    ~/venvs/hit401_climate/bin/python -B climate/tests/test_observed_analysis.py

Every test uses a made-up series whose answer is known in advance. Nothing reads the real
data files or the network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# climate_models.py and download_cmip6_pr.py live one level up, in climate/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import climate_models as cm


def monthly_table(start, totals, missing=()):
    """
    Build the kind of table monthly_totals_from_daily returns.
    `missing` is a set of 'YYYY-MM' strings to mark as missing months.
    """
    index = pd.period_range(start, periods=len(totals), freq="M").strftime("%Y-%m")
    complete = [m not in set(missing) for m in index]
    values = [np.nan if m in set(missing) else float(v) for m, v in zip(index, totals)]
    frame = pd.DataFrame({"total": values,
                          "blank_days": [0 if c else 30 for c in complete],
                          "complete": complete}, index=pd.Index(index, name="month"))
    return frame


# ---------------------------------------------------------
# the water-year exclusion rule
# ---------------------------------------------------------

def test_water_year_with_two_missing_months_is_kept_and_filled():
    """
    Two missing months is within the limit, so the year is kept and the gaps are filled
    with that calendar month's long-term average rather than zero.
    """
    # Three water years of 10 mm every month, then break two months of the middle year.
    table = monthly_table("1999-09", [10.0] * 36, missing=["2000-10", "2000-11"])
    totals, dropped, part = cm.observed_water_year_totals(table)

    assert 2000 in totals.index                 # kept
    assert dropped == []
    assert part == [2000]                       # flagged as part-estimated
    # Every month averages 10 mm, so the filled year still totals 120, not 100.
    assert round(totals.loc[2000], 6) == 120.0


def test_water_year_with_three_missing_months_is_dropped():
    table = monthly_table("1999-09", [10.0] * 36,
                          missing=["2000-10", "2000-11", "2000-12"])
    totals, dropped, part = cm.observed_water_year_totals(table)
    assert 2000 not in totals.index
    assert dropped == [2000]
    assert part == []


def test_partial_first_and_last_water_years_are_dropped():
    """A record starting in January cannot have a complete first water year."""
    table = monthly_table("2000-01", [5.0] * 24)       # Jan 2000 - Dec 2001
    totals, _, _ = cm.observed_water_year_totals(table)
    assert list(totals.index) == [2000]                # only Sep 2000 - Aug 2001 is whole


# ---------------------------------------------------------
# month-to-month change in bore level
# ---------------------------------------------------------

def test_level_change_is_the_difference_between_consecutive_months():
    levels = pd.Series([10.0, 10.5, 10.2],
                       index=pd.Index(["2015-01", "2015-02", "2015-03"], name="month"))
    change = cm.level_change(levels)
    assert pd.isna(change.loc["2015-01"])              # nothing before the first month
    assert round(change.loc["2015-02"], 6) == 0.5
    assert round(change.loc["2015-03"], 6) == -0.3


def test_level_change_is_not_computed_across_a_gap():
    """
    Jan, then a missing Feb, then Mar. The Jan->Mar step covers two months, so it is left
    as NaN instead of being recorded as a single month's movement.
    """
    levels = pd.Series([10.0, np.nan, 12.0],
                       index=pd.Index(["2015-01", "2015-02", "2015-03"], name="month"))
    levels = levels.dropna()                            # as a real gappy series arrives
    change = cm.level_change(levels)
    assert pd.isna(change.loc["2015-03"])


# ---------------------------------------------------------
# lag alignment
# ---------------------------------------------------------

def test_lag_correlation_finds_a_known_three_month_lag():
    """
    Build a series where the bore responds exactly 3 months after the rain, and check the
    correlation peaks at lag 3.
    """
    rng = np.random.default_rng(0)
    months = pd.period_range("2000-01", periods=200, freq="M").strftime("%Y-%m")
    rain = pd.Series(rng.normal(size=200), index=pd.Index(months, name="month"))

    # The response at month t is the rain at t-3, plus a little noise.
    response_values = np.full(200, np.nan)
    response_values[3:] = rain.to_numpy()[:-3] + rng.normal(scale=0.05, size=197)
    response = pd.Series(response_values, index=pd.Index(months, name="month")).dropna()

    results = cm.lag_correlations(rain, response, max_lag=12)
    best = results.loc[results["r"].abs().idxmax()]

    assert int(best["lag_months"]) == 3
    assert best["r"] > 0.9
    # The other lags should be nowhere near as strong.
    others = results[results["lag_months"] != 3]["r"].abs().max()
    assert others < 0.5


def test_lag_zero_matches_the_same_month():
    """With no lag the driver and response line up month for month."""
    months = pd.period_range("2000-01", periods=60, freq="M").strftime("%Y-%m")
    values = np.sin(np.arange(60) / 3.0)
    driver = pd.Series(values, index=pd.Index(months, name="month"))
    response = pd.Series(values * 2.0, index=pd.Index(months, name="month"))
    results = cm.lag_correlations(driver, response, max_lag=6)
    assert round(results.loc[0, "r"], 6) == 1.0
    assert results.loc[0, "n_months"] == 60


def test_lag_counts_only_months_present_in_both():
    months = pd.period_range("2000-01", periods=24, freq="M").strftime("%Y-%m")
    driver = pd.Series(np.arange(24.0), index=pd.Index(months, name="month"))
    response = driver.iloc[:10]                        # only 10 months of response
    results = cm.lag_correlations(driver, response, max_lag=3)
    assert results.loc[0, "n_months"] == 10
    assert results.loc[3, "n_months"] == 7             # three months slide off the start


# ---------------------------------------------------------
# wet / dry season split
# ---------------------------------------------------------

def test_wet_season_runs_november_to_april_and_is_labelled_by_its_start_year():
    """
    Nov 2015 - Apr 2016 is the wet season labelled 2015; May - Oct 2015 is dry season 2015.
    1 mm in every month makes each season total 6 mm.
    """
    table = monthly_table("2015-01", [1.0] * 24)       # Jan 2015 - Dec 2016
    frame = cm._season_frame(list(table.index), table["total"].to_numpy())

    wet_2015 = frame[(frame["wet"]) & (frame["season_year"] == 2015)]
    assert sorted(wet_2015["month"].tolist()) == [1, 2, 3, 4, 11, 12]
    assert len(wet_2015) == 6
    assert wet_2015["value"].sum() == 6.0

    dry_2015 = frame[(~frame["wet"]) & (frame["season_year"] == 2015)]
    assert sorted(dry_2015["month"].tolist()) == [5, 6, 7, 8, 9, 10]
    assert dry_2015["value"].sum() == 6.0


def test_january_belongs_to_the_previous_years_wet_season():
    frame = cm._season_frame(["2016-01"], [1.0])
    assert bool(frame.loc[0, "wet"]) is True
    assert int(frame.loc[0, "season_year"]) == 2015


def test_seasonal_model_totals_split_the_year_in_two():
    """A model series with 10 mm every month gives 60 mm in each season."""
    months = pd.period_range("2000-01", periods=48, freq="M").strftime("%Y-%m")
    series = pd.Series([10.0] * 48, index=pd.Index(months, name="month"))
    frame = cm._season_frame(list(series.index), series.to_numpy())
    grouped = frame.groupby(["season_year", "wet"])["value"].agg(["sum", "size"])
    whole = grouped[grouped["size"] == 6]
    assert (whole["sum"] == 60.0).all()


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
