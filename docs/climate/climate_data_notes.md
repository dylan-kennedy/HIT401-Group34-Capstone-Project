# HIT401 Group 34 – Climate modelling data notes (checked 7 Oct 2026)

## 1. Repo snapshot (dylan-kennedy/HIT401-Group34-Capstone-Project)

**Structure**
- `krishna-code/app(v1.2).py` – the current Streamlit app (there is no root `app.py`); `data.zip` (11 MB, shapefiles), `requirements.txt`
- `Datasets/`
  - `NT-NaturalResourceMapsBoreData/Bores.csv` (9.8 MB, NT-wide bore register)
  - `GroundwaterHeads_20250718/` – `Bores_Ti_Tree.csv`, `Bores_w_wl_data.csv/.xlsx`, `head_time_series_bores.csv`, 16 bore PNG plots, 16 `LocationExport-RNxxxxxx/` folders (60 CSVs: Depth Below Ground + Water Elevation (AHD), "Field Visits" and "Publish" series)
  - `BOM-Datasets/` – 11 BOM daily rainfall files `IDCJAC0009_<station>_1800_Data.csv` + notes
  - `StreamflowData/WaterCourseDischarge_G0280010_WoodfordeRiver-ArdenSoak_19740530-20260916.csv` (21 MB) + disclaimer
  - `DataSources.txt`
- Root scripts: `BOM_data_and_Stations.py`, `Colour_Indicator_Data_FilterMapTest.py`, `Folium_Bore_Implementation_Test.py`, `bore_gauge_distances.py`, `residual_mass_demo.py`; CSVs `bom_stations.csv`, `locations_index.csv`, `bore_gauge_distances_G0280010.csv`; `ti_tree_bores_map.html` (24 MB)
- `AppendixC_Code/` (gwrc_ingest.py, gwrc_trends.py, toolkit_demo.py), `dylan-code/`, `temp_CSVs/`, `Backup - Version History/`

**Columns**
- **Bores** (`Bores.csv`, `Bores_Ti_Tree.csv`, `Bores_w_wl_data.csv`): Bore no, Name, Bore report, Yield (L/s), Completion date, Drilled depth (m), Completion depth (m), Depth to water (m) at date of drilling, Purpose, Construction, Status, Latitude, Longitude, UTM zone, Easting, Northing, Position accuracy, Water data portal
- **Groundwater level time series** (LocationExport): Timestamp (UTC+09:30), Event Timestamp (UTC+09:30), Value (m)
- **Rainfall** (BOM IDCJAC0009): Product code, Bureau of Meteorology station number, Year, Month, Day, Rainfall amount (millimetres), Period over which rainfall was measured (days), Quality
- **River flow** (G0280010 Woodforde River – Arden Soak, m³/s; header lines start with `#`): Timestamp, Value, Quality Code, Interpolation Type
- **Water quality** (`Bores_water_quality.shp` inside data.zip, from app code): RN, SAMPLEDATE, TDS, EC_LAB, EC_FIELD, PH_LAB, PH_FIELD, CHLORIDE, NACL, HARD, ALK_TOTAL, NA_TOTAL, CA_SOL, MG_SOL, SO4_TOTAL, NO3, FE_TOTAL, HCO3, TEMP

**app(v1.2).py imports:** pathlib.Path, folium, geopandas, pandas, plotly.graph_objects, pyogrio, streamlit, streamlit_folium.st_folium
(requirements.txt: streamlit, pandas, geopandas, pyogrio, folium, streamlit-folium, plotly, openpyxl)

⚠️ `bom_stations.csv` lists Perth, Gnowangerup, Fort Hill Wharf, Adelaide, Mulgrave Mill, Woolshed, Brisbane, Sydney, Melbourne, Hobart: none of them are in the NT. You'll need NT stations (e.g. near Ti Tree/Alice Springs) for the rainfall comparison.

## 2. Sources compared

