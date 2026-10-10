# HIT401 Group 34 — Data Explorer

**What it is**: a single-page web app (FastAPI + Leaflet + Plotly.js, no build step) for
exploring every dataset in this repository: all NT bores, water-quality samples,
water-level series, river/stream gauges, BOM rainfall stations, the Ti Tree aquifer
layers, and the CMIP6 climate projections from `climate/`. It's a separate thing from
the Streamlit dashboards in `krishna-code/` and `dylan-code/` — different stack, NT-wide
rather than Ti Tree-only — and doesn't touch or depend on either of them.

Lives entirely under `webapp/`; nothing outside this folder was changed to build it.

## Setup

One-off, in a new virtual environment (already created and populated for this build —
see "What's installed" below if setting up fresh):

```bash
python3 -m venv ~/venvs/hit401_web
~/venvs/hit401_web/bin/pip install -r webapp/requirements.txt
```

Packages included: `fastapi`, `uvicorn`, `pandas`, `numpy`, `geopandas`, `pyogrio`, `shapely`, `pyarrow`, `xarray`, `netCDF4`, `httpx`, and `plotly` (used by `climate_models.py` for server-side figure generation where appropriate).

## Build the cache (run once, and again after any raw data file changes or portal URL updates)

```bash
python webapp/build_cache.py
```

Takes about 5–15 seconds. Reads, read-only:
- `Datasets/NT-NaturalResourceMapsBoreData/Bores.csv`
- `krishna-code/data.zip` (extracted once into `webapp/cache/_extracted/`, a copy —
  the original zip is never modified)
- `Datasets/GroundwaterHeads_20250718/` (bore water-level exports)
- `Datasets/BOM-Datasets/` (11 rainfall stations)
- `Datasets/StreamflowData/` (gauge G0280010)
- `climate/climate_models.py`, imported for its rainfall/flow aggregation logic

Writes compact Parquet/JSON/GeoJSON files to `webapp/cache/` only. Normalises legacy
NT Water Data Portal domains (`water.nt.gov.au` -> `ntg.aquaticinformatics.net`).
Prints a short summary and writes `webapp/cache/build_report.json` with every repair,
conflict and warning found along the way.

## Run

```bash
python webapp/server.py
```

Then open **http://127.0.0.1:8000**. Add `--port 8080` or `--host 0.0.0.0` if needed.

## Test

```bash
python webapp/tests/test_build_cache.py   # 16 tests, tests ID normalisation & portal URL migration
python webapp/tests/test_api.py           # 35 tests, needs the cache built
```

Both run as plain scripts (same convention as `climate/tests/`) — no pytest installed
or required, though `pytest webapp/tests/` also works if you have it.

Manual check with curl, against the running server:

```bash
curl -s http://127.0.0.1:8000/api/meta | python3 -m json.tool
curl -s "http://127.0.0.1:8000/api/location/bore/RN006543" | python3 -m json.tool
curl -s "http://127.0.0.1:8000/api/place?lat=-10&lon=110" | python3 -m json.tool
```

## What's where

```
webapp/
  build_cache.py        preprocessing: raw files -> webapp/cache/
  server.py              FastAPI app: serves the page + the JSON API
  static/
    index.html, app.js, styles.css
    vendor/              Leaflet 1.9.4, Leaflet.markercluster 1.5.3, Plotly.js 2.35.2
                          (downloaded once from unpkg.com / cdn.plot.ly, served locally
                          so the page works offline except for map tiles)
  cache/                 generated — Parquet, JSON, GeoJSON, and a read-only extracted
                          copy of krishna-code/data.zip. Rebuilt by build_cache.py.
  tests/
    test_build_cache.py  ID normalisation, the Bores.csv repair, shared constants
    test_api.py          every API endpoint (32 tests), against the real built cache
  README.md              this file
```

## The page

- **Executive KPI Summary Banner**: Displays key basin-wide performance indicators at the top
  of the dashboard (reimplemented from `krishna-code/app(v1.2).py`):
  - **Total Study Bores** (415 in Ti Tree basin, 43,099 NT-wide)
  - **Quality Monitored Bores** (272 in basin with historical chemical assays, 16,929 NT-wide)
  - **Water Quality Samples** (1,185 basin chemical assays, 84,769 NT-wide)
  - **Monitoring Bores** (126 in basin, 36 currently active; 2,274 NT-wide)
  Includes a smooth toggle button to collapse/expand the banner for maximum map workspace.
