"""
Tests for the residual mass code in climate_models.py (observed rainfall and river flow).

Run with:
    ~/venvs/hit401_climate/bin/python -B climate/tests/test_residual_mass.py

All of these use small made-up series, so the expected answers can be checked by hand.
Nothing here reads the real data files or the network.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# climate_models.py and download_cmip6_pr.py live one level up, in climate/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import climate_models as cm


def daily_frame(year, month, values, start_day=1):
    """Build a daily rainfall frame; use None for a blank (no value recorded) day."""
    dates = pd.date_range(f"{year}-{month:02d}-{start_day:02d}", periods=len(values), freq="D")
    return pd.DataFrame({"date": dates,
                         "rain_mm": [np.nan if v is None else float(v) for v in values],
                         "quality": ["N"] * len(values)})


# ---------------------------------------------------------
# the gap rule
# ---------------------------------------------------------

def test_five_blank_days_is_still_complete():
    """MAX_BLANK_DAYS = 5, so exactly 5 blanks must NOT make the month missing."""
    values = [1.0] * 31
    for day in range(5):                     # 5 blank days
        values[day] = None
    table = cm.monthly_totals_from_daily(daily_frame(2000, 1, values))
    assert table.loc["2000-01", "blank_days"] == 5
    assert bool(table.loc["2000-01", "complete"]) is True
    assert table.loc["2000-01", "total"] == 26.0        # the 26 days that had a value


def test_six_blank_days_makes_the_month_missing():
    values = [1.0] * 31
    for day in range(6):                     # one more blank than allowed
        values[day] = None
    table = cm.monthly_totals_from_daily(daily_frame(2000, 1, values))
    assert table.loc["2000-01", "blank_days"] == 6
    assert bool(table.loc["2000-01", "complete"]) is False
    assert pd.isna(table.loc["2000-01", "total"])       # no total for a missing month


def test_days_absent_from_the_file_count_as_blank():
    """A short month (rows simply not present) is judged the same way as empty cells."""
    table = cm.monthly_totals_from_daily(daily_frame(2000, 1, [1.0] * 24))   # 7 days absent
    assert table.loc["2000-01", "blank_days"] == 7
    assert bool(table.loc["2000-01", "complete"]) is False


# ---------------------------------------------------------
# calendar-month averages and the running total
# ---------------------------------------------------------

def test_calendar_month_average_uses_complete_months_only():
    """
    Two Januaries: one complete (total 31 mm), one missing (should be ignored).
    The January average must be 31, not an average that includes the broken month.
    """
    january_2000 = daily_frame(2000, 1, [1.0] * 31)                     # complete, 31 mm
    january_2001 = daily_frame(2001, 1, [10.0] * 10 + [None] * 21)      # 21 blanks: missing
    february_2000 = daily_frame(2000, 2, [2.0] * 29)                    # complete, 58 mm
    february_2001 = daily_frame(2001, 2, [4.0] * 28)                    # complete, 112 mm
    daily = pd.concat([january_2000, february_2000, january_2001, february_2001])

    table = cm.residual_mass(cm.monthly_totals_from_daily(daily))

    assert table.loc["2000-01", "month_average"] == 31.0                # only the good January
    assert table.loc["2001-02", "month_average"] == (58.0 + 112.0) / 2  # both Februaries
    # The missing month contributes nothing to the running total.
    assert table.loc["2001-01", "residual"] == 0.0


def test_cumulative_sum_on_a_known_example():
    """
    Three Januaries of 10, 20 and 30 mm: average 20, residuals -10, 0, +10,
    so the running total goes -10, -10, 0.
    """
    frames = [daily_frame(year, 1, [value / 31] * 31)
              for year, value in [(2000, 10.0), (2001, 20.0), (2002, 30.0)]]
    monthly = cm.monthly_totals_from_daily(pd.concat(frames))
    monthly = monthly[monthly.index.str.endswith("-01")]        # Januaries only

    table = cm.residual_mass(monthly)

    assert round(table.loc["2000-01", "month_average"], 6) == 20.0
    assert [round(v, 6) for v in table["residual"]] == [-10.0, 0.0, 10.0]
    assert [round(v, 6) for v in table["cumulative"]] == [-10.0, -10.0, 0.0]


def test_a_gap_holds_the_running_total_flat():
    """A missing month must not move the curve: its residual is 0."""
    good = daily_frame(2000, 1, [1.0] * 31)                  # 31 mm
    broken = daily_frame(2001, 1, [1.0] * 10 + [None] * 21)  # missing
    later = daily_frame(2002, 1, [3.0] * 31)                 # 93 mm
    table = cm.residual_mass(cm.monthly_totals_from_daily(pd.concat([good, broken, later])))
    januaries = table[table.index.str.endswith("-01")]
    assert januaries.loc["2001-01", "residual"] == 0.0
    assert januaries.loc["2001-01", "cumulative"] == januaries.loc["2000-01", "cumulative"]


def test_gap_bands_group_runs_of_missing_months():
    daily = pd.concat([
        daily_frame(2000, 1, [1.0] * 31),                      # complete
        daily_frame(2000, 2, [1.0] * 10 + [None] * 19),        # missing
        daily_frame(2000, 3, [1.0] * 10 + [None] * 21),        # missing (same run)
        daily_frame(2000, 4, [1.0] * 30),                      # complete
    ])
    table = cm.monthly_totals_from_daily(daily)
    assert cm.gap_bands(table) == [("2000-02", "2000-03")]


# ---------------------------------------------------------
# river flow: trapezoidal volume and the coverage rule
# ---------------------------------------------------------

def flow_frame(timestamps, values, quality=10):
    return pd.DataFrame({"timestamp": pd.to_datetime(timestamps),
                         "flow_cumecs": [float(v) for v in values],
                         "quality": [quality] * len(values),
                         "interpolation": [102] * len(values)})


def test_flow_volume_uses_the_trapezoidal_rule_over_actual_intervals():
    """
    A steady 1 m3/s for one hour is 3600 m3 = 3.6 ML.
    Readings are 10 minutes apart, so the intervals are not assumed, they are measured.
    """
    stamps = pd.date_range("2015-01-10 00:00", periods=7, freq="10min")
    table = cm.monthly_flow_volumes(flow_frame(stamps, [1.0] * 7))
    assert round(table.loc["2015-01", "total"], 6) == 3.6


def test_flow_volume_handles_a_ramp():
    """0 to 2 m3/s over 1000 s averages 1 m3/s: 1000 m3 = 1 ML."""
    stamps = [pd.Timestamp("2015-01-10 00:00"), pd.Timestamp("2015-01-10 00:00") + pd.Timedelta(seconds=1000)]
    table = cm.monthly_flow_volumes(flow_frame(stamps, [0.0, 2.0]))
    assert round(table.loc["2015-01", "total"], 6) == 1.0


def test_flow_month_with_a_long_gap_is_marked_missing():
    """A 10-day hole inside a month leaves more than 5 days uncovered, so it is missing."""
    first = pd.date_range("2015-01-01", "2015-01-05", freq="10min")
    second = pd.date_range("2015-01-16", "2015-01-31 23:50", freq="10min")
    stamps = first.append(second)
    table = cm.monthly_flow_volumes(flow_frame(stamps, [1.0] * len(stamps)))
    assert bool(table.loc["2015-01", "complete"]) is False
    assert table.loc["2015-01", "blank_days"] > cm.MAX_BLANK_DAYS


def test_flow_month_with_full_coverage_is_complete():
    stamps = pd.date_range("2015-01-01", "2015-01-31 23:50", freq="10min")
    table = cm.monthly_flow_volumes(flow_frame(stamps, [1.0] * len(stamps)))
    assert bool(table.loc["2015-01", "complete"]) is True
    assert table.loc["2015-01", "blank_days"] == 0


def test_quality_210_share_is_reported_not_dropped():
    """Quality 210 dominates the real file, so it is measured rather than removed."""
    stamps = pd.date_range("2015-01-01", "2015-01-31 23:50", freq="10min")
    frame = flow_frame(stamps, [1.0] * len(stamps))
    frame.loc[frame.index[: len(frame) // 2], "quality"] = 210
    table = cm.monthly_flow_volumes(frame)
    assert table.loc["2015-01", "total"] > 0                      # nothing was dropped
    assert 0.4 < table.loc["2015-01", "quality_210_share"] < 0.6   # about half


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
