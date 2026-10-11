"""
webapp/server.py — HIT401 Group 34 data explorer: one process, one command.

Serves the single-page app (webapp/static/) and a JSON API over the caches built by
build_cache.py. Everything the API returns is read from webapp/cache/ at startup, which
is what keeps startup fast — nothing here re-reads a shapefile or a 480,000-row CSV per
request.

Run with (after build_cache.py has been run at least once):
    ~/venvs/hit401_web/bin/python webapp/server.py
    ~/venvs/hit401_web/bin/python webapp/server.py --port 8000 --host 127.0.0.1
"""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

WEBAPP_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBAPP_DIR.parent
CACHE_DIR = WEBAPP_DIR / "cache"
STATIC_DIR = WEBAPP_DIR / "static"

sys.path.insert(0, str(REPO_ROOT / "climate"))
import climate_models as cm  # noqa: E402

START_TIME = time.time()

# ---------------------------------------------------------------------------
# LOAD CACHES ONCE AT STARTUP
# ---------------------------------------------------------------------------

def _require_cache():
    if not (CACHE_DIR / "bores.parquet").exists():
        print("No cache found. Run this first:\n"
              "    ~/venvs/hit401_web/bin/python webapp/build_cache.py", file=sys.stderr)
        sys.exit(1)


_require_cache()

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
        return urlunparse(parsed._replace(scheme="https", netloc="ntg.aquaticinformatics.net"))
    return text


BORES = pd.read_parquet(CACHE_DIR / "bores.parquet")
GAUGES = pd.read_parquet(CACHE_DIR / "gauges.parquet")
MONITORING_BORES = pd.read_parquet(CACHE_DIR / "monitoring_bores.parquet")

BORES["water_data_portal"] = BORES["water_data_portal"].map(fix_water_data_portal_url)
if "water_data_portal_shp" in BORES.columns:
    BORES["water_data_portal_shp"] = BORES["water_data_portal_shp"].map(fix_water_data_portal_url)
MONITORING_BORES["water_data_portal"] = MONITORING_BORES["water_data_portal"].map(fix_water_data_portal_url)
GAUGES["water_data_portal"] = GAUGES["water_data_portal"].map(fix_water_data_portal_url)
BOM_STATIONS = pd.read_parquet(CACHE_DIR / "bom_stations.parquet")
BOM_MONTHLY = pd.read_parquet(CACHE_DIR / "bom_monthly.parquet")
WQ_SUMMARY = pd.read_parquet(CACHE_DIR / "water_quality_summary.parquet")
WQ_FULL = pd.read_parquet(CACHE_DIR / "water_quality_full.parquet")
STREAMFLOW_MONTHLY = pd.read_parquet(CACHE_DIR / "streamflow_monthly.parquet")
WATERLEVEL_BORES = pd.read_parquet(CACHE_DIR / "waterlevel_bores.parquet")
STREAMFLOW_QUALITY = json.loads((CACHE_DIR / "streamflow_quality.json").read_text())
MEASUREMENTS = json.loads((CACHE_DIR / "measurement_names.json").read_text())
CONSTANTS = json.loads((CACHE_DIR / "constants.json").read_text())
BUILD_REPORT = json.loads((CACHE_DIR / "build_report.json").read_text())

FAR_STATION_WARNING_KM = CONSTANTS["FAR_STATION_WARNING_KM"]
FLOW_STATION_ID = CONSTANTS["FLOW_STATION_ID"]
NT_BOM_STATIONS = set(CONSTANTS["NT_BOM_STATIONS"])

# Merge monitoring attributes onto the bore table (every monitoring station id is a bore
# id already in BORES — confirmed in build_cache.py's own report). This is what turns the
# old app's separate "Groundwater-monitoring locations" mode into a filter + a tab on the
# bore it already is, rather than a fourth marker type.
_mon = MONITORING_BORES.rename(columns={
    "station_id": "bore_no", "name": "monitor_name", "monitor_type": "monitor_type",
    "water_data_portal": "monitor_portal_url", "commence": "monitor_commence",
    "cease": "monitor_cease", "active": "monitor_active",
})
BORES = BORES.merge(
    _mon[["bore_no", "monitor_name", "monitor_type", "monitor_portal_url",
          "monitor_commence", "monitor_cease", "monitor_active"]],
    on="bore_no", how="left"
)
BORES["is_monitoring_location"] = BORES["monitor_type"].notna()

# Aquifer overlay layers, loaded once as GeoDataFrames for point lookups (the GeoJSON
# files under cache/aquifer/ are also served directly to the browser for the map).
import geopandas as gpd  # noqa: E402
from shapely.geometry import Point  # noqa: E402

AQUIFER = {
    key: gpd.read_file(CACHE_DIR / "aquifer" / f"{key}.geojson")
    for key in ("boundary", "salinity", "aquifer_thickness", "water_depth", "contours")
}
STUDY_AREA = AQUIFER["boundary"].geometry.union_all()
CONTOURS_PROJECTED = AQUIFER["contours"].to_crs(epsg=28353)

# Precompute Ti Tree study area metrics once at startup for KPI banner & quick bore search
_pts = gpd.GeoSeries(gpd.points_from_xy(BORES["longitude"], BORES["latitude"]), crs="EPSG:4326")
_sa_mask = _pts.intersects(STUDY_AREA)
STUDY_AREA_BORE_IDS = sorted(BORES.loc[_sa_mask, "bore_no"].dropna().unique().tolist())
_sa_bores_set = set(STUDY_AREA_BORE_IDS)
_sa_wq = WQ_FULL[WQ_FULL["bore_no"].isin(_sa_bores_set)]
_sa_mon = BORES.loc[_sa_mask & BORES["is_monitoring_location"]]
_sa_mon_active = _sa_mon[_sa_mon["monitor_active"] == "Current"] if "monitor_active" in _sa_mon.columns else _sa_mon

