"""
webapp/build_cache.py — one-off preprocessing for the HIT401 Group 34 data explorer.

Reads every raw dataset in this repository (read-only — nothing outside webapp/ is ever
written to) and writes compact caches to webapp/cache/, which webapp/server.py then
serves from. This keeps the server's own startup to "load a few small Parquet files",
which is what makes a <5s start possible.

What it reads (all read-only):
  - Datasets/NT-NaturalResourceMapsBoreData/Bores.csv       (NT-wide bore attributes)
  - krishna-code/data.zip -> data/nt_bores/*.shp             (bore/monitoring/quality geometry)
  - krishna-code/data.zip -> data/ti_tree/data/ttbaq_250_*.shp (Ti Tree aquifer layers)
  - Datasets/GroundwaterHeads_20250718/LocationExport-*/      (bore water-level series)
  - Datasets/BOM-Datasets/                                    (daily rainfall, 11 stations)
  - Datasets/StreamflowData/                                  (river gauge G0280010)
  - climate/climate_models.py functions, imported read-only, for the rainfall/flow/bore
    aggregation logic (monthly totals, residual mass) so the numbers match what the
    climate module already produces and tests.

What it writes (webapp/cache/, nothing else):
  - bores.parquet, gauges.parquet, monitoring_bores.parquet, bom_stations.parquet
  - water_quality_summary.parquet, water_quality_full.parquet
  - bom_daily.parquet, bom_monthly.parquet
  - streamflow_monthly.parquet, streamflow_quality.json
  - waterlevel/<bore>.parquet (one per bore with a real exported series)
  - aquifer/<layer>.geojson (boundary, salinity, aquifer, water_depth, contours)
  - build_report.json — every assumption, repair and conflict made along the way, so the
    final report can quote it rather than re-derive it.

Re-run any time with:
    ~/venvs/hit401_web/bin/python webapp/build_cache.py

Every run rebuilds every cache file — the whole thing takes under 20 seconds, so there is
no incremental/staleness logic to go wrong. --force is accepted but currently a no-op.
"""

import argparse
import csv
import json
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pandas as pd

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------

WEBAPP_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBAPP_DIR.parent
CACHE_DIR = WEBAPP_DIR / "cache"
EXTRACT_DIR = CACHE_DIR / "_extracted"          # our own read-only extraction of data.zip

BORES_CSV = REPO_ROOT / "Datasets" / "NT-NaturalResourceMapsBoreData" / "Bores.csv"
DATA_ZIP = REPO_ROOT / "krishna-code" / "data.zip"
GW_HEADS_DIR = REPO_ROOT / "Datasets" / "GroundwaterHeads_20250718"
BOM_DIR = REPO_ROOT / "Datasets" / "BOM-Datasets"
FLOW_DIR = REPO_ROOT / "Datasets" / "StreamflowData"

# climate/climate_models.py is imported, not copied, so its logic and tests stay the
# single source of truth for the rainfall/flow calculations.
sys.path.insert(0, str(REPO_ROOT / "climate"))
import climate_models as cm  # noqa: E402  (import after sys.path edit, deliberately)

# ---------------------------------------------------------------------------
# NAMED CONSTANTS (so nothing below is a magic number)
# ---------------------------------------------------------------------------

FAR_STATION_WARNING_KM = 50     # "nearest station/gauge" shows a warning past this
FLOW_STATION_ID = "G0280010"
NT_BOM_STATIONS = {"015643", "014050"}   # the only 2 of 11 BOM stations actually in the NT
MAX_BLANK_DAYS = cm.MAX_BLANK_DAYS        # re-exported so the API and tests agree with climate_models

REPORT = {
    "generated_at": None,
    "bores_csv_repairs": [],
    "bores_csv_dropped_rows": 0,
    "shapefile_dedup": {},
    "monitoring_split": {},
    "bore_waterlevel_notes": [],
    "warnings": [],
    "row_counts": {},
    "timings_seconds": {},
}


def _log_warning(message):
    REPORT["warnings"].append(message)
    print(f"WARNING: {message}")


