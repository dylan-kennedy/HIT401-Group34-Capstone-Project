"""
Tests for climate_models.py, using small made-up series so the expected answers can be
worked out by hand. Run with:

    ~/venvs/hit401_climate/bin/python -B -m pytest climate/tests/test_climate_models.py -v
    ~/venvs/hit401_climate/bin/python -B climate/tests/test_climate_models.py      # same, no pytest

None of these tests touch the real data files or the network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# climate_models.py and download_cmip6_pr.py live one level up, in climate/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import climate_models as cm


# ---------------------------------------------------------
# helpers
# ---------------------------------------------------------

def monthly(start_year, start_month, values):
    """Build a monthly Series with climate_models' 'YYYY-MM' index from a list of numbers."""
    index = pd.period_range(f"{start_year}-{start_month:02d}", periods=len(values), freq="M")
    return pd.Series(values, index=pd.Index(index.strftime("%Y-%m"), name="month"), dtype=float)


# ---------------------------------------------------------
# water-year labelling
# ---------------------------------------------------------

def test_water_year_labelling_august_belongs_to_previous_year():
    """Aug 2000 is in water year 1999; Sep 2000 starts water year 2000."""
    # Two complete water years: Sep 1999-Aug 2000 (=1999) and Sep 2000-Aug 2001 (=2000).
    # Every month is 1 mm except Aug 2000 (= 100) and Sep 2000 (= 500), so the totals
    # tell us which water year each of those two months landed in.
    values = [1.0] * 24
    values[11] = 100.0      # Aug 2000 (12th month after Sep 1999)
    values[12] = 500.0      # Sep 2000
    series = monthly(1999, 9, values)

    totals = cm.water_year_totals(series)

    assert list(totals.index) == [1999, 2000]
    assert totals.loc[1999] == 11 * 1.0 + 100.0     # Aug 2000 counted here
    assert totals.loc[2000] == 11 * 1.0 + 500.0     # Sep 2000 counted here


def test_incomplete_first_and_last_years_are_dropped():
    """A series starting in January and ending mid-year keeps only whole water years."""
    # Jan 2000 - Dec 2002: water year 1999 is partial (Jan-Aug 2000 only), 2000 and 2001
    # are complete, 2002 is partial (Sep-Dec 2002 only).
    series = monthly(2000, 1, [1.0] * 36)

    totals = cm.water_year_totals(series)

    assert list(totals.index) == [2000, 2001]
    assert (totals == 12.0).all()


def test_last_year_cap_trims_beyond_2099():
    """Water years after LAST_WATER_YEAR (2099) are dropped even when complete."""
    series = monthly(2098, 9, [1.0] * 36)        # water years 2098, 2099, 2100
    totals = cm.water_year_totals(series)
    assert list(totals.index) == [2098, 2099]


# ---------------------------------------------------------
# unit conversion with a noleap calendar
# ---------------------------------------------------------

def test_noleap_february_conversion(tmp_path=None):
    """
    pr (kg m-2 s-1) must be converted with the MODEL's day count, so February on a
    'noleap' calendar is 28 days even in a leap year such as 2000.
    """
    import xarray as xr

    # A constant rate of 1e-5 kg m-2 s-1 over Jan/Feb/Mar 2000 on a noleap calendar.
    time = xr.cftime_range("2000-01-01", periods=3, freq="MS", calendar="noleap")
    data = xr.DataArray(np.full(3, 1e-5), coords={"time": time}, dims="time", name="pr")
    folder = Path(tmp_path) if tmp_path else Path(__file__).parent / "_tmp"
    folder.mkdir(exist_ok=True)
    path = folder / "pr_test_noleap.nc"
    data.to_dataset().to_netcdf(path)

    series = cm._monthly_mm(path)

    rate_mm_per_day = 1e-5 * cm.SECONDS_PER_DAY
    assert series["2000-01"] == rate_mm_per_day * 31
    assert series["2000-02"] == rate_mm_per_day * 28      # NOT 29, although 2000 is a leap year
    assert series["2000-03"] == rate_mm_per_day * 31
    path.unlink()