STUDY_AREA_METRICS = {
    "bores": len(STUDY_AREA_BORE_IDS),
    "quality_bores": int(_sa_wq["bore_no"].nunique()),
    "quality_samples": int(len(_sa_wq)),
    "monitoring_bores": int(len(_sa_mon)),
    "active_monitoring_bores": int(len(_sa_mon_active)),
    "bore_ids": STUDY_AREA_BORE_IDS,
}

print(f"Loaded caches: {len(BORES):,} bores, {len(GAUGES)} gauges, {len(BOM_STATIONS)} "
      f"BOM stations in {time.time() - START_TIME:.2f}s.")


# ---------------------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorised great-circle distance. lat1/lon1 can be arrays; lat2/lon2 scalars."""
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def nearest_bom_station(lat, lon, nt_only=True):
    """Nearest BOM station to a point. nt_only=True restricts to the 2 NT stations, which
    keeps 'nearest rainfall station' from ever quietly handing back Perth or Sydney."""
    pool = BOM_STATIONS[BOM_STATIONS["is_nt"]] if nt_only else BOM_STATIONS
    if pool.empty:
        return None
    distances = haversine_km(pool["lat"].to_numpy(), pool["lon"].to_numpy(), lat, lon)
    idx = int(np.argmin(distances))
    row = pool.iloc[idx]
    distance_km = float(distances[idx])
    return {
        "station": row["station"], "name": row["name"], "lat": float(row["lat"]),
        "lon": float(row["lon"]), "distance_km": round(distance_km, 1),
        "far_warning": distance_km > FAR_STATION_WARNING_KM,
    }


def nearest_gauge(lat, lon):
    if GAUGES.empty:
        return None
    distances = haversine_km(GAUGES["lat"].to_numpy(), GAUGES["lon"].to_numpy(), lat, lon)
    idx = int(np.argmin(distances))
    row = GAUGES.iloc[idx]
    distance_km = float(distances[idx])
    return {
        "station_id": row["station_id"], "name": row["name"],
        "lat": float(row["lat"]), "lon": float(row["lon"]),
        "distance_km": round(distance_km, 1),
        "far_warning": distance_km > FAR_STATION_WARNING_KM,
        "has_flow_series": row["station_id"] == FLOW_STATION_ID,
    }


def nearest_bores(lat, lon, exclude_id=None, limit=5):
    pool = BORES if exclude_id is None else BORES[BORES["bore_no"] != exclude_id]
    distances = haversine_km(pool["latitude"].to_numpy(), pool["longitude"].to_numpy(), lat, lon)
    order = np.argsort(distances)[:limit]
    out = []
    for i in order:
        row = pool.iloc[int(i)]
        out.append({
            "bore_no": row["bore_no"], "name": _clean(row["name"]),
            "distance_km": round(float(distances[int(i)]), 2),
            "lat": float(row["latitude"]), "lon": float(row["longitude"]),
        })
    return out


