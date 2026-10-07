"""
download_cmip6_pr.py - fetch CMIP6 monthly precipitation (Amon, pr) for ONE grid cell.

What it does
------------
1. Searches the ESGF search API for the latest `pr` files of each climate-model run
   (experiments: historical and ssp245 only).
2. Reads each file over OPeNDAP. OPeNDAP lets us ask the server for just one grid cell,
   so we transfer a few kB per file instead of the whole global file (hundreds of MB).
3. Picks the model grid cell NEAREST to a point (not a box average).
4. Saves the cell's time series to  data/climate/pr_<model>_<run>_<experiment>_<location>.nc
   Files that already exist are skipped. Existing data files are never modified.

Safety: with no flags the script only SEARCHES (metadata, no data). Data is only read when
you pass --coords (grid coordinates only) or --download (the actual cell time series).
No login, account, terms or API key is used; if a server asks for one the script stops.

Examples
--------
    python climate/download_cmip6_pr.py                      # search only: what is available?
    python climate/download_cmip6_pr.py --coords             # also read lat/lon, report nearest cell
    python climate/download_cmip6_pr.py --download           # fetch and save the cell time series
    python climate/download_cmip6_pr.py --models GFDL-ESM4 --locations Darwin --download
"""

import argparse
import math
import re
import sys
import threading
import time
from pathlib import Path

import requests

# ---------------------------------------------------------
# SETTINGS (edit here)
# ---------------------------------------------------------

# Point locations (lat, lon in degrees). Model longitude is 0-360, so these work as is.
LOCATIONS = {
    "Darwin": (-12.46, 130.84),
    "Ti Tree": (-22.1, 133.4),
}

EXPERIMENTS = ["historical", "ssp245"]

ESGF_SEARCH = "https://esgf.nci.org.au/esg-search/search"
NCI_HOST = "esgf.nci.org.au"
# Hosts tried in this order. NCI first; CEDA only if NCI does not hold the SAME member.
HOST_PREFERENCE = [NCI_HOST, "esgf.ceda.ac.uk"]

# GFDL-ESM4 historical is NOT on NCI. It is read from CEDA instead (known file names).
CEDA_GFDL_HIST_BASE = (
    "https://esgf.ceda.ac.uk/thredds/dodsC/esg_cmip6/CMIP6/CMIP/NOAA-GFDL/GFDL-ESM4/"
    "historical/r1i1p1f1/Amon/pr/gr1/v20190726/"
)
CEDA_GFDL_HIST_FILES = [
    "pr_Amon_GFDL-ESM4_historical_r1i1p1f1_gr1_185001-194912.nc",
    "pr_Amon_GFDL-ESM4_historical_r1i1p1f1_gr1_195001-201412.nc",
]

# Model runs matched to the supervisor's slides (non-"coupled" rows of slide 31).
# label = name used on the slide; member = CMIP6 variant label (r1i1p1f1 unless known).
MODEL_RUNS = [
    {"label": "GFDL-ESM4",                "source_id": "GFDL-ESM4",     "member": "r1i1p1f1"},
    {"label": "ACCESS-CM2",               "source_id": "ACCESS-CM2",    "member": "r1i1p1f1"},
    {"label": "EC-Earth3",                "source_id": "EC-Earth3",     "member": "r1i1p1f1"},
    {"label": "MRI-ESM2-0",               "source_id": "MRI-ESM2-0",    "member": "r1i1p1f1"},
    {"label": "MPI-ESM1-2-LR",            "source_id": "MPI-ESM1-2-LR", "member": "r1i1p1f1"},
    {"label": "FGOALS-g3",                "source_id": "FGOALS-g3",     "member": "r1i1p1f1"},
    {"label": "CNRM-CM6-1-HR",            "source_id": "CNRM-CM6-1-HR", "member": "r1i1p1f2"},  # f2, not f1: only f2 exists on NCI
    {"label": "GISS-E2-1-G",              "source_id": "GISS-E2-1-G",   "member": "r1i1p1f2"},  # f2: only p1 pair present in BOTH experiments
    {"label": "CMCC-ESM2",                "source_id": "CMCC-ESM2",     "member": "r1i1p1f1"},
    {"label": "ACCESS-ESM1-5 r6 (v2105)", "source_id": "ACCESS-ESM1-5", "member": "r6i1p1f1"},
    {"label": "NorESM2-MM",               "source_id": "NorESM2-MM",    "member": "r1i1p1f1"},
]