# ---------------------------------------------------------
# anomalies and the trailing mean
# ---------------------------------------------------------

def test_anomalies_are_differences_from_the_reference_mean():
    wy = pd.Series([100.0, 200.0, 300.0, 400.0], index=[1985, 1986, 2000, 2001])
    # Reference 1985-1986 only -> mean 150.
    out = cm.anomalies(wy, ref=(1985, 1986))
    assert list(out.values) == [-50.0, 50.0, 150.0, 250.0]


def test_trailing_mean_uses_the_previous_ten_years_and_crops_after():
    """
    The mean at year Y covers Y-9..Y inclusive, and the window is computed BEFORE cropping,
    so the first plotted year already has a full 10-year window behind it.
    """
    years = range(1960, 1981)                      # 1960..1980
    wy = pd.Series([float(y - 1959) for y in years], index=list(years))   # 1,2,3,...,21

    rolled = cm.trailing_mean(wy, window=10, first_year=1975)

    assert rolled.index.min() == 1975              # cropped
    # 1975 is the 16th value (=16); window 1966..1975 = values 7..16, mean 11.5
    assert rolled.loc[1975] == 11.5
    assert not rolled.isna().any()                 # full window everywhere after cropping


# ---------------------------------------------------------
# percent change (slide 31)
# ---------------------------------------------------------

def test_pct_change_mean_and_median_can_disagree_in_sign():
    """
    A known example: the future period has a higher MEAN (one very wet year) but a lower
    MEDIAN. Slide 31 shows exactly this case, where the tick sits on the other side of zero.
    """
    ref_years = {y: 100.0 for y in range(1985, 2015)}            # mean 100, median 100
    future_years = {y: 90.0 for y in range(2070, 2100)}          # start all at 90
    future_years[2099] = 1000.0                                  # one extreme wet year
    wy = pd.Series({**ref_years, **future_years})

    out = cm.pct_change(wy)

    # mean = (29*90 + 1000)/30 = 120.33 -> +20.3%;  median = 90 -> -10%
    assert round(out["mean_pct"], 1) == 20.3
    assert round(out["median_pct"], 1) == -10.0
    assert out["mean_pct"] > 0 > out["median_pct"]
    assert out["n_ref_years"] == 30 and out["n_future_years"] == 30


def test_pct_change_simple_values():
    wy = pd.Series({**{y: 200.0 for y in range(1985, 2015)},
                    **{y: 150.0 for y in range(2070, 2100)}})
    out = cm.pct_change(wy)
    assert round(out["mean_pct"], 1) == -25.0
    assert round(out["median_pct"], 1) == -25.0


# ---------------------------------------------------------
# the 2014/2015 join
# ---------------------------------------------------------

def test_join_detects_a_gap_between_experiments():
    historical = monthly(2013, 1, [1.0] * 24)       # ends 2014-12
    future = monthly(2015, 2, [1.0] * 12)           # starts 2015-02: January is missing
    joined = pd.concat([historical, future]).sort_index()
    assert cm._missing_months(joined.index) == ["2015-01"]


def test_join_is_clean_when_experiments_meet_exactly():
    historical = monthly(2013, 1, [1.0] * 24)       # ends 2014-12
    future = monthly(2015, 1, [1.0] * 12)           # starts 2015-01
    joined = pd.concat([historical, future]).sort_index()
    assert cm._missing_months(joined.index) == []
    assert len(joined.index) == len(set(joined.index))     # no overlap


def test_registry_matches_the_downloader():
    """climate_models.REGISTRY must stay in step with download_cmip6_pr.MODEL_RUNS."""
    import download_cmip6_pr as dl
    assert [(r["label"], r["source_id"], r["member"]) for r in cm.REGISTRY] == \
           [(r["label"], r["source_id"], r["member"]) for r in dl.MODEL_RUNS]


# ---------------------------------------------------------
# allow running without pytest
# ---------------------------------------------------------

if __name__ == "__main__":
    import tempfile
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            if name == "test_noleap_february_conversion":
                with tempfile.TemporaryDirectory() as tmp:
                    fn(tmp)
            else:
                fn()
            print(f"PASS {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
