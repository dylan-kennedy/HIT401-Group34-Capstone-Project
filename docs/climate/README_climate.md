# Climate modelling — HIT401 Group 34

Water-year rainfall from CMIP6 climate models for Darwin and Ti Tree, plus residual mass
curves for the observed rain gauge, the river gauge and nearby bores.

The charts reproduce the style of slides 28–31 of "The wet season that was" by
A/Prof Dylan Irvine (Charles Darwin University). All numbers are computed from data this
project downloaded; our figures are not expected to match his exactly, and nothing was
tuned to make them agree.

**None of this touches the main dashboard.** `krishna-code/app(v1.2).py`, everything in
`Datasets/` and `krishna-code/requirements.txt` are unchanged. The climate section is a separate module
that can be dropped into the app later as a tab.

---

## 0. Where things live

```
climate/                 code: the downloader, the analysis module, the demo app
climate/requirements.txt packages the climate module needs
climate/tests/           tests and the data-quality check
docs/climate/            this README, the AI log, the citations, the data source notes
data/climate/            downloaded single-cell NetCDF files
```

Paths inside the code are worked out from each file's own location, so the commands below
work from the repository root and the tests also run from inside their own folder.

## 1. Set up

A virtual environment outside the repo is used, so nothing here changes the dashboard's own
`krishna-code/requirements.txt`:

```bash
python3 -m venv ~/venvs/hit401_climate
~/venvs/hit401_climate/bin/python -m pip install -r climate/requirements.txt
```

Every command below uses that interpreter. `-B` just stops Python writing `__pycache__`
into the repo.

| Package | Why |
|---|---|
| `xarray`, `netCDF4` | read CMIP6 NetCDF over OPeNDAP and save the single-cell files |
| `requests` | query the ESGF search API |
| `plotly` | all charts |
| `streamlit` | the preview app |
| `pandas`, `numpy` | everything else |

`pytest` is **not** required; the test files run on their own.

---

## 2. What each file does

| File | Purpose |
|---|---|
| `climate/download_cmip6_pr.py` | Finds CMIP6 monthly rainfall on ESGF and saves the single nearest grid cell per location. |
| `climate/climate_models.py` | All the analysis and charts, plus `render_climate_tab()` for Streamlit. Importable and runnable. |
| `climate/streamlit_climate_demo.py` | Standalone preview page; one call to `render_climate_tab()`. |
| `climate/tests/test_climate_models.py` | 11 tests: water years, units, moving mean, percent change. |
| `climate/tests/test_residual_mass.py` | 12 tests: the gap rule, calendar-month averages, flow volumes. |
| `climate/tests/test_observed_analysis.py` | 11 tests: the water-year exclusion rule, lag alignment, level change, seasons. |
| `climate/tests/check_downloaded_data.py` | Quality report on the downloaded files (not a unit test). |
| `docs/climate/CITATIONS_CMIP6.md` | Model list, institutions, licences and DOIs. Read this before publishing. |
| `docs/climate/AI_LOG.md` | AI declaration record. |
| `docs/climate/climate_data_notes.md` | Background research notes on the data sources (see the AI log for how they were produced). |
| `climate/requirements.txt` | Packages the climate module needs. |

Data and output locations:

| Path | Contents |
|---|---|
| `data/climate/` | 44 single-cell NetCDF files, about 35 kB each |
| `data/climate/sensitivity/` | 18 files from the CMCC-ESM2 3×3 cell test |
| `outputs/climate_preview/` | Preview charts as standalone HTML |

---

## 3. Downloading the model data

The downloader does nothing but search unless you ask it to read data.

```bash
# 1. Search only. No data is transferred. Shows which runs are available where.
~/venvs/hit401_climate/bin/python -B climate/download_cmip6_pr.py --dry-run

# 2. Report the nearest grid cell per model (reads coordinates only, about 0.14 MB).
~/venvs/hit401_climate/bin/python -B climate/download_cmip6_pr.py --coords

# 3. Download the single-cell series. Files that already exist are skipped.
~/venvs/hit401_climate/bin/python -B climate/download_cmip6_pr.py --download

# One model, one location
~/venvs/hit401_climate/bin/python -B climate/download_cmip6_pr.py --download --models "GFDL-ESM4" --locations Darwin

# The 3x3 neighbourhood test (writes to data/climate/sensitivity/)
~/venvs/hit401_climate/bin/python -B climate/download_cmip6_pr.py --sensitivity --models "CMCC-ESM2" --locations Darwin
```

A full download transfers about 2 MB and takes a few minutes, because OPeNDAP sends only
the one grid cell we ask for rather than the whole global file.

**Safety built in:** reads only from `esgf.nci.org.au` and `esgf.ceda.ac.uk`; stops above
100 MB in one read or 500 MB in a run; three retries with timeouts; stops if any server
asks for a login; writes only into `data/climate/`.

---

## 4. Running the tests