def _clean(value):
    """NaN/NaT/pd.NA -> None, so JSON serialises as null instead of crashing."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d") if not pd.isna(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def row_to_dict(row):
    return {col: _clean(val) for col, val in row.items()}


def aquifer_context(lat, lon):
    """Point-in-polygon / nearest-line lookup against the 5 Ti Tree layers, exactly as
    krishna-code/app(v1.2).py does it. Only meaningful inside the Ti Tree basin; outside
    it, every field says so plainly rather than returning a misleading nearest value."""
    point = Point(lon, lat)
    inside = STUDY_AREA.contains(point) or STUDY_AREA.intersects(point)
    if not inside:
        return {"inside_ti_tree_basin": False}

    def _zone(layer_key, field):
        layer = AQUIFER[layer_key]
        matches = layer[layer.geometry.covers(point)]
        if matches.empty:
            return None
        return _clean(matches.iloc[0].get(field))

    point_projected = gpd.GeoSeries([point], crs="EPSG:4326").to_crs(epsg=28353).iloc[0]
    nearest_idx = CONTOURS_PROJECTED.geometry.distance(point_projected).idxmin()
    nearest_contour_depth = _clean(AQUIFER["contours"].loc[nearest_idx].get("DEPTH_AHD"))

    return {
        "inside_ti_tree_basin": True,
        "salinity_zone": _zone("salinity", "NOTES"),
        "aquifer_thickness_m": _zone("aquifer_thickness", "AQUIFER_TH"),
        "mapped_depth_to_groundwater_m": _zone("water_depth", "DEPTH_TO"),
        "nearest_groundwater_contour_depth_ahd": nearest_contour_depth,
    }


# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------

app = FastAPI(title="HIT401 Group 34 — Data Explorer")
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.get("/api/meta")
def api_meta():
    return {
        "counts": {
            "bores": len(BORES),
            "bores_with_water_level": int(BORES["has_water_level"].sum()),
            "bores_claiming_water_level": int(BORES["water_level_claimed"].sum()),
            "bores_with_water_quality": int(BORES["has_water_quality"].sum()),
            "water_quality_samples": len(WQ_FULL),
            "monitoring_bores": int(BORES["is_monitoring_location"].sum()),
            "river_stream_gauges": len(GAUGES),
            "bom_stations": len(BOM_STATIONS),
            "bom_stations_nt": int(BOM_STATIONS["is_nt"].sum()),
        },
        "study_area": STUDY_AREA_METRICS,
        "measurements": MEASUREMENTS,
        "constants": CONSTANTS,
        "status_options": sorted(BORES["status"].dropna().unique().tolist()),
        "purpose_options": sorted(BORES["purpose"].dropna().unique().tolist()),
        "flow_station_id": FLOW_STATION_ID,
        "streamflow_quality": STREAMFLOW_QUALITY,
    }


def _build_locations_payload():
    """Every marker the map needs, in one shipment. Kept deliberately slim (one row per
    bore/gauge/station, no time series) — the browser loads this once and does its own
    clustering and filtering; the detail drawer calls /api/location/... for everything
    else, lazily, only for the one site the person clicked.

    Built ONCE at startup (not per-request): for 43k+ bores, converting the DataFrame to
    a plain dict and JSON-encoding it measurably costs tens of milliseconds, and gzip-
    compressing an 11MB payload on every request cost another ~350ms in testing. Both are
    precomputed here instead, so a request just hands back bytes already sitting in
    memory."""
    bore_cols = ["bore_no", "name", "status", "purpose", "latitude", "longitude",
                 "yield_ls", "waterlevel_m", "has_water_quality", "has_water_level",
                 "water_level_claimed", "is_monitoring_location"]
    bores_out = [
        {
            "type": "bore", "id": r["bore_no"], "name": _clean(r["name"]),
            "lat": r["latitude"], "lon": r["longitude"],
            "status": _clean(r["status"]), "purpose": _clean(r["purpose"]),
            "yield_ls": _clean(r["yield_ls"]), "waterlevel_m": _clean(r["waterlevel_m"]),
            "has_water_quality": bool(r["has_water_quality"]),
            "has_water_level": bool(r["has_water_level"]),
            "is_monitoring_location": bool(r["is_monitoring_location"]),
        }
        for r in BORES[bore_cols].to_dict("records")
    ]
    gauges_out = [
        {
            "type": "river_stream_gauge", "id": r["station_id"], "name": _clean(r["name"]),
            "lat": r["lat"], "lon": r["lon"],
            "has_flow_series": r["station_id"] == FLOW_STATION_ID,
        }
        for r in GAUGES.to_dict("records")
    ]
    stations_out = [
        {
            "type": "bom_station", "id": r["station"], "name": _clean(r["name"]),
            "lat": r["lat"], "lon": r["lon"], "is_nt": bool(r["is_nt"]),
        }
        for r in BOM_STATIONS.to_dict("records")
    ]
    return {"bores": bores_out, "gauges": gauges_out, "bom_stations": stations_out}


_t0 = time.time()
_LOCATIONS_JSON = json.dumps(_build_locations_payload()).encode("utf-8")
_LOCATIONS_GZIP = gzip.compress(_LOCATIONS_JSON, compresslevel=6)
print(f"Prebuilt /api/locations payload ({len(_LOCATIONS_JSON):,}B raw, "
      f"{len(_LOCATIONS_GZIP):,}B gzip) in {time.time() - _t0:.2f}s.")


@app.get("/api/locations")
def api_locations(request: Request):
    accepts_gzip = "gzip" in request.headers.get("accept-encoding", "")
    if accepts_gzip:
        return Response(content=_LOCATIONS_GZIP, media_type="application/json",
                        headers={"Content-Encoding": "gzip"})
    return Response(content=_LOCATIONS_JSON, media_type="application/json")


@app.get("/api/location/bore/{bore_id}")
def api_bore_detail(bore_id: str):
    match = BORES[BORES["bore_no"] == bore_id]
    if match.empty:
        raise HTTPException(404, f"No bore {bore_id}")
    row = match.iloc[0]
    lat, lon = float(row["latitude"]), float(row["longitude"])

    wq_rows = WQ_SUMMARY[WQ_SUMMARY["bore_no"] == bore_id]
    wl_row = WATERLEVEL_BORES[WATERLEVEL_BORES["bore_no"] == bore_id]
    has_wl = not wl_row.empty

    claimed_not_present = bool(row["water_level_claimed"]) and not has_wl

    return {
        "id": bore_id, "type": "bore",
        "overview": row_to_dict(row.drop(labels=[
            c for c in ["monitor_commence", "monitor_cease"] if c in row.index
        ])) | {
            "monitor_commence": _clean(row.get("monitor_commence")),
            "monitor_cease": _clean(row.get("monitor_cease")),
        },
        "data_available": {
            "water_quality": not wq_rows.empty,
            "water_level": has_wl,
            "water_level_claimed_but_missing": claimed_not_present,
            "monitoring_location": bool(row["is_monitoring_location"]),
            "aquifer_context": aquifer_context(lat, lon)["inside_ti_tree_basin"],
        },
        "water_quality_summary": wq_rows.drop(columns=["bore_no"]).to_dict("records") if not wq_rows.empty else [],
        "water_level_series_available": (
            wl_row.iloc[0]["series_available"].tolist() if has_wl else []
        ),
        "rainfall": {
            "nearest_station": nearest_bom_station(lat, lon, nt_only=True),
            "note": "Only 2 of the 11 BOM stations on file are in the NT, so most bores "
                    "are far from both. This is the nearest station's own record, not a "
                    "local rainfall estimate for this bore.",
        },
        "river_flow": {
            "nearest_gauge": nearest_gauge(lat, lon),
        },
        "nearby": {
            "bores": nearest_bores(lat, lon, exclude_id=bore_id, limit=5),
            "bom_station": nearest_bom_station(lat, lon, nt_only=False),
            "gauge": nearest_gauge(lat, lon),
        },
        "aquifer_context": aquifer_context(lat, lon),
        "data_quality_notes": _bore_data_quality_notes(bore_id, row, claimed_not_present),
    }


def _bore_data_quality_notes(bore_id, row, claimed_not_present):
    notes = []
    if claimed_not_present:
        notes.append(
            "Listed in Bores_w_wl_data.csv as having a water-level series, but that "
            "series is not in this project's data (only 16 of the 48 listed bores have "
            "an exported file on disk)."
        )
    dup_note = next(
        (n for n in BUILD_REPORT.get("bore_waterlevel_notes", []) if n.startswith(bore_id)),
        None,
    )
    if dup_note:
        notes.append(dup_note)
    if pd.isna(row.get("waterlevel_m")) and pd.isna(row.get("depth_to_water_m")):
        notes.append("No static water-level reading recorded for this bore in either source file.")
    return notes


@app.get("/api/location/gauge/{station_id}")
def api_gauge_detail(station_id: str):
    match = GAUGES[GAUGES["station_id"] == station_id]
    if match.empty:
        raise HTTPException(404, f"No gauge {station_id}")
    row = match.iloc[0]
    lat, lon = float(row["lat"]), float(row["lon"])
    has_series = station_id == FLOW_STATION_ID
    return {
        "id": station_id, "type": "river_stream_gauge",
        "overview": row_to_dict(row),
        "data_available": {"flow_series": has_series},
        "flow_quality": STREAMFLOW_QUALITY if has_series else None,
        "nearby": {
            "bores": nearest_bores(lat, lon, limit=5),
            "bom_station": nearest_bom_station(lat, lon, nt_only=False),
        },
        "aquifer_context": aquifer_context(lat, lon),
        "data_quality_notes": (
            [] if has_series else
            ["This location is a river/stream gauge code found in the groundwater-"
             "monitoring layer, but no discharge time series for it is in this "
             "project's data. Only G0280010 (Woodforde River at Arden Soak) has one."]
        ),
    }


@app.get("/api/location/bom_station/{station_id}")
def api_bom_station_detail(station_id: str):
    match = BOM_STATIONS[BOM_STATIONS["station"] == station_id]
    if match.empty:
        raise HTTPException(404, f"No BOM station {station_id}")
    row = match.iloc[0]
    lat, lon = float(row["lat"]), float(row["lon"])
    return {
        "id": station_id, "type": "bom_station",
        "overview": row_to_dict(row),
        "data_available": {"daily_rainfall": True},
        "nearby": {"bores": nearest_bores(lat, lon, limit=5)},
        "data_quality_notes": (
            [] if row["is_nt"] else
            [f"{row['name']} is not in the Northern Territory. It is kept in this "
             "dataset for comparison/testing but excluded from 'nearest rainfall "
             "station' results and hidden on the map by default."]
        ),
    }


@app.get("/api/water-quality-map")
def api_water_quality_map(parameter: str = Query(...), statistic: str = Query("latest")):
    """Every bore's value for one chemical parameter, for the 'colour the whole map by
    this chemical, against a threshold' mode (the old app's Chemical-threshold map,
    generalised to all NT bores instead of just Ti Tree). Lazy — only fetched when this
    colour-by mode is actually chosen, not shipped with the base /api/locations payload."""
    columns = MEASUREMENTS["columns"]
    if parameter not in columns:
        raise HTTPException(400, f"Unknown parameter {parameter}. Use one of {columns}.")
    if statistic not in ("latest", "mean", "max", "min"):
        raise HTTPException(400, "statistic must be one of latest, mean, max, min")
    rows = WQ_SUMMARY[WQ_SUMMARY["parameter"] == parameter]
    values = rows.set_index("bore_no")[statistic].dropna()
    default_threshold = float(values.median()) if not values.empty else 0.0
    return {
        "parameter": parameter, "statistic": statistic,
        "values": {k: float(v) for k, v in values.items()},
        "default_threshold": round(default_threshold, 2),
        "min": round(float(values.min()), 2) if not values.empty else None,
        "max": round(float(values.max()), 2) if not values.empty else None,
    }


@app.get("/api/water-quality/{bore_id}")
def api_water_quality_series(bore_id: str, parameter: str = Query(...)):
    columns = MEASUREMENTS["columns"]
    if parameter not in columns:
        raise HTTPException(400, f"Unknown parameter {parameter}. Use one of {columns}.")
    rows = WQ_FULL[WQ_FULL["bore_no"] == bore_id][["sample_date", parameter]].dropna()
    rows = rows.sort_values("sample_date")
    vals = rows[parameter].astype(float)
    stats = None
    if not vals.empty:
        stats = {
            "min": round(float(vals.min()), 2),
            "max": round(float(vals.max()), 2),
            "mean": round(float(vals.mean()), 2),
            "median": round(float(vals.median()), 2),
            "count": int(len(vals)),
        }
    return {
        "bore_no": bore_id, "parameter": parameter,
        "dates": rows["sample_date"].dt.strftime("%Y-%m-%d").tolist(),
        "values": vals.tolist(),
        "statistics": stats,
    }


@app.get("/api/water-level/{bore_id}")
def api_water_level_series(
    bore_id: str,
    kind: str = Query("water_elevation_ahd"),
    series: str = Query("publish"),
):
    safe_kind = kind.lower().replace(" ", "_").replace("(", "").replace(")", "")
    safe_series = series.lower().replace(" ", "_")
    path = CACHE_DIR / "waterlevel" / f"{bore_id}__{safe_kind}__{safe_series}__monthly.parquet"
    if not path.exists():
        # fall back to whatever IS available for this bore, so the drawer never just errors
        wl_row = WATERLEVEL_BORES[WATERLEVEL_BORES["bore_no"] == bore_id]
        if wl_row.empty:
            raise HTTPException(404, f"No water-level series for {bore_id}")
        available = wl_row.iloc[0]["series_available"]
        if len(available) == 0:
            raise HTTPException(404, f"No water-level series for {bore_id}")
        first = available[0]
        safe_kind = first["kind"].lower().replace(" ", "_").replace("(", "").replace(")", "")
        safe_series = first["series"].lower().replace(" ", "_")
        path = CACHE_DIR / "waterlevel" / f"{bore_id}__{safe_kind}__{safe_series}__monthly.parquet"
        if not path.exists():
            raise HTTPException(404, f"No water-level series for {bore_id}")
    table = pd.read_parquet(path)
    valid_vals = [float(v) for v in table["value"] if pd.notna(v)]
    stats = None
    if valid_vals:
        s = pd.Series(valid_vals, dtype=float)
        stats = {
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "mean": round(float(s.mean()), 2),
            "median": round(float(s.median()), 2),
            "count": int(len(s)),
        }
    return {
        "bore_no": bore_id, "kind": safe_kind, "series": safe_series,
        "months": table["month"].tolist(),
        "values": [None if pd.isna(v) else float(v) for v in table["value"]],
        "statistics": stats,
    }


@app.get("/api/rainfall/{station_id}")
def api_rainfall(station_id: str):
    match = BOM_MONTHLY[BOM_MONTHLY["station"] == station_id]
    if match.empty:
        raise HTTPException(404, f"No rainfall data for station {station_id}")
    match = match.sort_values("month")
    return {
        "station": station_id,
        "months": match["month"].tolist(),
        "total_mm": [None if pd.isna(v) else float(v) for v in match["total"]],
        "complete": match["complete"].tolist(),
        "cumulative_residual_mm": [None if pd.isna(v) else float(v) for v in match["cumulative"]],
        "max_blank_days_rule": CONSTANTS["MAX_BLANK_DAYS"],
    }


@app.get("/api/flow")
def api_flow():
    table = STREAMFLOW_MONTHLY.sort_values("month")
    return {
        "station": FLOW_STATION_ID,
        "months": table["month"].tolist(),
        "total_ML": [None if pd.isna(v) else float(v) for v in table["total"]],
        "complete": table["complete"].tolist(),
        "quality_210_share": [
            None if pd.isna(v) else float(v) for v in table["quality_210_share"]
        ],
        "cumulative_residual_ML": [None if pd.isna(v) else float(v) for v in table["cumulative"]],
        "quality_report": STREAMFLOW_QUALITY,
    }


@app.get("/api/place")
def api_place(lat: float = Query(...), lon: float = Query(...)):
    """'Click anywhere on the map' — a summary for a point that is not an existing marker."""
    return {
        "lat": lat, "lon": lon,
        "nearby": {
            "bores": nearest_bores(lat, lon, limit=5),
            "bom_station": nearest_bom_station(lat, lon, nt_only=False),
            "nt_bom_station": nearest_bom_station(lat, lon, nt_only=True),
            "gauge": nearest_gauge(lat, lon),
        },
        "aquifer_context": aquifer_context(lat, lon),
    }


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    needle = q.strip().upper()
    if not needle:
        return {"results": []}
    results = []

    bore_hits = BORES[
        BORES["bore_no"].str.contains(needle, case=False, na=False)
        | BORES["name"].str.upper().str.contains(needle, na=False)
    ].head(25)
    for r in bore_hits.to_dict("records"):
        results.append({"type": "bore", "id": r["bore_no"], "label": f"{r['bore_no']} — {_clean(r['name']) or 'unnamed'}",
                        "lat": r["latitude"], "lon": r["longitude"]})

    gauge_hits = GAUGES[
        GAUGES["station_id"].str.contains(needle, case=False, na=False)
        | GAUGES["name"].str.upper().str.contains(needle, na=False)
    ].head(10)
    for r in gauge_hits.to_dict("records"):
        results.append({"type": "river_stream_gauge", "id": r["station_id"],
                        "label": f"{r['station_id']} — {_clean(r['name']) or 'unnamed gauge'}",
                        "lat": r["lat"], "lon": r["lon"]})

    station_hits = BOM_STATIONS[
        BOM_STATIONS["station"].str.contains(needle, case=False, na=False)
        | BOM_STATIONS["name"].str.upper().str.contains(needle, na=False)
    ].head(10)
    for r in station_hits.to_dict("records"):
        results.append({"type": "bom_station", "id": r["station"],
                        "label": f"{r['name']} ({r['station']})" + ("" if r["is_nt"] else " — not NT"),
                        "lat": r["lat"], "lon": r["lon"]})

    if not results:
        results.append({"type": "none", "label": (
            f"No bore, gauge or BOM station matches '{q}'. Search only covers IDs and "
            "names in this project's data — there is no town or state lookup, since "
            "none of the source files carry that field."
        )})
    return {"results": results}


@app.get("/api/about")
def api_about():
    citations_path = REPO_ROOT / "docs" / "climate" / "CITATIONS_CMIP6.md"
    notes_path = REPO_ROOT / "docs" / "climate" / "climate_data_notes.md"
    return {
        "citations_markdown": citations_path.read_text() if citations_path.exists() else None,
        "data_notes_markdown": notes_path.read_text() if notes_path.exists() else None,
        "sources": [
            "NT Natural Resource Maps — Bores.csv and bore shapefiles (Dr Cat Kutay / "
            "A/Prof Dylan Irvine, supplied by email; also at nrmaps.nt.gov.au)",
            "NT groundwater monitoring exports, GroundwaterHeads_20250718 (supplied by "
            "Dr Cat Kutay, April 2025)",
            "Bureau of Meteorology daily rainfall, product IDCJAC0009 "
            "(bom.gov.au/climate/data)",
            "NT water-course discharge, gauge G0280010 (NT Dept of Lands, Planning and "
            "Environment)",
            "CMIP6 climate projections via ESGF — see the citations file for the full, "
            "per-model licence and DOI table, including which entries are UNVERIFIED",
        ],
        "limitations": [
            "Water-quality samples run from 1909 to 2021 across the NT and are historical "
            "— nothing here is a current reading.",
            "Only 2 of the 11 BOM stations on file are actually in the NT; the rest are "
            "interstate and shown only for comparison, hidden on the map by default.",
            f"{STREAMFLOW_QUALITY.get('quality_210_share_overall', 0):.0%} of all "
            "readings at gauge G0280010 are quality code 210 ('not of release quality or "
            "contains missing data').",
            "48 bores are listed as having a water-level time series; only 16 actually "
            "have an exported file in this project's data.",
            "CNRM-CM6-1-HR's CMIP6 output is CC BY-NC-SA 4.0 (NonCommercial); the other "
            "ten models used are CC BY-SA 4.0. See the citations file before any "
            "commercial use.",
            "Several model DOIs are marked UNVERIFIED in the citations file — they were "
            "not re-checked against DataCite in this session.",
        ],
    }


# ---------------------------------------------------------------------------
# CLIMATE — reuses climate/climate_models.py directly, read-only
# ---------------------------------------------------------------------------

@app.get("/api/climate/meta")
def api_climate_meta():
    if not cm.DATA_DIR.exists():
        return {"available": False, "message": f"No climate data folder at {cm.DATA_DIR}."}
    out = {"available": True, "locations": {}}
    for location in cm.LOCATIONS:
        good, bad = cm.usable_runs(location)
        out["locations"][location] = {"usable_runs": good, "unusable": bad}
    return out


# The two climate endpoints below return plain chart data (arrays + colours + the
# reference-period window), not a Plotly figure object. climate_models.py's own
# plot_anomaly_bars()/plot_wetter_or_drier() build go.Figure objects, which would need
# the `plotly` Python package on the server — that package was not in the approved
# install list for this venv. Rather than ask for an extra install mid-build, this reuses
# climate_models' DATA functions (water_year_totals, anomalies, trailing_mean,
# change_table, cell_info) and its own colour constants directly, and leaves the actual
# figure construction to Plotly.js in the browser (already vendored for every other
# chart on the page). The numbers and colours are identical to what plot_anomaly_bars()
# and plot_wetter_or_drier() would draw; only which language builds the Figure differs.

@app.get("/api/climate/anomaly")
def api_climate_anomaly(location: str = Query(...), run: str = Query(...)):
    try:
        monthly = cm.load_monthly_pr(run, location)
        totals = cm.water_year_totals(monthly)
        anomaly = cm.anomalies(totals)
        rolling = cm.trailing_mean(totals)
        anomaly = anomaly[anomaly.index >= cm.FIRST_PLOT_YEAR]
        ref_mean = cm.reference_mean(totals)
        cell = cm.cell_info(run, location)
    except Exception as exc:
        raise HTTPException(400, f"Could not build this chart: {exc}")

    return {
        "location": location, "run": run,
        "years": anomaly.index.tolist(),
        "anomaly_mm": [round(float(v), 1) for v in anomaly.values],
        "wetter_color": cm.COLOUR_WETTER, "drier_color": cm.COLOUR_DRIER,
        "reference_shade_color": cm.COLOUR_REFERENCE_SHADE,
        "reference_period": list(cm.REFERENCE_PERIOD),
        "trailing_mean": {
            "years": rolling.index.tolist(),
            "anomaly_mm": [round(float(v - ref_mean), 1) for v in rolling.values],
        },
        "trailing_mean_window_years": cm.MOVING_MEAN_WINDOW,
        "line_color": cm.COLOUR_LINE,
        "title": f"{location}: water-year rainfall, {run}, {cm.SCENARIO_LABEL}",
        "subtitle": cm.ANOMALY_SUBTITLE,
        "footnote": (
            f"Model grid cell centre {cell[0]:.2f}, {cell[1]:.2f} is {cell[2]:.0f} km "
            f"from {location}. " if cell else ""
        ) + (f"The {cm.MOVING_MEAN_WINDOW}-year moving mean is trailing, computed on the "
             f"full series from 1850 and then cropped to {cm.FIRST_PLOT_YEAR}."),
        "credit": cm.CREDIT_TEXT,
    }


@app.get("/api/climate/wetter-drier")
def api_climate_wetter_drier(location: str = Query(...)):
    try:
        table = cm.change_table(location)
        if table.empty:
            raise ValueError(cm.missing_message(location) or f"No model data for {location}")
    except Exception as exc:
        raise HTTPException(400, f"Could not build this chart: {exc}")

    rows = table.iloc[::-1].reset_index(drop=True)   # wettest at the top
    labels = rows["model_run"].tolist()
    means = rows["mean_pct"].tolist()
    medians = rows["median_pct"].tolist()
    distances = [cm.cell_info(label, location)[2] for label in labels if cm.cell_info(label, location)]
    wetter = int((table["mean_pct"] > 0).sum())

    return {
        "location": location,
        "labels": labels,
        "mean_pct": [round(float(v), 1) for v in means],
        "median_pct": [round(float(v), 1) for v in medians],
        "wetter_color": cm.COLOUR_WETTER, "drier_color": cm.COLOUR_DRIER,
        "line_color": cm.COLOUR_LINE,
        "reference_period": list(cm.REFERENCE_PERIOD), "future_period": list(cm.FUTURE_PERIOD),
        "scenario_label": cm.SCENARIO_LABEL,
        "models_wetter": wetter, "models_total": len(table),
        "footnote": (
            f"Each model has its own grid; the cell centres used are "
            f"{min(distances):.0f}-{max(distances):.0f} km from {location}."
            if distances else ""
        ),
        "credit": cm.CREDIT_TEXT,
    }


# ---------------------------------------------------------------------------
# SEASONAL RECHARGE, LAG CORRELATIONS & MULTI-SERIES COMPARISON
# ---------------------------------------------------------------------------

@app.get("/api/climate/seasonal")
def api_climate_seasonal(
    location: str = Query("Ti Tree"),
    station: str = Query(None),
    runs: str = Query(None),
    to_2099: bool = Query(False),
):
    if location not in cm.LOCATIONS:
        raise HTTPException(400, f"Unknown location '{location}'. Must be one of {cm.LOCATIONS}")

    start_year = 1987
    end_year = 2099 if to_2099 else 2025

    # 1. Observed seasonal totals (seasonal_totals_observed)
    observed_data = None
    observed_df = None
    target_station = station if station else (cm.TI_TREE_STATION if location == "Ti Tree" else None)
    if target_station:
        try:
            observed_df = cm.seasonal_totals_observed(station=target_station)
            part = observed_df[(observed_df.index >= start_year) & (observed_df.index <= end_year)]
            observed_data = {
                "station": target_station,
                "years": part.index.tolist(),
                "wet": [None if pd.isna(v) else round(float(v), 1) for v in part["wet"]],
                "wet_missing": [int(v) for v in part["wet_missing"]],
                "dry": [None if pd.isna(v) else round(float(v), 1) for v in part["dry"]],
                "dry_missing": [int(v) for v in part["dry_missing"]],
            }
        except FileNotFoundError:
            observed_data = None
        except Exception as exc:
            raise HTTPException(400, f"Could not load observed seasonal totals: {exc}")

    # 2. Model seasonal totals (seasonal_totals_model)
    available = cm.available_runs(location)
    if runs:
        selected_runs = [r.strip() for r in runs.split(",") if r.strip() and r.strip() in available]
    else:
        preferred = ["ACCESS-ESM1-5 r6 (v2105)", "GFDL-ESM4", "NorESM2-MM"]
        selected_runs = [r for r in preferred if r in available]
        if not selected_runs:
            selected_runs = available[:3]

    model_tables = {}
    models_data = {}
    for r in selected_runs:
        try:
            m_df = cm.seasonal_totals_model(r, location=location)
            model_tables[r] = m_df
            part = m_df[(m_df.index >= start_year) & (m_df.index <= end_year)]
            models_data[r] = {
                "years": part.index.tolist(),
                "wet": [None if pd.isna(v) else round(float(v), 1) for v in part["wet"]],
                "dry": [None if pd.isna(v) else round(float(v), 1) for v in part["dry"]],
            }
        except Exception as exc:
            print(f"Warning: could not load model {r}: {exc}", file=sys.stderr)

    # 3. Server-generated figure using plot_seasonal where available
    figure_dict = None
    if observed_df is not None and model_tables:
        try:
            fig = cm.plot_seasonal(observed_df, model_tables, location=location,
                                   start_year=start_year, end_year=end_year)
            figure_dict = json.loads(fig.to_json())
        except Exception:
            figure_dict = None

    footnote = (
        "Outlined bars are seasons with at least one missing month in the gauge record. "
        if observed_data else
        f"No local observed BOM daily rainfall record available for {location}; showing climate model projections only. "
    )
    if to_2099:
        footnote += "Projections shown out to 2099."

    return {
        "location": location,
        "station": target_station,
        "start_year": start_year,
        "end_year": end_year,
        "observed": observed_data,
        "models": models_data,
        "available_runs": available,
        "selected_runs": selected_runs,
        "figure": figure_dict,
        "title": f"{location}: wet season (Nov-Apr) and dry season (May-Oct) rainfall",
        "subtitle": "Observed rainfall vs CMIP6 model projections. Seasons are labelled by their start year.",
        "footnote": footnote,
        "credit": cm.CREDIT_TEXT,
    }


@app.get("/api/climate/lag")
def api_climate_lag(
    bore_id: str = Query(None),
    driver: str = Query("rainfall"),
    max_lag: int = Query(cm.MAX_LAG_MONTHS),
):
    driver_norm = driver.strip().lower()
    if driver_norm in ("rainfall", "rain"):
        try:
            source = cm.rainfall_residual_mass()
        except Exception as exc:
            raise HTTPException(400, f"Could not load rainfall series: {exc}")
        driver_label = "Rainfall"
    elif driver_norm in ("flow", "river_flow", "streamflow"):
        try:
            source = cm.flow_residual_mass()
        except Exception as exc:
            raise HTTPException(400, f"Could not load river flow series: {exc}")
        driver_label = "River flow"
    else:
        raise HTTPException(400, f"Unknown driver '{driver}'. Use 'rainfall' or 'flow'.")

    chosen, _ = cm.choose_bores(limit=10)
    qualifying_bores = chosen["bore"].tolist() if not chosen.empty else []

    target_bore = bore_id if bore_id else (qualifying_bores[0] if qualifying_bores else None)
    if not target_bore:
        raise HTTPException(404, "No bore with water-level series available.")

    try:
        levels = cm.bore_monthly_level(target_bore)
        if levels.dropna().empty:
            raise ValueError(f"Bore {target_bore} has no recorded monthly levels.")
    except Exception as exc:
        raise HTTPException(404, f"Could not load water levels for bore {target_bore}: {exc}")

    driver_anomaly = cm.monthly_anomaly(source)
    response_change = cm.level_change(levels)
    results = cm.lag_correlations(driver_anomaly, response_change, max_lag=max_lag)

    # Calculate best lag and note
    usable = results.dropna(subset=["r"])
    reliable = usable[usable["n_months"] >= cm.MIN_PAIRED_MONTHS]
    best = (reliable.loc[reliable["r"].abs().idxmax()] if not reliable.empty else None)

    title = f"{target_bore} water-level change vs {driver_label.lower()} anomaly"
    subtitle = f"Monthly {driver_label.lower()} anomaly leading the month-to-month change in bore level."

    figure_dict = None
    try:
        fig = cm.plot_lag_correlation(results, title, subtitle)
        figure_dict = json.loads(fig.to_json())
    except Exception:
        figure_dict = None

    thin = results[results["n_months"] < cm.MIN_PAIRED_MONTHS]["lag_months"].tolist()
    note = (
        "Correlation is not causation; the bore series are short and gappy, so these "
        "numbers are a hint about timing, not proof. Paired months per lag: "
        f"{int(results['n_months'].min())}-{int(results['n_months'].max())}."
    )
    if thin:
        note += (
            f" Lags {', '.join(str(int(l)) for l in thin)} rest on fewer than "
            f"{cm.MIN_PAIRED_MONTHS} paired months and are not treated as findings."
        )
    if best is None:
        note += (
            f" No lag reaches {cm.MIN_PAIRED_MONTHS} paired months, so no strongest lag is marked."
        )

    return {
        "bore_id": target_bore,
        "driver": driver_label,
        "available_bores": qualifying_bores,
        "max_lag": max_lag,
        "min_paired_months": cm.MIN_PAIRED_MONTHS,
        "lags": results["lag_months"].tolist(),
        "r": [None if pd.isna(v) else round(float(v), 3) for v in results["r"]],
        "n_months": [int(v) for v in results["n_months"]],
        "best_lag": int(best["lag_months"]) if best is not None else None,
        "best_r": round(float(best["r"]), 3) if best is not None else None,
        "best_n": int(best["n_months"]) if best is not None else None,
        "figure": figure_dict,
        "title": title,
        "subtitle": subtitle,
        "footnote": note,
        "credit": cm.CREDIT_TEXT,
        "wetter_color": cm.COLOUR_WETTER,
        "drier_color": cm.COLOUR_DRIER,
    }


@app.get("/api/climate/rain-flow-bores")
def api_climate_rain_flow_bores(
    start: str = Query("2010-01"),
    bores: str = Query(None),
):
    try:
        rain = cm.rainfall_residual_mass()
        flow = cm.flow_residual_mass()
    except Exception as exc:
        raise HTTPException(400, f"Could not load rainfall or flow residual mass: {exc}")

    chosen, _ = cm.choose_bores(limit=3)
    if bores:
        requested = [b.strip() for b in bores.split(",") if b.strip()]
    else:
        requested = chosen["bore"].tolist() if not chosen.empty else []

    levels = {}
    for b in requested:
        try:
            lvl = cm.bore_monthly_level(b)
            if not lvl.dropna().empty:
                levels[b] = lvl
        except Exception:
            pass

    if not levels:
        raise HTTPException(404, "No bore water-level series available for plotting.")

    caption = (
        f"Bores {', '.join(levels.keys())}. Rain station {cm.TI_TREE_STATION} is about 34 km from "
        f"gauge {cm.FLOW_STATION}. Gaps in the bore lines are left open."
    )

    figure_dict = None
    try:
        fig = cm.plot_rain_flow_bores(rain, flow, levels, start=start, caption=caption)
        figure_dict = json.loads(fig.to_json())
    except Exception as exc:
        raise HTTPException(400, f"Could not build the multi-panel plot: {exc}")

    # Build CSV export rows
    r_part = rain[rain.index >= start]
    f_part = flow[flow.index >= start]
    all_months = sorted(set(r_part.index) | set(f_part.index))
    for b, s in levels.items():
        all_months = sorted(set(all_months) | set(s[s.index >= start].index))

    rows = []
    r_cum = r_part["residual"].cumsum()
    f_cum = f_part["residual"].cumsum()
    for m in all_months:
        row = {"month": m}
        row["rainfall_total_mm"] = round(float(r_part.loc[m, "total"]), 2) if (m in r_part.index and pd.notna(r_part.loc[m, "total"])) else None
        row["rainfall_cum_residual_mm"] = round(float(r_cum.loc[m]), 2) if (m in r_cum.index and pd.notna(r_cum.loc[m])) else None
        row["flow_total_ML"] = round(float(f_part.loc[m, "total"]), 2) if (m in f_part.index and pd.notna(f_part.loc[m, "total"])) else None
        row["flow_cum_residual_ML"] = round(float(f_cum.loc[m]), 2) if (m in f_cum.index and pd.notna(f_cum.loc[m])) else None
        for b, s in levels.items():
            row[f"water_level_{b}_m_AHD"] = round(float(s.loc[m]), 3) if (m in s.index and pd.notna(s.loc[m])) else None
        rows.append(row)

    return {
        "start": start,
        "bores": list(levels.keys()),
        "available_bores": chosen["bore"].tolist() if not chosen.empty else list(levels.keys()),
        "caption": caption,
        "figure": figure_dict,
        "rows": rows,
        "credit": cm.CREDIT_TEXT,
    }


# ---------------------------------------------------------------------------
# STATIC FILES — the SPA itself
# ---------------------------------------------------------------------------

app.mount("/aquifer_geo", StaticFiles(directory=CACHE_DIR / "aquifer"), name="aquifer_geo")
app.mount("/vendor", StaticFiles(directory=STATIC_DIR / "vendor"), name="vendor")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"Starting server at http://{args.host}:{args.port} "
          f"(ready {time.time() - START_TIME:.2f}s after launch)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
