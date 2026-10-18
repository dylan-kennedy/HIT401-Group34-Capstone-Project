# -*- coding: utf-8 -*-
"""
gwrc_trends.py - Groundwater Report Card: trend and completeness analysis
HIT401 Capstone Project, Group 34, Semester 2 2026.

Consumes gwrc_tidy.csv (produced by gwrc_ingest.py) and reproduces the results in
Section V of the Interim Report: per-bore water-level trends, record completeness,
and the two figures.

Method (Interim Report, Section III):
  * Raw observations are averaged to monthly then annual means. Annual averaging
    removes the seasonal cycle and most of the serial correlation that Helsel et al.
    (2020) warn will otherwise inflate the significance of a trend test.
  * An ordinary least-squares trend is fitted to the annual means.
  * Mann-Kendall with a Sen slope is also computed as a non-parametric robustness
    check; bores where the two disagree in sign or significance are flagged.

Usage:
    python3 gwrc_trends.py [gwrc_tidy.csv]
"""
from __future__ import annotations

import os
import sys
import itertools

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

AHD = "Water Elevation (AHD)"
# RN005723's Field Visits timestamps are the corrupted ones; prefer its Publish series.
PREFER_PUBLISH = {"RN005723"}


def annual_means(df: pd.DataFrame) -> pd.Series:
    """Monthly means then annual means, so heavily logged years are not over-weighted."""
    s = df.set_index("timestamp")["value"]
    return s.resample("MS").mean().dropna().resample("YS").mean().dropna()


def sen_slope(years: np.ndarray, vals: np.ndarray) -> float:
    """Sen (1968) median of all pairwise slopes."""
    slopes = [(vals[j] - vals[i]) / (years[j] - years[i])
              for i, j in itertools.combinations(range(len(years)), 2)
              if years[j] != years[i]]
    return float(np.median(slopes)) if slopes else np.nan


