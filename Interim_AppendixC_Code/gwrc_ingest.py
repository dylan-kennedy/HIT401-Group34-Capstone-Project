# -*- coding: utf-8 -*-
"""
gwrc_ingest.py - Groundwater Report Card: ingestion and quality audit
HIT401 Capstone Project, Group 34, Semester 2 2026.

Reads the per-bore CSV exports in the GroundwaterHeads_20250718 folder supplied by
A/Prof Dylan Irvine, normalises them into one tidy DataFrame, and reports the
data-quality defects described in Section IV of the Interim Report.

The export format is:
    line 1  #Data Set Export - <Parameter>.<DatasetType>@<BoreID>,,
    line 2  <telemetry disclaimer>
    line 3  Timestamp (UTC+09:30),Event Timestamp (UTC+09:30),Value (m)
    line 4+ data
so we skip 2 rows and take columns 0 and 2, following the same convention as the
client's own Load_and_plot.py.

Usage:
    python3 gwrc_ingest.py /path/to/GroundwaterHeads_20250718
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

import pandas as pd

AHD = "Water Elevation (AHD)"
DBG = "Depth Below Ground"


def parse_export(path: str) -> pd.DataFrame:
    """Parse one DataSetExport CSV into a tidy DataFrame [timestamp, value]."""
    df = pd.read_csv(path, skiprows=2, usecols=[0, 2],
                     names=["timestamp", "value"], header=0,
                     encoding="utf-8-sig", on_bad_lines="skip")
    # The dataset mixes two timestamp formats: RN005723's AHD Field Visits export uses
    # DD/MM/YYYY while every other file uses YYYY-MM-DD (Section IV, defect (a)).
    # Detect which is present rather than forcing one, so neither is silently dropped.
    raw = df["timestamp"].astype(str)
    iso_like = raw.str.match(r"^\d{4}-\d{2}-\d{2}")
    ts = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    if iso_like.any():
        ts[iso_like] = pd.to_datetime(raw[iso_like], format="ISO8601", errors="coerce")
    if (~iso_like).any():
        ts[~iso_like] = pd.to_datetime(raw[~iso_like], dayfirst=True, errors="coerce")
    df["timestamp"] = ts
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().sort_values("timestamp").reset_index(drop=True)


def describe_file(name: str) -> tuple[str | None, str | None, str | None]:
    """Return (bore_id, parameter, dataset_type) inferred from an export filename."""
    m = re.search(r"@(RN\d{6})", name)
    bore = m.group(1) if m else None
    parameter = AHD if "(AHD)" in name else (DBG if DBG in name else None)
    if "Publish" in name:
        dtype = "Publish"
    elif "Field Visits" in name:
        dtype = "Field Visits"
    else:
        dtype = None
    return bore, parameter, dtype


def ingest(root: str) -> pd.DataFrame:
    """Walk the supplied folder and return every series as one tidy DataFrame."""
    frames = []
    seen_bores = set()
    for sub in sorted(os.listdir(root)):
        sub_path = os.path.join(root, sub)
        if not (os.path.isdir(sub_path) and sub.startswith("LocationExport")):
            continue
        # Skip a folder that duplicates a bore already ingested (see audit's defect (b));
        # the defect is still reported there, we just don't double-count its rows here.
        m = re.search(r"(RN\d{6})", sub)
        if m:
            if m.group(1) in seen_bores:
                continue
            seen_bores.add(m.group(1))
        for fname in sorted(os.listdir(sub_path)):
            if not fname.lower().endswith(".csv"):
                continue
            bore, parameter, dtype = describe_file(fname)
            if not (bore and parameter and dtype):
                print(f"  ! could not classify {fname}")
                continue
            df = parse_export(os.path.join(sub_path, fname))
            if df.empty:
                print(f"  ! no valid rows parsed from {fname}")
                continue
            df["bore"] = bore
            df["parameter"] = parameter
            df["dataset"] = dtype
            df["source_folder"] = sub
            frames.append(df)
    if not frames:
        raise SystemExit("No exports found - check the path.")
    return pd.concat(frames, ignore_index=True)


def audit(root: str, tidy: pd.DataFrame) -> None:
    """Report the four data-quality defects documented in Section IV."""
    subs = [s for s in os.listdir(root)
            if os.path.isdir(os.path.join(root, s)) and s.startswith("LocationExport")]
    bores = sorted(tidy["bore"].unique())

    print("\n--- DATA-QUALITY AUDIT ---")
    print(f"LocationExport subfolders : {len(subs)}")
    print(f"Unique bore IDs           : {len(bores)}")

    # (b) duplicate exports of the same bore
    per_bore = defaultdict(set)
    for s in subs:
        m = re.search(r"(RN\d{6})", s)
        if m:
            per_bore[m.group(1)].add(s)
    dupes = {b: sorted(f) for b, f in per_bore.items() if len(f) > 1}
    for b, folders in dupes.items():
        print(f"(b) DUPLICATE EXPORT: {b} appears in {len(folders)} folders -> {folders}")

    # (c) bores the client's Load_and_plot.py silently skips (needs BOTH AHD files)
    have = defaultdict(set)
    for (b, ds), _ in tidy[tidy["parameter"] == AHD].groupby(["bore", "dataset"]):
        have[b].add(ds)
    skipped = sorted(b for b in bores
                     if not {"Publish", "Field Visits"} <= have.get(b, set()))
    print(f"(c) SKIPPED by Load_and_plot.py (no Publish AHD export): {skipped}")
    print(f"    {len(bores)} unique - {len(skipped)} skipped = "
          f"{len(bores) - len(skipped)} plotted "
          f"(compare head_time_series_bores.csv)")

    # (d) Publish vs Field Visits disagree on period of record
    print("(d) PERIOD-OF-RECORD MISMATCH (Publish end vs Field Visits end):")
    ahd = tidy[tidy["parameter"] == AHD]
    for b in bores:
        ends = ahd[ahd["bore"] == b].groupby("dataset")["timestamp"].max()
        if len(ends) == 2 and abs((ends.get("Publish") - ends.get("Field Visits")).days) > 365:
            print(f"    {b}: Publish ends {ends['Publish']:%Y-%m-%d}, "
                  f"Field Visits ends {ends['Field Visits']:%Y-%m-%d}")


def main() -> None:
    root = sys.argv[1] if len(sys.argv) > 1 else "GroundwaterHeads_20250718"
    if not os.path.isdir(root):
        raise SystemExit(f"Error: '{root}' is not a directory. "
                          "Pass the path to the GroundwaterHeads_20250718 folder.")
    print(f"Ingesting {root} ...")
    tidy = ingest(root)
    print(f"\nParsed {len(tidy):,} measurements "
          f"across {tidy.groupby(['bore', 'parameter', 'dataset']).ngroups} series")
    print(f"Period of record: {tidy['timestamp'].min():%Y-%m-%d} "
          f"to {tidy['timestamp'].max():%Y-%m-%d}")
    audit(root, tidy)
    tidy.to_csv("gwrc_tidy.csv", index=False)
    print("\nWrote gwrc_tidy.csv")


if __name__ == "__main__":
    main()
