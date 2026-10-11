# HIT401 Group 34 Capstone Project
## Interactive Groundwater & Climate Explorer for the Northern Territory

**Supervisor:** Dr Cat Kutay (Charles Darwin University)  
**Hydrogeology Adviser:** Assoc. Prof. Dylan Irvine (Charles Darwin University)  

**Group 34 Team:**
- Krishna Dhakal (S396451)
- Gaurab Gaihre (S387897)
- Dylan Kennedy (S343881)
- Sachin Kharel (S399310)

---

## 1. Overview & Final Web Application

The primary output of this project is the **final web application** located in **`webapp/`**. It is a unified, single-page data explorer and climate analysis dashboard built with **FastAPI** (Python backend), **Leaflet** (spatial GIS mapping with clustering), and **Plotly.js** (interactive client-side charting).

The application addresses the client's core project goals, specifically **Cat's Aim 1** (exploring NT-wide bore metadata, groundwater levels, water quality, streamflow, and aquifer geometries) and **Cat's Aim 2** (analysing seasonal recharge patterns, rainfall-streamflow-bore time series, and lag correlations using CMIP6 climate model projections).

> **Distinction from Legacy Dashboards**: Earlier exploratory work in `krishna-code/` and `dylan-code/` produced standalone Streamlit prototypes. Key analytical features from those prototypes (KPI summary banner, quick bore search, statistics cards, Ti Tree GIS layers) have been reimplemented into the final web application under `webapp/`. The Streamlit scripts remain in the repository for historical provenance, but `webapp/` is the official, complete final platform.

---

## 2. Environment Setup & Installation

The project runs on **Python 3.11+ / 3.12**. It is recommended to use a virtual environment:

```bash
# 1. Create a virtual environment
python -m venv .venv

# 2. Activate the virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (Command Prompt):
.venv\Scripts\activate.bat
# On macOS / Linux:
source .venv/bin/activate

# 3. Install required packages
pip install -r webapp/requirements.txt
```

### Core Dependencies:
- **Backend API & Web Framework:** `fastapi`, `uvicorn`, `httpx`
- **Data Processing & Geospatial:** `pandas`, `numpy`, `geopandas`, `pyogrio`, `shapely`, `pyarrow`
- **Climate Modelling & NetCDF:** `xarray`, `netCDF4`, `scipy`
- **Visualisation & Plotting:** `plotly`, `matplotlib` (used for server-side figure serialisation)
- **Frontend Assets:** Vendored locally in `webapp/static/vendor/` (`Leaflet 1.9.4`, `Leaflet.markercluster 1.5.3`, `Plotly.js 2.35.2`) so the application functions offline without external CDN dependencies.

---

## 3. Building the Data Cache

Before launching the server for the first time (or after any source dataset changes), run the cache-building pipeline:

```bash
python webapp/build_cache.py
```

### What `build_cache.py` Does:
1. **Reads Raw Data (Read-Only)**:
   - NT Bore Register (`Datasets/NT-NaturalResourceMapsBoreData/Bores.csv`)
   - Krishna's geospatial shapefiles (`krishna-code/data.zip` extracted once as a read-only copy into `webapp/cache/_extracted/`)
   - Groundwater Head exports (`Datasets/GroundwaterHeads_20250718/`)
   - BOM daily rainfall series (`Datasets/BOM-Datasets/`)
   - River discharge series (`Datasets/StreamflowData/`)
   - Ti Tree aquifer GIS layers (boundary, salinity, thickness, depth to water, contours)
2. **Performs Ingestion Cleaning & Normalisation**:
   - Repairs 10 malformed lines in `Bores.csv` with unescaped quotation marks (e.g. `6"CAS`) without dropping records.
   - Upgrades legacy NT Water Data Portal URLs from `water.nt.gov.au` to `ntg.aquaticinformatics.net`, preserving paths and query parameters.
   - De-duplicates bore and monitoring layer records with consistent ID formatting (`RN006543`).
   - Pre-aggregates daily rainfall, streamflow, and bore readings to monthly means for fast chart delivery.
