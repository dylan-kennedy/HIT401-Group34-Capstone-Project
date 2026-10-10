# HIT401-Group34-Capstone-Project

A project repository for Group 34's 'HIT401 - Capstone Project' code.

Supervisor: Dr Cat Kutay

Group 34 Team:

Krishna Dhakal	S396451
Gaurab Gaihre	S387897
Dylan Kennedy	S343881
Sachin Kharel	S399310

Datasets origins\*:
"GroundwaterHeads\_20250718" - Shared by supervisor Dr Cat Kutay via email with the team.

"Bores.csv" inside "NT-NaturalResourceMapsBoreData" - Can be downloaded directly through Northern Territory's Natural Resource Maps website (at https://nrmaps.nt.gov.au/nrmaps.html), but the current version 4/09/26 was provided via email exchange between Group 34, supervisor Dr Cat Kutay, and Associate Professor Dylan Irvine, by Dylan.

"BOM-Datasets" - Provided by supervisor, but can and likely will be updated by location from the source at the BOM website: https://www.bom.gov.au/climate/data/

\*This information is also located alongside the datasets under "DataSources.txt" - possibly remove both this + the .txt file later.

# Edit readme later

To Use python Files:

Will need to run python install commands for packages listed before code next to 'import X' (all simple) if you don't have them installed already:
folium, pandas, matplotlib, requests, probably one or two more but can't remember which are main packages and which come with those main packages, just run the install command for the name of the package and see what it says I guess.

can use 'pip install (package name)' if you have 'pip' configured / installed, otherwise need to configure / install pip first







Running Krishna's Code (edit as we go, file path will likely change later)



Unzip 'data.zip' from krishna-code/

* file size too big for GitHub repo...



> Set up virtual environment 



"python -m venv krishna-code/.venv"



> Activate virtual environment



"krishna-code/.venv/Scripts/activate.ps1"



> Install dependencies (from requirements.txt)



"pip install -r krishna-code/requirements.txt"



> Run the app.py file (modify to latest version num) with streamlit



"streamlit run krishna-code\\"app(v1.2).py"" - include quotes around "app(v1.2).py", until we rename it.


Running dylan's version, similar commands.

Extract the data.zip folder into the same dylan-code folder first.

"python -m venv dylan-code/.venv"

"dylan-code/.venv/Scripts/activate.ps1"
(If the above doesn't work, try this first: "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" - temporary bypass for scripts being disabled on windows machines)

"pip install -r dylan-code/requirements.txt"

"streamlit run dylan-code\Updated_Dashboard_Prototype.py"

"deactivate" when finished & delete .venv folder if you wish.


---

## Running the Web Application (Data Explorer & Climate Analysis)

The unified web application in `webapp/` provides full exploratory access to all Northern Territory bore datasets, water quality samples, streamflow records, BOM rainfall, Ti Tree aquifer overlay layers, and integrated CMIP6 climate models / hydrology analyses.

This directly addresses **Cat's Aim 2**: analysing seasonal recharge patterns and investigating the relationship between bore levels and rainfall.

### 1. Setup & Installation
Install dependencies:
```bash
pip install -r webapp/requirements.txt
```

### 2. Build Cache (if setting up fresh or after raw data changes)
```bash
python webapp/build_cache.py
```

### 3. Launch the Server
```bash
python webapp/server.py
```
Open **http://127.0.0.1:8000** in your browser.

### 4. Climate & Hydrology Analyses
Switch to the **Climate** view using the top navigation bar to explore:
- **Seasonal Recharge (Observed vs Modelled)**: Wet season (Nov–Apr) and dry season (May–Oct) rainfall totals per year using `seasonal_totals_observed` for gauge records (Territory Grape Farm 015643) and `seasonal_totals_model` for CMIP6 model projections. Users can toggle projections out to 2099 and download chart data as CSV.
- **Rainfall, River Flow, and Bore Water Levels (Time Series Comparison)**: 3-panel comparison using `plot_rain_flow_bores` across the modern telemetry record (2010 onwards) examining rainfall residual mass, Woodforde River flow residual mass, and monitoring bore water levels (m AHD).
- **Lag Correlation (Rainfall & Streamflow vs Bore Levels)**: Time-lagged Pearson correlation analysis using `lag_correlations` comparing monthly anomalies against month-to-month changes in bore levels across 0–12+ months to investigate recharge timing hints.

### 5. Running Tests
```bash
python webapp/tests/test_api.py
python webapp/tests/test_build_cache.py
```