| Source | Monthly tas+pr, hist/ssp245/ssp585 | Login? | Region subset? | Verdict |
|---|---|---|---|---|
| **ESGF via NCI node** (esgf.nci.org.au) | All 10 models available (MPI-ESM1-2 = LR or HR) | **No** for CMIP6 download/OPeNDAP | Yes, via OPeNDAP with xarray (only the NT box is transferred) | **Easiest overall**: no account, Australian server |
| **Copernicus CDS** (projections-cmip6) | Complete only for CMCC-ESM2, CNRM-CM6-1, FGOALS-g3, GFDL-ESM4, MPI-ESM1-2-LR, MRI-ESM2-0. Gaps: ACCESS-ESM1-5 (hist only), NorESM2-LM (no hist), MPI-ESM1-2-HR (hist only), EC-Earth3 & GISS-E2-1-G (none of these combos) | **Yes**: ECMWF account + accept CMIP6 licence + API key | Yes (area box in form/API) | Easy point-and-click, but needs an account |
| **Climate Change in Australia** | Only 9 ACS GCMs (overlap: ACCESS-ESM1-5, CMCC-ESM2, EC-Earth3, MPI-ESM1-2-HR). **Daily, bias-adjusted, 30-yr slices (2035-64, 2070-99) only**, no raw monthly or historical runs, no ssp245 monthly series | No | Yes (NetcdfSubset) | Good for application-ready local data, but doesn't match the brief |

ESGF LLNL (esgf-node.llnl.gov) now redirects to the ESGF MetaGrid UI at metagrid.esgf-west.org.

## 3. Recommended 3 models (complete on both ESGF and CDS)
**MPI-ESM1-2-LR, MRI-ESM2-0, GFDL-ESM4** (member r1i1p1f1). If you want an Australian model, ACCESS-ESM1-5 is complete on NCI ESGF but not on CDS.

### Option A – ESGF/NCI OPeNDAP (no login)
Base: `https://esgf.nci.org.au/thredds/dodsC/esgcet/replica/CMIP6/`
- MPI-ESM1-2-LR (grid gn, v20190710; 20-year files: hist 9 files, ssp 5 files)
  - `CMIP/MPI-M/MPI-ESM1-2-LR/historical/r1i1p1f1/Amon/{tas,pr}/gn/v20190710/`
  - `ScenarioMIP/MPI-M/MPI-ESM1-2-LR/{ssp245,ssp585}/r1i1p1f1/Amon/{tas,pr}/gn/v20190710/`
- MRI-ESM2-0 (gn)
  - `CMIP/MRI/MRI-ESM2-0/historical/r1i1p1f1/Amon/{tas,pr}/gn/v20190222/{var}_Amon_MRI-ESM2-0_historical_r1i1p1f1_gn_185001-201412.nc`
  - `ScenarioMIP/MRI/MRI-ESM2-0/ssp245/r1i1p1f1/Amon/{tas,pr}/gn/v20190222/..._201501-210012.nc`
  - `ScenarioMIP/MRI/MRI-ESM2-0/ssp585/r1i1p1f1/Amon/{tas,pr}/gn/v20191108/..._201501-210012.nc` (a second file covers 2101–2300; skip it)
- GFDL-ESM4 (grid gr1)
  - historical (not on NCI; use CEDA): `https://esgf.ceda.ac.uk/thredds/dodsC/esg_cmip6/CMIP6/CMIP/NOAA-GFDL/GFDL-ESM4/historical/r1i1p1f1/Amon/{tas,pr}/gr1/v20190726/` (files 185001-194912, 195001-201412)
  - `ScenarioMIP/NOAA-GFDL/GFDL-ESM4/{ssp245,ssp585}/r1i1p1f1/Amon/{tas,pr}/gr1/v20180701/..._201501-210012.nc`