3. **Writes Optimised Formats**:
   - Generates compact Parquet, JSON, and GeoJSON files in `webapp/cache/`.
   - Generates `webapp/cache/build_report.json` auditing every defect, conflict, and timing benchmark.
   - Pipeline completes in ~5–15 seconds.

---

## 4. Running the Web Application

Start the local FastAPI development server:

```bash
python webapp/server.py
```

Open your browser and navigate to:
**http://127.0.0.1:8000**

*(Optional flags: `--port 8080`, `--host 0.0.0.0`)*

### Key Features in the Final Web App:
- **Executive KPI Summary Banner:** Displays study bore counts (415 Ti Tree basin, 43,099 NT-wide), water-quality monitored bores (272 basin, 16,929 NT-wide), chemical sample counts (1,185 basin, 84,769 NT-wide), and monitoring bores with live active status.
- **Quick Bore Search:** Direct dropdown selector for Ti Tree study bores and quick jump box supporting shorthand IDs (e.g. typing `6543` auto-resolves to `RN006543`, pans the map, and opens the detail drawer).
- **Interactive Spatial Map:** Leaflet map with multi-scale clustering, marker styling by purpose/status/chemical thresholds, and Ti Tree aquifer GIS layer overlays (salinity, depth, thickness, contours).
- **Bore Detail Drawer & Statistics Cards:** Summary metrics (Min, Max, Mean, Median) for water quality and water level series, verified checklist of available datasets, and external link to NT Water Data Portal.
- **Multi-Bore Comparison Tray:** Compare up to 5 bores side-by-side with overlay charts for any water quality parameter or water level elevation, featuring dedicated **"Download data (CSV)"** export buttons.
- **Integrated Climate View:**
  - *Seasonal Recharge (Observed vs Modelled):* Wet season (Nov–Apr) and dry season (May–Oct) rainfall totals per year for Territory Grape Farm (015643) against 5 CMIP6 model projections out to 2099.
  - *Rainfall, River Flow, and Bore Levels:* 3-panel comparative time-series (rainfall residual mass, Woodforde River flow residual mass, and monitoring bore levels).
  - *Lag Correlation Matrix:* Time-lagged Pearson correlations (0–12 months) examining recharge delays between climate drivers and aquifer head changes.
  - *CMIP6 Precipitation Projections & Anomalies:* Reference period 1995–2014 baseline anomaly bars and wetter/drier classification summaries.

---

## 5. Running Automated Tests

The application contains comprehensive automated unit and integration test suites:

```bash
# 1. Test preprocessing, ID normalisation, CSV repair, and URL migration (16 tests)
python webapp/tests/test_build_cache.py

# 2. Test API endpoints, data payloads, stats cards, and climate models (35 tests)
python webapp/tests/test_api.py
```

*(You can also run both test suites with pytest: `pytest webapp/tests/`)*

Both test suites execute without external network calls and report `0 failure(s)`.

---

## 6. Repository Structure