# Slide-31 rows marked "(coupled ...)". We do not know what "coupled" means here, so we do
# NOT guess which files they are. They are listed in the report as unmatched.
UNMATCHED_COUPLED = [
    "CNRM-CM6-1-HR (coupled)",
    "ACCESS-ESM1-5 r20 (coupled v2112)",
    "NorESM2-MM (coupled)",
    "ACCESS-ESM1-5 r40 (coupled v2112)",
]

MAX_DOWNLOAD_BYTES = 100 * 1_000_000   # stop and ask before any single read above this (bytes TRANSFERRED,
                                         # not the size of the whole file on the server)
MAX_TOTAL_BYTES = 500 * 1_000_000      # stop and ask if the whole run would transfer more than this
MAX_COORD_BYTES = 1 * 1_000_000        # stop if reading grid coordinates exceeds this
BYTES_PER_VALUE = 4                      # pr is float32

MAX_TRIES = 3                            # attempts per remote operation before skipping it
READ_TIMEOUT_S = 180                     # give up on one attempt after this many seconds
SEARCH_TIMEOUT_S = (10, 60)              # (connect, read) timeout for the search API

# The ONLY hosts this script reads data from (the search API host is NCI as well).
ALLOWED_HOSTS = {NCI_HOST, "esgf.ceda.ac.uk"}

# This file lives in climate/, so the repository root is one level up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "climate"
SENSITIVITY_DIR = OUT_DIR / "sensitivity"    # 3x3 neighbourhood tests, kept apart from the main data


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

class StopAndAsk(Exception):
    """Raised when the script must stop and hand the decision back to the user."""


def safe_name(text):
    """Make a string safe for use in a file name (e.g. 'Ti Tree' -> 'TiTree')."""
    return "".join(ch for ch in text if ch.isalnum() or ch in "-_")


def out_path(source_id, member, experiment, location):
    return OUT_DIR / f"pr_{source_id}_{member}_{experiment}_{safe_name(location)}.nc"


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points (degrees)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


class RemoteFailure(Exception):
    """A remote server kept failing after MAX_TRIES attempts; the caller skips that item."""


class Budget:
    """Running total of bytes transferred in this run; stops the script above MAX_TOTAL_BYTES."""

    def __init__(self):
        self.total = 0

    def add(self, nbytes, what):
        if self.total + nbytes > MAX_TOTAL_BYTES:
            raise StopAndAsk(
                f"Reading {what} would take the run past the {MAX_TOTAL_BYTES/1e6:.0f} MB total cap "
                f"(already {self.total/1e6:.2f} MB). Ask before continuing."
            )
        self.total += nbytes


BUDGET = Budget()


def check_host(url):
    """Refuse to read from any host other than ALLOWED_HOSTS."""
    host = url.split("/")[2]
    if host not in ALLOWED_HOSTS:
        raise StopAndAsk(f"Refusing to read from unexpected host {host} ({url})")