- Find/verify any file: https://esgf.nci.org.au/esg-search/search?project=CMIP6&source_id=MRI-ESM2-0&experiment_id=ssp245&variable_id=tas&table_id=Amon&member_id=r1i1p1f1&type=File&latest=true&distrib=true (file-level results include HTTPServer and OPENDAP links). HTTP download: swap `dodsC` for `fileServer`.

```python
import xarray as xr   # pip install xarray netCDF4
url = "https://esgf.nci.org.au/thredds/dodsC/esgcet/replica/CMIP6/ScenarioMIP/MRI/MRI-ESM2-0/ssp245/r1i1p1f1/Amon/tas/gn/v20190222/tas_Amon_MRI-ESM2-0_ssp245_r1i1p1f1_gn_201501-210012.nc"
ds = xr.open_dataset(url)
nt = ds["tas"].sel(lat=slice(-26, -10), lon=slice(129, 138))   # lon is 0-360, so 129-138 works as is
nt.to_netcdf("tas_MRI-ESM2-0_ssp245_NT.nc")
# tas is in K (subtract 273.15); pr is in kg m-2 s-1 (multiply by 86400 × days in month for mm/month)
```

### Option B – Copernicus CDS API (needs login)
Dataset page: https://cds.climate.copernicus.eu/datasets/projections-cmip6?tab=download
```python
import cdsapi   # needs ~/.cdsapirc
c = cdsapi.Client()
c.retrieve("projections-cmip6", {
    "temporal_resolution": "monthly",
    "experiment": "ssp2_4_5",            # or "historical", "ssp5_8_5"
    "variable": "near_surface_air_temperature",   # or "precipitation"
    "model": "mpi_esm1_2_lr",            # or "mri_esm2_0", "gfdl_esm4"
    "year": [str(y) for y in range(2015, 2101)],  # historical: 1850-2014
    "month": [f"{m:02d}" for m in range(1, 13)],
    "area": [-10, 129, -26, 138],        # N, W, S, E
}, "mpi_ssp245_tas_NT.zip")              # zip containing NetCDF
```
**What you need to do yourselves (I did not create accounts or accept terms):**
1. Register for an ECMWF account at https://cds.climate.copernicus.eu (top-right Login/Register).
2. On the dataset's Download tab, tick and accept "CMIP6 – Data Access – Terms of Use".
3. Copy your API token from your CDS profile page into `~/.cdsapirc`:
   `url: https://cds.climate.copernicus.eu/api` / `key: <your-token>`
4. `pip install cdsapi`

### Expected sizes (all NetCDF, monthly)
- **NT subset (A or B): under ~2 MB per model/variable/experiment, about 10–20 MB total for all 18 requests.** None needs approval under your 500 MB limit.
- Full global files if downloaded whole (r1i1p1f1, to 2100): MPI-ESM1-2-LR ≈ 360 MB total (hist tas 66 / pr 109, each SSP tas 35 / pr 57); MRI-ESM2-0 ≈ 1.1 GB (hist tas 225 / pr 321, each SSP tas 117 / pr 167); GFDL-ESM4 ≈ 1.1 GB (hist tas 230 / pr 320, each SSP tas 120 / pr 167). Single files are under 500 MB, but the sets are not, so subset instead.