```
HIT401-Group34-Capstone-Project/
├── webapp/                    # FINAL APPLICATION (FastAPI + Leaflet + Plotly.js)
│   ├── server.py              # Application server and REST API endpoints
│   ├── build_cache.py         # Data preprocessing and cache builder
│   ├── requirements.txt       # Web application Python dependencies
│   ├── README.md              # Detailed technical documentation for webapp
│   ├── static/                # Frontend user interface (HTML, CSS, JS, vendor scripts)
│   │   ├── index.html         # Single-page UI layout
│   │   ├── app.js             # Client state management, map logic, charts, CSV exports
│   │   ├── styles.css         # Responsive styling with dark mode support
│   │   └── vendor/            # Offline vendor libraries (Leaflet, Plotly, MarkerCluster)
│   ├── cache/                 # Preprocessed Parquet/JSON/GeoJSON files (generated)
│   └── tests/                 # Automated test suite (test_api.py, test_build_cache.py)
│
├── climate/                   # CLIMATE MODELLING & HYDROLOGY FUNCTIONS
│   ├── climate_models.py      # Core module: CMIP6 downscaling, recharge & lag functions
│   ├── download_cmip6_pr.py   # Downloader script for CMIP6 precipitation NetCDF files
│   ├── CMIP6/                 # Gridded NetCDF precipitation model runs
│   └── tests/                 # Unit tests for climate modelling routines
│
├── Datasets/                  # RAW INPUT DATASETS
│   ├── NT-NaturalResourceMapsBoreData/ # Bores.csv (43,099 bore records)
│   ├── GroundwaterHeads_20250718/      # Bore water level series (16 bores, 60 CSV exports)
│   ├── BOM-Datasets/                   # 11 BOM weather stations (daily rainfall & notes)
│   ├── StreamflowData/                 # River discharge data for gauge G0280010
│   └── DataSources.txt                 # Detailed data provenance and station coverage notes
│
├── krishna-code/              # LEGACY PROTOTYPE (Krishna Dhakal)
│   ├── app(v1.2).py           # Streamlit GIS dashboard prototype
│   ├── requirements.txt       # Streamlit prototype dependencies
│   └── data.zip               # GIS shapefiles (read by webapp/build_cache.py)
│
├── dylan-code/                # LEGACY PROTOTYPE (Dylan Kennedy)
│   ├── Updated_Dashboard_Prototype.py # Streamlit bore plotting prototype
│   └── requirements.txt       # Streamlit prototype dependencies
│
├── AppendixC_Code/            # INTERIM REPORT APPENDIX C CODE
│   ├── gwrc_ingest.py         # Groundwater head ingestion and data-quality audit
│   ├── gwrc_trends.py         # Linear trends and Mann-Kendall robustness checks
│   ├── toolkit_demo.py        # Groundwater analysis toolkit validation
│   └── README.md              # Appendix C execution and methodology notes
│
└── docs/                      # PROJECT DOCUMENTATION
    └── climate/               # CMIP6 citations, data logs, and research notes
```

---

## 7. Data Provenance & Key Findings

For complete data provenance and coverage details, refer to `Datasets/DataSources.txt`. Key findings include:

1. **BOM Rainfall Coverage:** Contains 11 Australian stations, including **015643 Territory Grape Farm** (within the Ti Tree Basin study area, ~42 km away) and **014050 Fort Hill Wharf** (Darwin Harbour), plus 9 interstate reference stations for continental comparison.
2. **Groundwater Head Records:** 16 unique monitoring bores in the Ti Tree Basin contain high-frequency logger or manual dip series in `Datasets/GroundwaterHeads_20250718/`.
3. **Water Quality Records:** 84,769 chemical assay samples across 16,929 bores NT-wide (1909–2021) in `krishna-code/data.zip` (`Bores_water_quality.shp`).
4. **Streamflow Discharge Quality:** 56% of historical daily readings at gauge G0280010 (Woodforde River at Arden Soak) carry BOM/NT quality code 210 ("not of release quality or contains missing data") — highlighted in the web app rather than smoothed over.
5. **NT Water Data Portal Migration:** Decommissioned URLs pointing to `water.nt.gov.au` are automatically converted to `https://ntg.aquaticinformatics.net` across all endpoints and export buttons.

---

## 8. Limitations

- **No Automatic External Data Ingestion:** Data caching via `python webapp/build_cache.py` is a manual preprocessing step; the web app does not pull real-time telemetry over the internet.
- **Water-Level Series Coverage:** Of the 48 bores listed in `Bores_w_wl_data.csv`, only 16 have raw time-series export files on disk. Bores lacking exported series are clearly flagged with an empty-state checklist in the UI.
- **Pumping & Commercial Abstraction:** Commercial extraction records are held under private regulatory licenses and are not included in the repository.
- **Linear Trend Assumptions:** Trend lines in Appendix C are fitted as linear; sudden regime shifts (e.g. new extraction licenses) require contextual interpretation.