```bash
~/venvs/hit401_climate/bin/python -B climate/tests/test_climate_models.py
~/venvs/hit401_climate/bin/python -B climate/tests/test_residual_mass.py
~/venvs/hit401_climate/bin/python -B climate/tests/test_observed_analysis.py

# data quality report on what was downloaded
~/venvs/hit401_climate/bin/python -B climate/tests/check_downloaded_data.py
```

34 tests, all passing as of 7 October 2026. None needs the network.

---

## 5. The preview app

```bash
~/venvs/hit401_climate/bin/python -m streamlit run climate/streamlit_climate_demo.py
```

It opens at <http://localhost:8501>. A location selector drives everything; missing data
produces a plain message rather than an error.

To print a summary without a browser:

```bash
~/venvs/hit401_climate/bin/python -B climate/climate_models.py
```

---

## 6. What the charts show

| Chart | Based on |
|---|---|
| Water-year rainfall anomalies | One model run, 1975–2099, against the 1985–2014 mean (slides 28–30) |
| Is it getting wetter or drier? | All 11 runs, 2070–2099 against 1985–2014 (slide 31) |
| Observed water-year rainfall | Gauge 015643, against its own long-term mean |
| Rainfall residual mass | Gauge 015643, 1987–2026 |
| River flow residual mass | Gauge G0280010, mostly 2010 onwards |
| Three-panel figure | Rainfall, flow and bore levels on one time axis |
| Lag charts | Rainfall or flow anomaly against month-to-month bore movement |
| Wet vs dry season | Observed seasons with three models over the top |

Key conventions: a **water year** runs 1 September to 31 August and is labelled by its
starting year; the **10-year moving mean is trailing**, computed on the full series from
1850 and then cropped to 1975; **residual mass** is each month's total minus the long-term
average for that same calendar month, accumulated (BOM AWRA technical supplement).

---

## 7. Limitations — read before quoting any of this

1. **Model grid cells are coarse.** Cell centres sit 17–120 km from the point. Darwin and
   Ti Tree never share a cell, but a cell is a 100–250 km average, not a place.
2. **Our slide-31 numbers differ from the supervisor's.** We get 5 of 11 wetter for Darwin
   spanning −19.4% to +11.3%; his slide says 6 of 15 spanning −25.7% to +13.7%. Different
   data versions, a different grid cell and 4 runs we could not identify explain some of
   it. **CMCC-ESM2 is the outlier: we get +4.4%, the slide says −21.2%.** A 3×3 cell test
   gave +1.4% to +8.9% across every neighbouring cell, so the cell choice is not the cause.
   This is unresolved and worth asking Dylan about.
3. **Four slide-31 runs are missing.** The rows marked "coupled" could not be matched to a
   published run, so they were not guessed at.
4. **Two runs use a different variant** from the slides: CNRM-CM6-1-HR and GISS-E2-1-G use
   `r1i1p1f2`, because `r1i1p1f1` is not published for both experiments.
5. **The rain gauge is gappy.** About 5% of days have no value; 159 of 477 months are short
   at least one day. A month with more than 5 blank days is treated as missing and adds 0
   to the residual mass curve. Five water years are excluded outright.
6. **The river record is really two records.** 1974–2009 is sparse spot readings;
   2010–2026 is 10-minute telemetry. Only 110 of 626 months pass the coverage rule, nearly
   all after 2010. Quality code 210 ("not of release quality") covers 56% of rows; it is
   reported rather than dropped, because dropping it would remove most of the record.
7. **The bores are far from the gauge and short.** No bore within 10 km has a long enough
   record. The three used are 25.9–33.5 km away, and 48–72% of their months since 2010 have
   no reading.
8. **The lag charts are weak evidence.** The best rainfall correlations are r ≈ 0.25–0.35.
   Every flow-versus-bore lag for two of the three bores rests on fewer than 24 paired
   months and is not treated as a finding. Correlation is not causation.
9. **A residual mass curve computed over a whole record ends near zero** by construction.
   Read the slope, not the height.
10. **Licences differ from the project notes.** The files say CC BY-SA 4.0, and
    **CNRM-CM6-1-HR is CC BY-NC-SA 4.0 (NonCommercial)**. See `docs/climate/CITATIONS_CMIP6.md`.
11. **Seven of the eleven models have no verified DOI.** They are marked UNVERIFIED in
    `docs/climate/CITATIONS_CMIP6.md`; none was invented.

---

## 8. Adding this to the main dashboard

Nothing in the main app has been changed. When the team is ready, the whole section is one
import and one call:

```python
import climate_models

tab_map, tab_climate = st.tabs(["Map", "Climate"])
with tab_climate:
    climate_models.render_climate_tab()
```

`climate_models.py` only needs `plotly`, `pandas`, `numpy`, `xarray` and `netCDF4`; the
first two are already in the dashboard's `krishna-code/requirements.txt`. The climate
module's own list is `climate/requirements.txt`. Adding `xarray` and `netCDF4` to the
dashboard's shared list is proposed in `HANDOVER_climate.md` (kept locally, not committed)
rather than made here.