def call_with_timeout(fn, seconds):
    """
    Run fn() in a background thread and give up waiting after `seconds`.
    (netCDF4/OPeNDAP has no timeout setting we can pass in, so we time out from outside.
    A hung attempt is abandoned; it cannot be killed but will not block the script exiting.)
    """
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as exc:    # hand any error back to the calling thread
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise TimeoutError(f"no response after {seconds}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def with_retries(fn, what):
    """Call fn() up to MAX_TRIES times with a timeout; raise RemoteFailure if it keeps failing."""
    last = None
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return call_with_timeout(fn, READ_TIMEOUT_S)
        except StopAndAsk:
            raise                        # decisions for the user are never retried
        except Exception as exc:
            check_auth_error(exc)        # a login request stops everything
            last = exc
            print(f"    warning: {what} failed (try {attempt}/{MAX_TRIES}): {str(exc)[:100]}")
            time.sleep(2 * attempt)
    raise RemoteFailure(f"{what} failed after {MAX_TRIES} tries: {str(last)[:100]}")


def check_auth_error(exc):
    """If a server wants a login, stop. We never create accounts or use keys."""
    text = str(exc)
    if any(code in text for code in ("401", "403", "Unauthorized", "Forbidden")):
        raise StopAndAsk(
            "The server appears to require a login (401/403). Not continuing: "
            f"no accounts or keys are used. Details: {text[:200]}"
        )


# ---------------------------------------------------------
# 1. SEARCH (metadata only - no data is downloaded here)
# ---------------------------------------------------------

def search_files(source_id, experiment, member=None):
    """
    Ask the ESGF search API for the latest pr files of one model/experiment.
    Returns a list of dicts: {title, opendap, host, grid, version, size, member}.
    If `member` is None the search is not restricted to one variant (used to list options).
    """
    params = {
        "project": "CMIP6",
        "source_id": source_id,
        "experiment_id": experiment,
        "variable_id": "pr",
        "table_id": "Amon",
        "type": "File",
        "latest": "true",
        "distrib": "true",
        "limit": 1000,          # high enough that one query is never cut off (200 once hid files)
        "format": "application/solr+json",
    }
    if member:
        params["member_id"] = member
    # Retry the search up to MAX_TRIES times (metadata only, tiny).
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = requests.get(ESGF_SEARCH, params=params, timeout=SEARCH_TIMEOUT_S)
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == MAX_TRIES:
                raise
            time.sleep(2 * attempt)
    docs = response.json()["response"]["docs"]

    files = []
    for doc in docs:
        # Each 'url' entry looks like "<link>|<mime type>|<service name>".
        opendap = None
        for entry in doc.get("url", []):
            link, _, service = entry.split("|")
            if service.upper() == "OPENDAP":   # the API spells it "OPENDAP"
                opendap = link[:-5] if link.endswith(".html") else link
        if opendap:
            files.append({
                "title": doc.get("title"),
                "opendap": opendap,
                "host": opendap.split("/")[2],
                "grid": (doc.get("grid_label") or [""])[0],
                "version": (doc.get("version") or [""])[0] if isinstance(doc.get("version"), list) else doc.get("version", ""),
                "size": (doc.get("size") or 0),
                "member": (doc.get("member_id") or [""])[0],
            })
    return files


def _coverage(files):
    """(first_month, last_month, n_months) parsed from the YYYYMM-YYYYMM in each file name."""
    spans = []
    for f in files:
        match = re.search(r"_(\d{6})-(\d{6})\.nc$", f["title"])
        if match:
            spans.append(match.groups())
    if not spans:
        return None
    spans.sort()
    first, last = spans[0][0], spans[-1][1]
    months = (int(last[:4]) - int(first[:4])) * 12 + int(last[4:]) - int(first[4:]) + 1
    return first, last, months


def pick_files(files):
    """
    Choose one host + grid + version to read.

    A host can hold an INCOMPLETE replica: NCI's FGOALS-g3 historical starts in 1970 while
    CEDA holds the full 1850-2016 set. So we compare the span each host offers and prefer
    the longest one, falling back to HOST_PREFERENCE order only to break a tie.
    Returns (host, files); (None, []) if no allowed host has this member.
    """
    best = None
    for host in HOST_PREFERENCE:
        here = [f for f in files if f["host"] == host]
        if not here:
            continue
        for key in sorted({(f["grid"], f["version"]) for f in here}):
            group = sorted([f for f in here if (f["grid"], f["version"]) == key],
                           key=lambda f: f["title"])
            span = _coverage(group)
            months = span[2] if span else 0
            rank = (months, -HOST_PREFERENCE.index(host))
            if best is None or rank > best[0]:
                best = (rank, host, group)
    if best is None:
        return None, []
    return best[1], best[2]


def find_run_files(run, experiment):
    """
    Work out which files to read for one run + experiment.
    Returns (urls, note). `urls` is empty when the run is unavailable; `note` says why.
    """
    # Known exception: GFDL-ESM4 historical comes from CEDA, not NCI.
    if run["source_id"] == "GFDL-ESM4" and experiment == "historical":
        urls = [CEDA_GFDL_HIST_BASE + name for name in CEDA_GFDL_HIST_FILES]
        return urls, "CEDA (not on NCI)"

    try:
        files = search_files(run["source_id"], experiment, run["member"])
    except requests.RequestException as exc:
        return [], f"search failed: {exc}"

    host, chosen = pick_files(files)
    if chosen:
        note = f"{host} {chosen[0]['grid']} v{chosen[0]['version']}, {len(chosen)} file(s)"
        return [f["opendap"] for f in chosen], note

    # Nothing on NCI for this member: report what exists instead of guessing.
    try:
        others = search_files(run["source_id"], experiment)
    except requests.RequestException:
        others = []
    members = sorted({f["member"] for f in others if f["host"] in HOST_PREFERENCE})
    if members:
        return [], f"member {run['member']} not on NCI/CEDA; they have: {', '.join(members[:8])}"
    hosts = sorted({f["host"] for f in others})
    if hosts:
        return [], f"not on NCI; other hosts list it: {', '.join(hosts)}"
    return [], "no files found"


# ---------------------------------------------------------
# 2. READ ONE GRID CELL OVER OPeNDAP
# ---------------------------------------------------------

def open_remote(url, decode_times):
    """Open a remote file lazily with xarray (imported here so --help works without it)."""
    import xarray as xr
    check_host(url)
    try:
        return xr.open_dataset(
            url, engine="netcdf4", decode_times=decode_times, use_cftime=True if decode_times else None,
            drop_variables=["lat_bnds", "lon_bnds", "time_bnds"], chunks=None,
        )
    except Exception as exc:  # network / server errors
        check_auth_error(exc)
        raise


def nearest_cell(ds, lat0, lon0):
    """
    Find the index of the model grid cell nearest to (lat0, lon0).
    Returns (i_lat, i_lon, lat, lon, distance_km). Handles 0-360 or -180-180 longitude.
    """
    lat = ds["lat"].values
    lon = ds["lon"].values
    if lat.ndim != 1 or lon.ndim != 1:
        raise StopAndAsk("This model uses a 2-D (curvilinear) grid; nearest-cell search not implemented.")
    if lat.size * 8 + lon.size * 8 > MAX_COORD_BYTES:
        raise StopAndAsk("Grid coordinates exceed 1 MB; stopping as instructed.")
    # Put the target longitude on the same convention as the model.
    target_lon = lon0 % 360 if lon.min() >= 0 else ((lon0 + 180) % 360) - 180
    i_lat = int(abs(lat - lat0).argmin())
    # Wrap-safe longitude difference.
    dlon = abs((lon - target_lon + 180) % 360 - 180)
    i_lon = int(dlon.argmin())
    dist = haversine_km(lat0, lon0, float(lat[i_lat]), float(lon[i_lon]))
    return i_lat, i_lon, float(lat[i_lat]), float(lon[i_lon]), dist


def coords_for(url):
    """Open one file (coordinates only) and return the nearest cell for every location."""
    ds = open_remote(url, decode_times=False)
    with ds:
        # Opening loads the lat, lon and time coordinate arrays (8 bytes per value).
        BUDGET.add((ds.sizes["lat"] + ds.sizes["lon"] + ds.sizes["time"]) * 8, url.rsplit("/", 1)[-1])
        lat, lon = ds["lat"].values, ds["lon"].values
        # Median spacing: robust to irregular first points (e.g. FGOALS-g3 starts near the pole).
        import numpy as np
        grid = (lat.size, lon.size, float(np.median(np.abs(np.diff(lat)))), float(np.median(np.abs(np.diff(lon)))))
        return {loc: nearest_cell(ds, *LOCATIONS[loc]) for loc in LOCATIONS}, grid


def report_cells(runs_files):
    """--coords: read ONLY lat/lon (+ time axis) of the first file of each run and report cells."""
    print("\nNearest grid cell per run (coordinates only, no precipitation data read):")
    print(f"{'run':28} {'location':9} {'cell lat':>9} {'cell lon':>9} {'dist km':>8}  grid (nlat x nlon, dlat x dlon deg)")
    cells = {}
    for label, urls in runs_files.items():
        try:
            result, grid = with_retries(lambda u=urls[0]: coords_for(u), label)
        except RemoteFailure as exc:
            print(f"{label:28} SKIPPED: {exc}")
            continue
        for loc, (_, _, clat, clon, dist) in result.items():
            cells[(label, loc)] = (clat, clon)
            print(f"{label:28} {loc:9} {clat:9.2f} {clon:9.2f} {dist:8.0f}  "
                  f"{grid[0]} x {grid[1]}, {grid[2]:.2f} x {grid[3]:.2f}")
    # Do two locations share a cell?
    for label in runs_files:
        if all((label, loc) in cells for loc in LOCATIONS) and len({cells[(label, loc)] for loc in LOCATIONS}) == 1:
            print(f"  note: {label}: all locations fall in the SAME grid cell")


def read_cells(url, locations):
    """
    Open ONE remote file and read the nearest cell for each location.
    Prints the estimated bytes before each read and enforces the per-read and total caps.
    Returns {location: (cell DataArray, cell_lat, cell_lon, distance_km)}.
    """
    name = url.rsplit("/", 1)[-1]
    ds = open_remote(url, decode_times=True)
    with ds:
        BUDGET.add((ds.sizes["lat"] + ds.sizes["lon"] + ds.sizes["time"]) * 8, name)
        out = {}
        for loc in locations:
            i_lat, i_lon, clat, clon, dist = nearest_cell(ds, *LOCATIONS[loc])
            # One cell over time is all that is transferred: time steps x 4 bytes.
            est_bytes = ds.sizes["time"] * BYTES_PER_VALUE
            print(f"    {name} [{loc}]: about to read ~{est_bytes/1024:.1f} kB "
                  f"(run total so far {BUDGET.total/1e6:.2f} MB)")
            if est_bytes > MAX_DOWNLOAD_BYTES:
                raise StopAndAsk(f"Single read ~{est_bytes/1e6:.0f} MB for {url}; ask before continuing.")
            BUDGET.add(est_bytes, name)
            out[loc] = (ds["pr"].isel(lat=i_lat, lon=i_lon).load(), clat, clon, dist)
    return out


def download_run(run, experiment, urls, locations):
    """Read the nearest cell for each location from all files of a run, join in time, save."""
    import xarray as xr

    pieces = {loc: [] for loc in locations}
    cell_info = {}
    for url in urls:
        # Up to 3 tries with a timeout; RemoteFailure means skip this whole run (nothing is saved).
        result = with_retries(lambda u=url: read_cells(u, locations), url.rsplit("/", 1)[-1])
        for loc, (cell, clat, clon, dist) in result.items():
            pieces[loc].append(cell)
            cell_info[loc] = (clat, clon, dist)

    for loc in locations:
        pr = xr.concat(pieces[loc], dim="time").sortby("time")
        clat, clon, dist = cell_info[loc]
        out = pr.to_dataset(name="pr")
        out.attrs.update({
            "source_id": run["source_id"],
            "variant_label": run["member"],
            "experiment_id": experiment,
            "location": loc,
            "requested_lat": LOCATIONS[loc][0],
            "requested_lon": LOCATIONS[loc][1],
            "cell_lat": clat,                       # centre of the model grid cell used
            "cell_lon": clon,
            "distance_to_point_km": round(dist, 1), # distance from the requested point to that centre
            "units_note": "pr in kg m-2 s-1; multiply by 86400 x days in month for mm/month",
            "source_urls": "\n".join(urls),
        })
        path = out_path(run["source_id"], run["member"], experiment, loc)
        path.parent.mkdir(parents=True, exist_ok=True)   # only ever data/climate/
        out.to_netcdf(path)
        t0, t1 = out["time"].values[0], out["time"].values[-1]
        print(f"    saved {path.relative_to(PROJECT_ROOT)} ({path.stat().st_size/1024:.1f} kB on disk), "
              f"{t0.year}-{t0.month:02d} to {t1.year}-{t1.month:02d}, {out.sizes['time']} months")


def download_neighbourhood(run, experiment, urls, location, radius=1):
    """
    Read the (2*radius+1)^2 block of cells centred on the nearest cell, one cell at a time.

    This is only used to show how much the answer depends on WHICH cell is picked; the
    main analysis still uses the single nearest cell. Files go to data/climate/sensitivity/
    and never overwrite the main data.
    """
    import xarray as xr

    pieces = {}
    meta = {}
    for url in urls:
        def read(u=url):
            ds = open_remote(u, decode_times=True)
            with ds:
                BUDGET.add((ds.sizes["lat"] + ds.sizes["lon"] + ds.sizes["time"]) * 8, u)
                i_lat, i_lon, _, _, _ = nearest_cell(ds, *LOCATIONS[location])
                got = {}
                for di in range(-radius, radius + 1):
                    for dj in range(-radius, radius + 1):
                        j_lat = min(max(i_lat + di, 0), ds.sizes["lat"] - 1)
                        j_lon = (i_lon + dj) % ds.sizes["lon"]        # longitude wraps
                        BUDGET.add(ds.sizes["time"] * BYTES_PER_VALUE, u)
                        cell = ds["pr"].isel(lat=j_lat, lon=j_lon).load()
                        key = (di, dj)
                        got[key] = cell
                        meta[key] = (float(ds["lat"].values[j_lat]), float(ds["lon"].values[j_lon]))
                return got
        block = with_retries(read, url.rsplit("/", 1)[-1])
        for key, cell in block.items():
            pieces.setdefault(key, []).append(cell)

    SENSITIVITY_DIR.mkdir(parents=True, exist_ok=True)
    for (di, dj), parts in pieces.items():
        series = xr.concat(parts, dim="time").sortby("time")
        clat, clon = meta[(di, dj)]
        out = series.to_dataset(name="pr")
        out.attrs.update({
            "source_id": run["source_id"], "variant_label": run["member"],
            "experiment_id": experiment, "location": location,
            "cell_lat": clat, "cell_lon": clon,
            "offset_lat": di, "offset_lon": dj,
            "distance_to_point_km": round(haversine_km(*LOCATIONS[location], clat, clon), 1),
            "source_urls": "\n".join(urls),
        })
        name = (f"pr_{run['source_id']}_{run['member']}_{experiment}_"
                f"{safe_name(location)}_d{di:+d}{dj:+d}.nc")
        path = SENSITIVITY_DIR / name
        out.to_netcdf(path)
        print(f"    saved sensitivity/{name} ({path.stat().st_size/1024:.1f} kB)")


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="*", help="only these slide labels (default: all)")
    parser.add_argument("--locations", nargs="*", default=list(LOCATIONS), choices=list(LOCATIONS))
    parser.add_argument("--coords", action="store_true", help="read grid coordinates only and report nearest cells")
    parser.add_argument("--download", action="store_true", help="download and save the cell time series")
    parser.add_argument("--dry-run", action="store_true", help="search only (this is already the default)")
    parser.add_argument("--sensitivity", action="store_true",
                        help="read the 3x3 block of cells around the point into data/climate/sensitivity/")
    args = parser.parse_args()

    runs = [r for r in MODEL_RUNS if not args.models or r["label"] in args.models]

    # --- search every run/experiment (metadata only) ---
    found = {}      # (label, experiment) -> urls
    missing = []    # (label, experiment, reason)
    print("Searching ESGF (metadata only)...")
    for run in runs:
        for exp in EXPERIMENTS:
            urls, note = find_run_files(run, exp)
            tag = f"{len(urls)} file(s)" if urls else "MISSING"
            print(f"  {run['label']:28} {exp:10} {tag:10} {note}")
            if urls:
                found[(run["label"], exp)] = urls
            else:
                missing.append((run["label"], exp, note))

    # --- optional: nearest-cell report ---
    if args.coords:
        first_urls = {label: urls for (label, exp), urls in found.items() if exp == "historical"}
        report_cells(first_urls)

    # --- optional: download ---
    if args.download:
        print("\nDownloading nearest-cell time series...")
        for run in runs:
            for exp in EXPERIMENTS:
                urls = found.get((run["label"], exp))
                if not urls:
                    continue
                todo = [loc for loc in args.locations
                        if not out_path(run["source_id"], run["member"], exp, loc).exists()]
                if not todo:
                    print(f"  {run['label']} {exp}: all files exist, skipped")
                    continue
                print(f"  {run['label']} {exp}: fetching for {', '.join(todo)}")
                try:
                    download_run(run, exp, urls, todo)
                except StopAndAsk:
                    raise
                except Exception as exc:
                    print(f"    SKIPPED {run['label']} {exp} (continuing with next run): {str(exc)[:150]}")
                    missing.append((run["label"], exp, f"download failed: {str(exc)[:80]}"))

    # --- optional: 3x3 neighbourhood (sensitivity test only) ---
    if args.sensitivity:
        print("\nReading the 3x3 cell block around each location (sensitivity test)...")
        for run in runs:
            for exp in EXPERIMENTS:
                urls = found.get((run["label"], exp))
                if not urls:
                    continue
                for loc in args.locations:
                    print(f"  {run['label']} {exp} {loc}")
                    try:
                        download_neighbourhood(run, exp, urls, loc)
                    except StopAndAsk:
                        raise
                    except Exception as exc:
                        print(f"    SKIPPED: {str(exc)[:150]}")

    # --- final report ---
    print("\nSummary")
    print(f"  data transferred this run: {BUDGET.total/1e6:.2f} MB (cap {MAX_TOTAL_BYTES/1e6:.0f} MB)")
    print(f"  runs with both experiments found: "
          f"{sum(1 for r in runs if (r['label'],'historical') in found and (r['label'],'ssp245') in found)}/{len(runs)}")
    if missing:
        print("  missing / unavailable:")
        for label, exp, note in missing:
            print(f"    {label} [{exp}]: {note}")
    print("  not matched (slide rows marked 'coupled', meaning unknown, not guessed):")
    for name in UNMATCHED_COUPLED:
        print(f"    {name}")


if __name__ == "__main__":
    try:
        main()
    except StopAndAsk as stop:
        print(f"\nSTOPPED - needs your decision: {stop}")
        sys.exit(2)