def mann_kendall_p(vals: np.ndarray) -> float:
    """Two-sided p-value for the Mann (1945) rank-based trend test, with tie correction."""
    n = len(vals)
    if n < 4:
        return np.nan
    s = sum(np.sign(vals[j] - vals[i])
            for i, j in itertools.combinations(range(n), 2))
    _, counts = np.unique(vals, return_counts=True)
    tie_term = sum(c * (c - 1) * (2 * c + 5) for c in counts if c > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return np.nan
    z = (s - np.sign(s)) / np.sqrt(var_s) if s != 0 else 0.0
    return float(2 * (1 - stats.norm.cdf(abs(z))))


def analyse(tidy: pd.DataFrame) -> pd.DataFrame:
    rows, series = [], {}
    for bore, g in tidy[tidy["parameter"] == AHD].groupby("bore"):
        want = "Publish" if bore in PREFER_PUBLISH else "Field Visits"
        sub = g[g["dataset"] == want]
        if sub.empty:                      # fall back if the preferred series is absent
            sub = g[g["dataset"] == ("Field Visits" if want == "Publish" else "Publish")]
        if sub.empty:
            continue
        a = annual_means(sub)
        if len(a) < 5:
            continue
        years = a.index.year.to_numpy(float)
        vals = a.to_numpy(float)
        lr = stats.linregress(years, vals)
        p_mk = mann_kendall_p(vals)
        sen = sen_slope(years, vals)
        span = int(years[-1] - years[0] + 1)
        rows.append(dict(
            bore=bore, source=want, n_years=len(years),
            start=int(years[0]), end=int(years[-1]),
            ols_slope=lr.slope, r2=lr.rvalue ** 2, p_ols=lr.pvalue,
            sen_slope=sen, p_mk=p_mk,
            net_change=vals[-1] - vals[0],
            coverage_pct=100.0 * len(years) / span,
            longest_gap_yr=int(np.max(np.diff(years))) if len(years) > 1 else 0,
        ))
        series[bore] = (years, vals)
    return pd.DataFrame(rows).set_index("bore").sort_index(), series


def report(res: pd.DataFrame) -> None:
    pd.set_option("display.width", 160)
    print("\n--- PER-BORE TREND AND COMPLETENESS ---")
    print(res.round(4).to_string())

    dec = res[(res.ols_slope < 0) & (res.p_ols < 0.05)]
    inc = res[(res.ols_slope > 0) & (res.p_ols < 0.05)]
    print(f"\nBores analysed                     : {len(res)}")
    print(f"Significant DECLINE (OLS, p<0.05)  : {len(dec)} {list(dec.index)}")
    print(f"Significant RISE    (OLS, p<0.05)  : {len(inc)} {list(inc.index)}")
    print(f"Median trend                       : {res.ols_slope.median():+.4f} m/yr")
    print(f"Mean trend                         : {res.ols_slope.mean():+.4f} m/yr")
    print(f"Steepest decline                   : {res.ols_slope.idxmin()} "
          f"({res.ols_slope.min():.4f} m/yr)")
    print(f"Largest net fall                   : {res.net_change.idxmin()} "
          f"({res.net_change.min():.2f} m)")
    print(f"Mean annual coverage               : {res.coverage_pct.mean():.1f}%")
    print(f"Bores below 80% coverage           : "
          f"{(res.coverage_pct < 80).sum()} of {len(res)}")
    print(f"Longest single gap                 : {res.longest_gap_yr.max()} years")

    # robustness check: OLS vs Mann-Kendall
    disagree = res[(np.sign(res.ols_slope) != np.sign(res.sen_slope)) |
                   ((res.p_ols < 0.05) != (res.p_mk < 0.05))]
    if len(disagree):
        print("\nOLS and Mann-Kendall/Sen DISAGREE for "
              f"{len(disagree)} bore(s) - report these as uncertain:")
        print(disagree[["ols_slope", "p_ols", "sen_slope", "p_mk"]].round(4).to_string())
    else:
        print("\nOLS and Mann-Kendall/Sen agree in sign and significance for every bore.")


def figures(res: pd.DataFrame, series: dict) -> None:
    plt.rcParams.update({"font.size": 9, "axes.linewidth": 0.6})
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))

    for bore in res.sort_values("ols_slope").index[:6]:
        yr, v = series[bore]
        ax[0].plot(yr, v, marker="o", ms=2.5, lw=1,
                   label=f"{bore} ({res.loc[bore, 'ols_slope']:+.3f} m/yr)")
    ax[0].set_xlabel("Year"); ax[0].set_ylabel("Water elevation (m AHD)")
    ax[0].set_title("Six most steeply declining bores"); ax[0].legend(fontsize=7)
    ax[0].grid(alpha=.3, lw=.4)

    order = res.sort_values("ols_slope").index
    ax[1].barh(range(len(order)), res.loc[order, "ols_slope"],
               color=["#b2182b" if s < 0 else "#2166ac" for s in res.loc[order, "ols_slope"]])
    ax[1].set_yticks(range(len(order))); ax[1].set_yticklabels(order, fontsize=7)
    ax[1].axvline(0, color="k", lw=.6); ax[1].set_xlabel("Trend (m/yr)")
    ax[1].set_title("Fitted linear trend per bore"); ax[1].grid(alpha=.3, lw=.4, axis="x")

    fig.tight_layout()
    fig.savefig("gwrc_trends.png", dpi=170, bbox_inches="tight")
    print("\nWrote gwrc_trends.png")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "gwrc_tidy.csv"
    if not os.path.isfile(path):
        raise SystemExit(f"Error: '{path}' not found. "
                          "Run gwrc_ingest.py first to produce gwrc_tidy.csv.")
    tidy = pd.read_csv(path, parse_dates=["timestamp"])
    res, series = analyse(tidy)
    report(res)
    res.to_csv("gwrc_trend_results.csv")
    print("Wrote gwrc_trend_results.csv")
    figures(res, series)


if __name__ == "__main__":
    main()