- **Quick Bore Search**: Dedicated sidebar control (reimplemented from `krishna-code/app(v1.2).py`)
  featuring a sorted dropdown (`Search bore by ID:`) of Ti Tree study basin bores plus a quick
  jump input with automatic ID normalisation (e.g. `6543` -> `RN006543`), automatically centering
  the map and opening the detail drawer.
- **Statistical Summary Cards**: 4-metric statistics cards (reimplemented from `krishna-code/app(v1.2).py`)
  calculating and displaying **Minimum**, **Maximum**, **Mean**, and **Median** (formatted to 2 decimal
  places with observation counts) for valid numerical observations in the Water Quality and Water
  Level time-series tabs, gracefully handling non-numeric or missing data.
- **Map**: every NT bore, river/stream gauge and BOM rainfall station on one map, with
  3 base layers (OpenTopoMap, Esri satellite, OpenStreetMap) and the 5 Ti Tree aquifer
  overlays (salinity, aquifer thickness, depth to groundwater, contours, boundary) as
  toggleable layers. Clustered for the full 43,000+ bore list; filters and a "colour
  bores by" control (status, purpose, has water level/quality, yield, water level, or
  any of the 18 chemical parameters against a threshold you set) live in the left panel.
- **Click any marker** to open the right-hand drawer with up to 8 tabs: Overview, Water
  level, Water quality, Rainfall, River flow, Nearby, Data quality, Aquifer context.
  A tab with nothing for that site says so plainly and points at the nearest
  alternative rather than staying blank.
- **Click anywhere else on the map** for a place summary: nearest bore, rainfall
  station and gauge, with distances, and whether the point falls inside the Ti Tree
  basin.
- **Search** by bore ID or name, gauge ID or name, or BOM station name/number. There is
  no town or state search — none of the source files carry that field, and nothing is
  invented to fill the gap; the search box says so when nothing matches.
- **Compare tray**: add up to 5 bores from their drawer, then overlay any chemical
  parameter or the water-level series for all of them on one chart.
- **Climate view** (top-bar switch): the Darwin/Ti Tree CMIP6 anomaly-bar and
  wetter-or-drier charts from `climate/climate_models.py`, the rainfall and river-
  flow residual-mass charts, plus the **seasonal recharge charts** (observed gauge totals
  vs CMIP6 model projections out to 2099), **rainfall, flow, and bore water-level time series**
  (three-panel stacked comparison from 2010 onwards), and **lag correlation charts**
  (evaluating how long after rainfall or flow the water table moves) — all computed live
  from that module.