## 4. Licence and citation text for the report
- Licence: CC BY 4.0 for these models (per the DataCite records). Older file headers say CC BY-SA 4.0, so quote the `license` attribute from the files you use. Terms: https://pcmdi.llnl.gov/CMIP6/TermsOfUse
- Required acknowledgement: "We acknowledge the World Climate Research Programme, which, through its Working Group on Coupled Modelling, coordinated and promoted CMIP6. We thank the climate modeling groups for producing and making available their model output, the Earth System Grid Federation (ESGF) for archiving the data and providing access, and the multiple funding agencies who support CMIP6 and ESGF."
- Include a table of models + institutions (official source_id names). If you use CDS, also cite the dataset: doi:10.24381/cds.c866074c
- Dataset citations (DOIs verified on DataCite):
  - Krasting, J. P. et al. (2018) NOAA-GFDL GFDL-ESM4 model output prepared for CMIP6 CMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.1407
  - John, J. G. et al. (2018) NOAA-GFDL GFDL-ESM4 model output prepared for CMIP6 ScenarioMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.1414
  - Yukimoto, S. et al. (2019) MRI MRI-ESM2.0 model output prepared for CMIP6 CMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.621
  - Yukimoto, S. et al. (2019) MRI MRI-ESM2.0 model output prepared for CMIP6 ScenarioMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.638
  - Wieners, K.-H. et al. (2019) MPI-M MPIESM1.2-LR model output prepared for CMIP6 CMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.742
  - Wieners, K.-H. et al. (2019) MPI-M MPIESM1.2-LR model output prepared for CMIP6 ScenarioMIP. ESGF. https://doi.org/10.22033/ESGF/CMIP6.793
  - (optional) Ziehn, T. et al. (2019) CSIRO ACCESS-ESM1.5 … CMIP / ScenarioMIP: https://doi.org/10.22033/ESGF/CMIP6.2288, https://doi.org/10.22033/ESGF/CMIP6.2291
- Also cite O'Neill et al. (2016) ScenarioMIP, GMD 9, 3461 (https://gmd.copernicus.org/articles/9/3461/2016/) and Eyring et al. (2016) CMIP6 overview, GMD 9, 1937.

## 5. Newer versions?
- **CMIP7** is publishing on ESGF. As of 6 Oct 2026 only 7 models are listed: CanESM5-1, CanESM6-0-MR, UKESM1-3-LL, UKCM2-0-LL, UKCM2a-0-HH, EC-Earth3-ESM-1-1 and CNRM-ESM2-1e. From your list, only EC-Earth3 (as EC-Earth3-ESM-1-1) and the CNRM family (CNRM-ESM2-1e) have successors so far. CMIP7 uses new scenarios (scen7-h/m/vl…) instead of ssp245/ssp585, so it isn't a drop-in swap. ACCESS-ESM1.6 and EC-Earth4 are announced for CMIP7 but weren't on that list.
- Within CMIP6, higher-resolution or ESM variants exist: MPI-ESM1-2-HR, NorESM2-MM, EC-Earth3-Veg/-CC, CNRM-CM6-1-HR/CNRM-ESM2-1, GISS-E2-1-H/E2-2-G, FGOALS-f3-L, ACCESS-CM2. Newer dataset *versions* also exist (e.g. MRI ssp585 v20191108 vs ssp245 v20190222), so always request `latest=true`.
- For an assignment that uses ssp245/ssp585, sticking with CMIP6 is standard and defensible.

## Links
- Repo: https://github.com/dylan-kennedy/HIT401-Group34-Capstone-Project
- CDS CMIP6: https://cds.climate.copernicus.eu/datasets/projections-cmip6
- ESGF NCI search API: https://esgf.nci.org.au/esg-search/search
- ESGF MetaGrid UI: https://metagrid.esgf-west.org/search/cmip6/
- CCiA downloads: https://www.climatechangeinaustralia.gov.au/en/obtain-data/download-datasets/ (CMIP6 data: https://data-cbr.csiro.au/thredds/catalog/catch_all/qdc-cmip6/catalog.html; technical report https://doi.org/10.25919/03by-9y62)
- CMIP7 availability tracker: https://www.climate-resource.com/tools/esm-model/cmip7-availability/models
- CMIP7 guidance: https://wcrp-cmip.github.io/cmip7-guidance/docs/CMIP7/Guidance_for_users/
- EC-Earth4 & CMIP7: https://ec-earth.org/ec-earth-and-cmip/ec-earth4-and-cmip7/
- ACCESS-ESM1.6 (CMIP7): https://forum.access-hive.org.au/t/cmip7-fast-track-publication-land-model-description-for-access-esm1-6/6511