# ---------------------------------------------------------------------------
# ID NORMALISATION — same rule as krishna-code/app(v1.2).py, so IDs line up
# ---------------------------------------------------------------------------

def normalise_id(value):
    """'RN5628', 'rn 005628', 'RN005628' -> 'RN005628'. G-codes and anything else are
    just upper-cased and stripped of spaces; only RN bore numbers get zero-padded."""
    if value is None:
        return None
    text = str(value).strip().strip('"').upper().replace(" ", "")
    if not text:
        return None
    if text.startswith("RN"):
        digits = "".join(c for c in text[2:] if c.isdigit())
        if digits:
            return f"RN{int(digits):06d}"
    return text


def fix_water_data_portal_url(value):
    """Upgrades legacy NT Water Data Portal URLs from the decommissioned
    water.nt.gov.au host to the official ntg.aquaticinformatics.net host.

    Preserves full path (e.g. /Data/Location/Summary/Location/<ID>/...), query
    parameters and fragments. Unrelated domains (e.g. ntlis.nt.gov.au bore reports)
    and already-correct URLs are untouched. Missing/empty values remain None."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().strip('"')
    if not text or not text.startswith("http"):
        return None
    try:
        parsed = urlparse(text)
    except Exception:
        return text

    if parsed.netloc.lower() == "water.nt.gov.au":
        new_parsed = parsed._replace(scheme="https", netloc="ntg.aquaticinformatics.net")
        return urlunparse(new_parsed)
    return text


# ---------------------------------------------------------------------------
# 1. Bores.csv — the primary attribute source, with the known quoting repairs
# ---------------------------------------------------------------------------

BORES_CSV_COLUMNS = [
    "bore_no", "name", "bore_report_url", "yield_ls", "completion_date",
    "drilled_depth_m", "completion_depth_m", "depth_to_water_m", "purpose",
    "construction", "status", "latitude", "longitude", "utm_zone",
    "easting", "northing", "position_accuracy", "water_data_portal",
]


def _repair_row(row_number, row):
    """
    Bores.csv has a handful of rows where a literal " inside the Name field (meant as an
    inch mark, e.g. 6"CAS) closes the CSV quoting early. Python's csv module then reads
    more or fewer fields than the 18 the header defines. This reconstructs the Name field
    for the two shapes this takes in the file (confirmed by scanning every row — see
    build_report.json["bores_csv_repairs"]):

      * 19 or 20 fields: the Name field was split into 2 or 3 pieces by stray commas.
        Rejoin fields[1 : 1 + extra + 1] with "," to rebuild the Name.
      * 11 fields: the stray quote swallowed the Name AND the next 7 columns (Bore
        report .. Purpose) into one blob, still comma-separated inside it. Split that
        blob back into 8 pieces.

    Returns an 18-field row, or None if the shape is one we don't recognise (in which
    case the row is dropped and counted, never guessed at).
    """
    n = len(row)
    if n == 18:
        return row
    if n in (19, 20):
        extra = n - 18
        name = ",".join(row[1:2 + extra]).rstrip('"')
        rebuilt = [row[0], name] + row[2 + extra:]
        if len(rebuilt) == 18:
            REPORT["bores_csv_repairs"].append(
                {"line": row_number, "shape": f"{n}_fields_name_split", "repaired_name": name}
            )
            return rebuilt
        return None
    if n == 11:
        blob = row[1]
        parts = blob.split(",")
        if len(parts) == 8:
            name = parts[0].rstrip('"')
            purpose = parts[7].rstrip('"')
            rebuilt = [row[0], name] + parts[1:7] + [purpose] + row[2:]
            if len(rebuilt) == 18:
                REPORT["bores_csv_repairs"].append(
                    {"line": row_number, "shape": "11_fields_blob_split", "repaired_name": name}
                )
                return rebuilt
        return None
    return None


def load_bores_csv():
    rows = []
    dropped = 0
    with open(BORES_CSV, encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert len(header) == 18, f"Bores.csv header changed shape: {header}"
        for line_number, row in enumerate(reader, start=2):
            fixed = _repair_row(line_number, row)
            if fixed is None:
                dropped += 1
                _log_warning(f"Bores.csv line {line_number}: unrecognised shape ({len(row)} "
                             "fields), dropped rather than guessed at.")
                continue
            rows.append(fixed)
    REPORT["bores_csv_dropped_rows"] = dropped

    frame = pd.DataFrame(rows, columns=BORES_CSV_COLUMNS)
    frame["bore_no"] = frame["bore_no"].map(normalise_id)
    frame = frame.dropna(subset=["bore_no"])

    for col in ("yield_ls", "drilled_depth_m", "completion_depth_m", "depth_to_water_m",
                "latitude", "longitude", "easting", "northing"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["utm_zone"] = pd.to_numeric(frame["utm_zone"], errors="coerce").astype("Int64")
    frame["completion_date"] = pd.to_datetime(frame["completion_date"], errors="coerce")

    for col in ("name", "purpose", "construction", "status", "position_accuracy",
                "water_data_portal", "bore_report_url"):
        frame[col] = frame[col].astype("string").str.strip()
        frame.loc[frame[col] == "", col] = pd.NA
    frame["water_data_portal"] = frame["water_data_portal"].map(fix_water_data_portal_url)

    before = len(frame)
    frame = frame.dropna(subset=["latitude", "longitude"])
    if before != len(frame):
        _log_warning(f"Bores.csv: dropped {before - len(frame)} rows with no coordinates.")

    duplicate_ids = frame["bore_no"][frame["bore_no"].duplicated()].unique().tolist()
    if duplicate_ids:
        _log_warning(f"Bores.csv: {len(duplicate_ids)} bore_no values appear more than once "
                     f"after normalising; keeping the first occurrence of each. Examples: "
                     f"{duplicate_ids[:5]}")
    frame = frame.drop_duplicates("bore_no", keep="first").reset_index(drop=True)
    return frame


# ---------------------------------------------------------------------------
# 2. krishna-code/data.zip — extract once into webapp/cache/_extracted/, then
#    read with geopandas exactly as krishna-code/app(v1.2).py does.
# ---------------------------------------------------------------------------

def ensure_extracted():
    """Extracts data.zip into webapp/cache/_extracted/ if not already done. This is a
    copy, made inside webapp/ only — krishna-code/data.zip itself is never modified."""
    marker = EXTRACT_DIR / ".extracted_ok"
    if marker.exists():
        return
    if not DATA_ZIP.exists():
        raise FileNotFoundError(f"{DATA_ZIP} not found — cannot build the bore/aquifer caches.")
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {DATA_ZIP.name} -> {EXTRACT_DIR} (one-off, read-only copy)...")
    with zipfile.ZipFile(DATA_ZIP) as zf:
        zf.extractall(EXTRACT_DIR)
    marker.write_text("ok\n")


def nt_bores_path(name):
    return EXTRACT_DIR / "data" / "nt_bores" / name


def ti_tree_path(name):
    return EXTRACT_DIR / "data" / "ti_tree" / "data" / name


def load_bores_shapefile():
    """Bores.shp: WATERLEVEL, RISK_CLASS and the water-data-portal link that Bores.csv
    doesn't carry, plus geometry as a cross-check on Bores.csv's own lat/lon."""
    import pyogrio

    frame = pyogrio.read_dataframe(
        nt_bores_path("Bores.shp"),
        columns=["BORE_NO", "WATERLEVEL", "RISK_CLASS", "WATER_DATA", "MONITORED",
                 "STATUSCONS", "COMPL_DATE", "TESTDATE"],
    )
    frame = frame.set_geometry("geometry").to_crs(epsg=4326)
    frame["bore_no"] = frame["BORE_NO"].map(normalise_id)
    frame["WATERLEVEL"] = pd.to_numeric(frame["WATERLEVEL"], errors="coerce")
    frame["RISK_CLASS"] = pd.to_numeric(frame["RISK_CLASS"], errors="coerce")
    frame["shp_lat"] = frame.geometry.y
    frame["shp_lon"] = frame.geometry.x
    frame = frame.dropna(subset=["bore_no"])

    total = len(frame)
    unique = frame["bore_no"].nunique()
    dup_groups = frame[frame.duplicated("bore_no", keep=False)].groupby("bore_no")
    conflicting = 0
    for bore_no, group in dup_groups:
        if group["WATERLEVEL"].nunique(dropna=True) > 1 or group["RISK_CLASS"].nunique(dropna=True) > 1:
            conflicting += 1
    REPORT["shapefile_dedup"] = {
        "total_records": total,
        "unique_bore_no": unique,
        "duplicate_bore_no_groups": len(dup_groups),
        "groups_with_differing_waterlevel_or_risk": conflicting,
        "rule": "kept the first occurrence of each normalised bore_no (pandas default row "
                "order, i.e. the shapefile's own record order); later duplicates discarded.",
    }
    frame = frame.drop_duplicates("bore_no", keep="first")
    frame["WATER_DATA"] = frame["WATER_DATA"].map(fix_water_data_portal_url)
    return frame[["bore_no", "WATERLEVEL", "RISK_CLASS", "WATER_DATA", "MONITORED",
                  "STATUSCONS", "shp_lat", "shp_lon"]].rename(columns={
        "WATERLEVEL": "waterlevel_m", "RISK_CLASS": "risk_class",
        "WATER_DATA": "water_data_portal_shp", "MONITORED": "monitored",
        "STATUSCONS": "status_construction",
    })


def load_monitoring_layer():
    """Bores_groundwater_level.shp mixes bore monitoring stations with river/stream gauge
    codes (G0xxxxxx). Split by whether the normalised STATION id matches an RN bore
    number or not — the gauges get their own location type, per the project's decision,
    rather than being silently treated as bores or dropped."""
    import pyogrio

    frame = pyogrio.read_dataframe(
        nt_bores_path("Bores_groundwater_level.shp"),
        columns=["STATION", "STATION_NA", "MONITOR_TY", "WATER_DATA", "COMMENCE",
                 "CEASE", "ACTIVE"],
    )
    frame = frame.set_geometry("geometry").to_crs(epsg=4326)
    frame["station_id"] = frame["STATION"].map(normalise_id)
    frame["lat"] = frame.geometry.y
    frame["lon"] = frame.geometry.x
    frame["commence"] = pd.to_datetime(frame["COMMENCE"], errors="coerce")
    frame["cease"] = pd.to_datetime(frame["CEASE"], errors="coerce")
    frame["WATER_DATA"] = frame["WATER_DATA"].map(fix_water_data_portal_url)
    frame = frame.dropna(subset=["station_id"]).drop_duplicates("station_id", keep="first")

    is_bore = frame["station_id"].str.startswith("RN")
    bores = frame[is_bore].copy()
    gauges = frame[~is_bore].copy()

    REPORT["monitoring_split"] = {
        "total_stations": len(frame),
        "classified_as_bore_monitoring": len(bores),
        "classified_as_river_stream_gauge": len(gauges),
        "rule": "station id starts with 'RN' after normalising -> bore monitoring "
                "location; otherwise -> river/stream gauge location type.",
    }

    def _tidy(df):
        return df[["station_id", "STATION_NA", "MONITOR_TY", "WATER_DATA", "commence",
                   "cease", "ACTIVE", "lat", "lon"]].rename(columns={
            "STATION_NA": "name", "MONITOR_TY": "monitor_type",
            "WATER_DATA": "water_data_portal", "ACTIVE": "active",
        })

    return _tidy(bores), _tidy(gauges)


def load_water_quality():
    """Bores_water_quality.shp, kept NT-wide (not filtered to Ti Tree, per the approved
    scope change). Returns the full long-format sample table and a per-bore summary."""
    import pyogrio

    measurements = {
        "Total dissolved solids": "TDS", "Laboratory electrical conductivity": "EC_LAB",
        "Chloride": "CHLORIDE", "Calculated NaCl": "NACL", "Laboratory pH": "PH_LAB",
        "Hardness": "HARD", "Alkalinity": "ALK_TOTAL", "Sodium": "NA_TOTAL",
        "Calcium": "CA_SOL", "Magnesium": "MG_SOL", "Sulphate": "SO4_TOTAL",
        "Nitrate": "NO3", "Fluoride": "F", "Iron": "FE_TOTAL", "Bicarbonate": "HCO3",
        "Field electrical conductivity (limited data)": "EC_FIELD",
        "Field pH (limited data)": "PH_FIELD", "Water temperature (limited data)": "TEMP",
    }
    columns = list(measurements.values())
    frame = pyogrio.read_dataframe(
        nt_bores_path("Bores_water_quality.shp"),
        columns=["BORE_NO", "SAMPLEDATE", *columns],
    )
    frame["bore_no"] = frame["BORE_NO"].map(normalise_id)
    frame["sample_date"] = pd.to_datetime(frame["SAMPLEDATE"], errors="coerce")
    for col in columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["bore_no", "sample_date"])
    full = frame[["bore_no", "sample_date", *columns]].rename(
        columns={v: v for v in columns}
    ).reset_index(drop=True)

    long = full.melt(id_vars=["bore_no", "sample_date"], value_vars=columns,
                     var_name="parameter", value_name="value").dropna(subset=["value"])
    long_sorted = long.sort_values("sample_date")
    latest = long_sorted.groupby(["bore_no", "parameter"])["value"].last().rename("latest")
    summary = long.groupby(["bore_no", "parameter"]).agg(
        mean=("value", "mean"), max=("value", "max"), min=("value", "min"),
        count=("value", "size"),
        first_date=("sample_date", "min"), last_date=("sample_date", "max"),
    ).join(latest).reset_index()

    REPORT["row_counts"]["water_quality_samples"] = len(full)
    REPORT["row_counts"]["water_quality_unique_bores"] = full["bore_no"].nunique()
    return full, summary, list(measurements.keys()), list(measurements.values())


def load_aquifer_layers():
    """The 5 Ti Tree-specific layers, simplified and reprojected exactly as
    krishna-code/app(v1.2).py does it, so they look the same on the map."""
    import geopandas as gpd

    layers = {}
    files = {
        "boundary": "ttbaq_250_bnd.shp", "salinity": "ttbaq_250_sal.shp",
        "aquifer_thickness": "ttbaq_250_aqt.shp", "water_depth": "ttbaq_250_wd.shp",
        "contours": "ttbaq_250_cnt.shp",
    }
    for key, filename in files.items():
        gdf = gpd.read_file(ti_tree_path(filename)).to_crs(epsg=4326)
        gdf["geometry"] = gdf.geometry.simplify(tolerance=0.0005, preserve_topology=True)
        layers[key] = gdf
    return layers


# ---------------------------------------------------------------------------
# 3. BOM rainfall — all 11 stations, tagged NT or not, via climate_models
# ---------------------------------------------------------------------------

def load_bom():
    station_files = sorted(BOM_DIR.glob("IDCJAC0009_*_1800_Note.txt"))
    stations = []
    daily_frames = []
    monthly_frames = []
    for note_path in station_files:
        station_id = note_path.name.split("_")[1]
        text = note_path.read_text(errors="replace")
        name = next((l.split(":", 1)[1].strip() for l in text.splitlines()
                    if l.startswith("Station name:")), station_id)
        lat = next((float(l.split(":", 1)[1].strip()) for l in text.splitlines()
                   if l.startswith("Latitude")), None)
        lon = next((float(l.split(":", 1)[1].strip()) for l in text.splitlines()
                   if l.startswith("Longitude")), None)

        daily = cm.load_station_daily(station=station_id, folder=BOM_DIR)
        daily_tagged = daily.copy()
        daily_tagged["station"] = station_id
        daily_frames.append(daily_tagged)

        monthly = cm.monthly_totals_from_daily(daily, max_blank_days=MAX_BLANK_DAYS)
        monthly = cm.residual_mass(monthly)
        monthly = monthly.reset_index()
        monthly["station"] = station_id
        monthly_frames.append(monthly)

        stations.append({
            "station": station_id, "name": name, "lat": lat, "lon": lon,
            "is_nt": station_id in NT_BOM_STATIONS,
            "first_date": daily["date"].min(), "last_date": daily["date"].max(),
            "n_days": len(daily),
        })

    stations_df = pd.DataFrame(stations)
    daily_df = pd.concat(daily_frames, ignore_index=True)
    monthly_df = pd.concat(monthly_frames, ignore_index=True)
    return stations_df, daily_df, monthly_df


# ---------------------------------------------------------------------------
# 4. Streamflow gauge G0280010
# ---------------------------------------------------------------------------

def load_streamflow():
    flow = cm.load_flow(station=FLOW_STATION_ID, folder=FLOW_DIR)
    quality_counts = flow["quality"].value_counts(dropna=False).sort_index()
    quality_meaning = {10: "quality-A (best available)", 90: "quality-B (compromised)",
                       110: "quality-C (estimate)", 140: "quality-E (unknown reliability)",
                       210: "quality-F (not release quality / missing)"}
    quality_report = {
        str(code): {
            "count": int(count), "share": round(count / len(flow), 4),
            "meaning": quality_meaning.get(code, "unrecognised code"),
        }
        for code, count in quality_counts.items()
    }
    monthly = cm.monthly_flow_volumes(flow, max_blank_days=MAX_BLANK_DAYS)
    monthly = cm.residual_mass(monthly).reset_index()

    quality_210_share_overall = quality_report.get("210", {}).get("share", 0.0)
    return monthly, {
        "station": FLOW_STATION_ID,
        "total_readings": len(flow),
        "quality_breakdown": quality_report,
        "quality_210_share_overall": quality_210_share_overall,
        "headline_warning": (
            f"{quality_210_share_overall:.0%} of all readings at this gauge are quality "
            "code 210 (\"not of release quality or contains missing data\"). Treat this "
            "record as indicative, not precise."
        ) if quality_210_share_overall > 0.1 else None,
    }


# ---------------------------------------------------------------------------
# 5. Bore water-level series — only the bores with a real exported file
# ---------------------------------------------------------------------------

def load_bore_waterlevels():
    """
    Picks, for each RN bore under Datasets/GroundwaterHeads_20250718/, whichever kinds and
    series it actually has on disk, reusing climate_models._read_export_series to parse
    each file. RN006543 has two export folders (a duplicate download); per the approved
    decision we use the NEWER one (the folder with the later timestamp suffix), which is
    the opposite of climate_models.bore_catalogue's own "keep the first" rule — so this
    does NOT reuse bore_catalogue, to avoid silently picking the older folder.
    """
    kinds = ["Water Elevation (AHD)", "Depth Below Ground"]
    series_kinds = ["Publish", "Field Visits"]
    waterlevel_dir = CACHE_DIR / "waterlevel"
    waterlevel_dir.mkdir(parents=True, exist_ok=True)

    folders_by_bore = {}
    for folder in sorted(GW_HEADS_DIR.glob("LocationExport-*")):
        bore = normalise_id(folder.name.split("-")[1])
        folders_by_bore.setdefault(bore, []).append(folder)

    bores_summary = []
    for bore, folders in sorted(folders_by_bore.items()):
        chosen_folder = max(folders, key=lambda f: f.name)   # newest timestamp suffix
        if len(folders) > 1:
            REPORT["bore_waterlevel_notes"].append(
                f"{bore}: {len(folders)} export folders found; used the newer one "
                f"({chosen_folder.name}), not climate_models' default (the first/older one)."
            )

        series_written = []
        for kind in kinds:
            for series_kind in series_kinds:
                tag = ".Publish@" if series_kind == "Publish" else ".Field Visits@"
                matches = [p for p in chosen_folder.glob("DataSetExport-*.csv")
                          if kind in p.name and tag in p.name]
                if not matches:
                    continue
                values = cm._read_export_series(matches[0])
                if values.empty:
                    continue
                safe_kind = kind.lower().replace(" ", "_").replace("(", "").replace(")", "")
                safe_series = series_kind.lower().replace(" ", "_")
                raw_df = values.rename("value").reset_index().rename(columns={"index": "timestamp"})
                raw_df.to_parquet(waterlevel_dir / f"{bore}__{safe_kind}__{safe_series}__raw.parquet")

                monthly = values.groupby(values.index.to_period("M")).mean()
                full_range = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M")
                monthly = monthly.reindex(full_range)
                monthly.index = monthly.index.strftime("%Y-%m")
                monthly_df = monthly.rename("value").reset_index().rename(columns={"index": "month"})
                monthly_df.to_parquet(
                    waterlevel_dir / f"{bore}__{safe_kind}__{safe_series}__monthly.parquet"
                )
                series_written.append({
                    "kind": kind, "series": series_kind, "readings": len(values),
                    "first": str(values.index.min()), "last": str(values.index.max()),
                })

        if series_written:
            has_publish = any(s["series"] == "Publish" for s in series_written)
            bores_summary.append({
                "bore_no": bore, "has_water_level": True,
                "has_dense_series": has_publish,
                "series_available": series_written,
                "source_folder": chosen_folder.name,
            })

    return pd.DataFrame(bores_summary)


# ---------------------------------------------------------------------------
# 6. "Listed but not on disk" gap — the 48-vs-16 finding
# ---------------------------------------------------------------------------

def load_waterlevel_claims():
    claimed = pd.read_csv(GW_HEADS_DIR / "Bores_w_wl_data.csv", encoding="utf-8-sig")
    claimed["bore_no"] = claimed["Bore no"].map(normalise_id)
    return set(claimed["bore_no"].dropna())


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force", action="store_true",
        help="No-op today: every run rebuilds every cache file (it takes well under a "
             "minute). Kept as a flag in case a staleness check is added later.",
    )
    parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT["generated_at"] = pd.Timestamp.now().isoformat()
    t_total = time.time()

    print("1/7  Extracting krishna-code/data.zip (read-only copy)...")
    ensure_extracted()

    print("2/7  Bores.csv + shapefile attributes...")
    t0 = time.time()
    bores_csv = load_bores_csv()
    bores_shp = load_bores_shapefile()
    bores = bores_csv.merge(bores_shp, on="bore_no", how="left")
    # Bores.csv is primary; fall back to the shapefile's lat/lon only where Bores.csv has none
    # (it never does after our own dropna, but keep the fallback honest if that changes).
    bores["latitude"] = bores["latitude"].fillna(bores["shp_lat"])
    bores["longitude"] = bores["longitude"].fillna(bores["shp_lon"])
    bores = bores.drop(columns=["shp_lat", "shp_lon"])
    waterlevel_claims = load_waterlevel_claims()
    bores["water_level_claimed"] = bores["bore_no"].isin(waterlevel_claims)
    REPORT["timings_seconds"]["bores"] = round(time.time() - t0, 2)

    print("3/7  Monitoring layer (bores vs river/stream gauges)...")
    t0 = time.time()
    monitoring_bores, gauges = load_monitoring_layer()
    REPORT["timings_seconds"]["monitoring"] = round(time.time() - t0, 2)

    print("4/7  Water quality (NT-wide, 84,769 samples)...")
    t0 = time.time()
    wq_full, wq_summary, measurement_names, measurement_columns = load_water_quality()
    bores["has_water_quality"] = bores["bore_no"].isin(wq_full["bore_no"].unique())
    REPORT["timings_seconds"]["water_quality"] = round(time.time() - t0, 2)

    print("5/7  Bore water-level series (16 bores with a real file on disk)...")
    t0 = time.time()
    waterlevel_bores = load_bore_waterlevels()
    bores["has_water_level"] = bores["bore_no"].isin(
        waterlevel_bores["bore_no"] if not waterlevel_bores.empty else []
    )
    REPORT["timings_seconds"]["bore_waterlevels"] = round(time.time() - t0, 2)

    print("6/7  BOM rainfall (11 stations) + streamflow gauge G0280010...")
    t0 = time.time()
    bom_stations, bom_daily, bom_monthly = load_bom()
    streamflow_monthly, streamflow_report = load_streamflow()
    REPORT["timings_seconds"]["bom_and_flow"] = round(time.time() - t0, 2)

    print("7/7  Ti Tree aquifer overlay layers...")
    t0 = time.time()
    aquifer_layers = load_aquifer_layers()
    REPORT["timings_seconds"]["aquifer_layers"] = round(time.time() - t0, 2)

    # Nearest-bore/gauge/station distances are computed live in server.py (a vectorised
    # haversine over a few thousand points is sub-millisecond), so the precomputed
    # bore_gauge_distances_G0280010.csv isn't needed here — it only ever covered distances
    # to one gauge, where the server can now answer that for any point on the map.

    # --- write everything ---
    print("\nWriting cache files...")
    bores.to_parquet(CACHE_DIR / "bores.parquet", index=False)
    gauges.to_parquet(CACHE_DIR / "gauges.parquet", index=False)
    monitoring_bores.to_parquet(CACHE_DIR / "monitoring_bores.parquet", index=False)
    bom_stations.to_parquet(CACHE_DIR / "bom_stations.parquet", index=False)
    bom_daily.to_parquet(CACHE_DIR / "bom_daily.parquet", index=False)
    bom_monthly.to_parquet(CACHE_DIR / "bom_monthly.parquet", index=False)
    wq_full.to_parquet(CACHE_DIR / "water_quality_full.parquet", index=False)
    wq_summary.to_parquet(CACHE_DIR / "water_quality_summary.parquet", index=False)
    streamflow_monthly.to_parquet(CACHE_DIR / "streamflow_monthly.parquet", index=False)
    waterlevel_bores.to_parquet(CACHE_DIR / "waterlevel_bores.parquet", index=False)

    (CACHE_DIR / "streamflow_quality.json").write_text(json.dumps(streamflow_report, indent=2))
    (CACHE_DIR / "measurement_names.json").write_text(
        json.dumps({"names": measurement_names, "columns": measurement_columns}, indent=2)
    )
    (CACHE_DIR / "constants.json").write_text(json.dumps({
        "FAR_STATION_WARNING_KM": FAR_STATION_WARNING_KM,
        "MAX_BLANK_DAYS": MAX_BLANK_DAYS,
        "FLOW_STATION_ID": FLOW_STATION_ID,
        "NT_BOM_STATIONS": sorted(NT_BOM_STATIONS),
    }, indent=2))

    aquifer_dir = CACHE_DIR / "aquifer"
    aquifer_dir.mkdir(exist_ok=True)
    for key, gdf in aquifer_layers.items():
        (aquifer_dir / f"{key}.geojson").write_text(gdf.to_json())

    REPORT["row_counts"].update({
        "bores": len(bores),
        "bores_with_water_level": int(bores["has_water_level"].sum()),
        "bores_claiming_water_level": int(bores["water_level_claimed"].sum()),
        "bores_with_water_quality": int(bores["has_water_quality"].sum()),
        "monitoring_bores": len(monitoring_bores),
        "river_stream_gauges": len(gauges),
        "bom_stations_total": len(bom_stations),
        "bom_stations_nt": int(bom_stations["is_nt"].sum()),
    })
    REPORT["timings_seconds"]["total"] = round(time.time() - t_total, 2)

    (CACHE_DIR / "build_report.json").write_text(
        json.dumps(REPORT, indent=2, default=str)
    )

    print(f"\nDone in {REPORT['timings_seconds']['total']}s.")
    print(f"Bores: {len(bores)} | with water level: {REPORT['row_counts']['bores_with_water_level']} "
          f"(claimed: {REPORT['row_counts']['bores_claiming_water_level']}) | "
          f"with water quality: {REPORT['row_counts']['bores_with_water_quality']}")
    print(f"River/stream gauges: {len(gauges)} | BOM stations: {len(bom_stations)} "
          f"({REPORT['row_counts']['bom_stations_nt']} in the NT)")
    print(f"See {CACHE_DIR / 'build_report.json'} for every repair, conflict and warning.")


if __name__ == "__main__":
    main()