- **Every chart**: downloads as PNG (the chart's own toolbar or the button underneath)
  or as the exact CSV used to draw it.
- **Shareable link**: the URL updates with the selected site, its open tab, and which
  view (map/climate) is showing, via `?loc=bore:RN006543&tab=waterquality`.
- **Dark mode** toggle, top right. **About** panel: data sources, licence/limitations
  text, and the full CMIP6 citations file.

## Known gaps / planned work

- **No automatic data download.** `build_cache.py` is a human-triggered preprocessing
  step; nothing in this app downloads or refreshes source data on its own.
  `climate/download_cmip6_pr.py` exists as a separate manual script for the CMIP6 data
  specifically, also not wired into any UI.
- **CSV download for the compare tray is planned, not built.** Every single-location
  chart has a CSV download already; the multi-bore compare overlay (`openCompareView`
  in `app.js`) does not yet.
- **The NT Water Data Portal link may point to the old domain for some bores.** This
  app renders whatever URL is in the source shapefile's `WATER_DATA` field as-is
  (`water_data_portal` / `water_data_portal_shp` / `monitor_portal_url` in
  `build_cache.py` and `server.py`); some of those stored URLs use the old
  `water.nt.gov.au` domain instead of `ntg.aquaticinformatics.net`. Not rewritten here.

## Data findings (see `webapp/cache/build_report.json` for the complete, generated list)

- **`Bores.csv` has 10 malformed rows**, not just the one at line 930 that
  `Datasets/DataSources.txt` already flags — a literal `"` inside a bore name (meant as
  an inch mark, e.g. `6"CAS`) breaks CSV quoting in three different ways across the
  file. All 10 were reconstructed (not dropped); see `bores_csv_repairs` in the report
  for the exact before/after on each one.
- **The bore shapefile has 43,232 records but only 43,109 unique bore numbers** — 63
  bores are duplicated (kept the first occurrence of each), and of those 63 duplicate
  groups, **13 have genuinely different `WATERLEVEL` or `RISK_CLASS` values** between
  the copies — a real conflict, not just a harmless repeat.
- **The groundwater-monitoring shapefile mixes bores and river gauges**: of its 2,405
  stations, 131 are `G0xxxxxx` gauge codes, not bores. These are now their own location
  type (River/stream gauge) rather than silently shown as bores.
- **48 bores are listed as having a water-level series; only 16 actually have an
  exported file** in this project's data. Every one of those 16 is checked individually
  for which kind (Water Elevation / Depth Below Ground) and which series (dense
  "Publish" telemetry vs sparse "Field Visits") it actually has — 4 of the 16 have only
  the sparse manual series, never a dense one.
- **`RN006543` has two duplicate export folders.** `climate_models.py`'s own
  `bore_catalogue()` keeps the first (older) one; this build deliberately keeps the
  newer one instead, and says so on that bore's Data quality tab.
- **Water quality is genuinely NT-wide**: 84,769 samples across 16,929 bores, 1909–2021
  — all of it matches `Bores.csv` by normalised ID (100%).
- **9 of the 11 BOM stations on file are not in the Northern Territory** (Perth,
  Adelaide, Sydney, Melbourne, Hobart, Brisbane, and three regional Queensland/WA
  stations) — kept for comparison, hidden on the map by default, and excluded from
  "nearest rainfall station" results.
- **56% of all readings at gauge G0280010 are quality code 210** ("not of release
  quality or contains missing data") — shown as a banner on that gauge's data-quality
  tab and a chart badge, not smoothed over.
- `bom_stations.csv` and `locations_index.csv` at the repo root are both stale relative
  to what's actually on disk (the first omits station 015643, the only one near Ti Tree;
  the second lists 3 rows against 17 real export folders) — this build derives its own
  indices from the source files instead of trusting either.
- **NT Water Data Portal domain migration (`water.nt.gov.au` -> `ntg.aquaticinformatics.net`)**:
  Raw groundwater-monitoring layer shapefiles (`Bores_groundwater_level.shp`) contained legacy links
  using `http(s)://water.nt.gov.au/...`, which the NT Government decommissioned and redirects to a
  generic disclaimer losing the specific bore or gauge ID. The application converts these links to
  `https://ntg.aquaticinformatics.net/...` at both cache build time (`build_cache.py`), server
  startup (`server.py`), and client side (`app.js`), preserving the `/Data/Location/...` path, query
  parameters, and identifiers, while leaving valid unrelated external links (such as `ntlis.nt.gov.au`
  bore reports) and records with no portal link untouched. Rebuilding the cache (`python webapp/build_cache.py`)
  persists these cleaned URLs directly into the on-disk parquet files.

## Design notes

- **Plotly integration & dual representation.** `climate_models.py`'s `plot_anomaly_bars()`,
  `plot_wetter_or_drier()`, `plot_seasonal()`, `plot_lag_correlation()`, and
  `plot_rain_flow_bores()` build `plotly.graph_objects.Figure` objects. The backend
  climate endpoints in `server.py` (`/api/climate/anomaly`, `/api/climate/wetter-drier`,
  `/api/climate/seasonal`, `/api/climate/lag`, `/api/climate/rain-flow-bores`) return
  both structured data arrays (for CSV exports and responsive table rendering) as well
  as serialised Plotly figure structures, allowing the browser's vendored Plotly.js to
  draw interactive charts with full theme support (light and dark mode).

- **No LTTB downsampling was needed.** Every series actually shown is already small:
  water quality averages ~5 samples per bore, and rainfall/flow/water-level are all
  aggregated to **monthly** means before being sent to the browser (reusing
  `climate_models`'s own monthly-aggregation functions) — at most a few hundred points.
  Full-resolution raw data (daily rainfall, sub-daily flow, raw bore readings) is cached
  separately and only read for a CSV download, never for the on-screen chart.
  `/api/locations` (43,000+ markers) is the one genuinely large payload; its JSON and
  gzip bytes are built once at server startup and served as-is, cutting that request
  from ~0.8s to ~14ms (see "Performance" below).
- **Nearest-neighbour is a live, vectorised haversine**, not a precomputed table. With
  at most ~43,000 bores, 131 gauges and 11 stations, a numpy distance calculation
  against the full array for one query point is sub-millisecond — faster than building
  and maintaining a spatial index would have been, and it works for *any* clicked point
  on the map, not just the one gauge `bore_gauge_distances_G0280010.csv` was
  precomputed for.
- **Monitoring locations are a bore attribute, not a fourth marker type.** All 2,274
  "monitoring" stations in the shapefile (after removing the 131 gauges) turned out to
  already be bores in `Bores.csv` — so the old app's separate "Groundwater-monitoring
  locations" mode becomes a checkbox filter and a flag on the bore it already is.

## Performance (measured on this machine, 2026-10-08)

| Step | Time |
|---|---|
| `build_cache.py`, full run (cold, including the one-off zip extraction) | 14.6s |
| `build_cache.py`, full run (warm, zip already extracted) | 5.6s |
| Server startup: load all caches into memory | 0.26–0.42s |
| Server startup: build the `/api/locations` payload (JSON + gzip, once) | 0.6s |
| **Server startup, total, process launch to first successful request** | **1.6s** (target: <5s) |
| `GET /api/locations` (43k+ markers, gzip), after the above | **14ms** (was ~775ms before precomputing it) |
| `GET /api/locations`, uncompressed | 0.43s |
| `GET /api/location/bore/{id}` (full drawer detail) | ~26ms |
| `GET /api/water-quality/{id}?parameter=X` | ~3ms |
| **Click-to-first-chart, server round trip** (detail + one series) | **~29ms** (target: <400ms) |

**What this table does *not* measure**: actual time-to-first-paint in a browser (Leaflet
init, vendor script parsing, clustering 43,000+ markers client-side) and the Plotly chart
draw time after the data arrives. No headless browser was available in this environment
to drive a real page load and report console errors, so these numbers are the server
side of the budget only. See "Manual testing" below for exactly what to click to check
the rest by eye.

## Manual testing (do this once, in a real browser)

1. Open http://127.0.0.1:8000 — the map should appear with bore markers clustering at
   country scale within ~1–2 seconds.
2. Zoom into the Ti Tree area (around -22.3, 133.4) — clusters should break apart into
   individual pins as you zoom in.
3. Click a bore pin — the drawer should open on the right within well under a second,
   on the Overview tab.
4. Click through the other tabs on a bore that has data (search "RN006543") — Water
   level and Water quality should each draw a chart.
5. Click a bore with no tick marks on its checklist (e.g. search any "RN0030xx" bore) —
   every data tab should say plainly that nothing is there, never show a blank chart.
6. Click empty water, e.g. in the Timor Sea north of Darwin — a place-summary box should
   appear bottom-left with "far" warnings on the nearest rainfall station.
7. Toggle "Colour bores by" to a chemical parameter, move the threshold slider — marker
   colours should update live.
8. Add 2–3 bores to the compare tray from their drawers, click "Compare selected" — an
   overlay chart should appear.
9. Switch to the Climate tab, change location/model run — both charts should redraw.
10. Toggle dark mode — the whole page, including the drawer and charts, should restyle.
11. Open the browser's developer console throughout steps 1–10 and confirm there are no
    red errors — this was not checked automatically in this environment (see above).

## Limitations (also shown in the page's own About panel)

See the About panel in the app for the full, current list — it's generated from
`/api/about`, which reads `docs/climate/CITATIONS_CMIP6.md` and `climate_data_notes.md`
directly, so it can't drift out of sync with this README.
