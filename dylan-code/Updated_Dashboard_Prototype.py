##############################################################
##                                                           #
##             NT Water Management Dashboard                 #
#            (or some other name, not sure yet)              #
##                                                           #
##      An extension of app(v1.2).py from ./krishna-code     #
##                with my additions + fixes                  #
##                                                           #
##############################################################


### New Additions - Project is still in a proof of concept stage at the moment ###
# - Added filter to select State / Territory, city / suburb could be added later if necessary but are part of search feature for now. 
# - Added filter to hide markers not within the map's extent (not in the current borders of the map, so zoom in / pan around and they'll disappear until you return) - basic version of below (planned)
#   - Plan to extend this feature by grouping markers into one icon (marker clustering) but still need to work out how to do that with this existing code, 
#      mainly only for future use with significantly more data that would need to be loaded to reduce load times & strain on older hardware.
#   - Does cause constant refreshing so please uncheck this feature if you want to move around freely - maybe need to add a warning to user as help popup or something?
# - Added code comments to sections I've added / modified and some to existing sections where possible, rest is as it originally was.
# - Fixed map automatically refreshing when panning/zooming/clicking anywhere that isn't a marker by adjusting st.sessionstate, now only refresh on marker click (toggle comparison), or constantly with the map extent option turned on.
# - Added the BOM data we have (can easily add more files to it now too but only thing new additions won't have is the State recognised - it will still be placed correctly on map).
#   - Added a lot more of the NT region ones for proof-of-concept, analysis feature available in 'BOM Climate Data' dashboard mode - need to select station from dashboard controls (bottom left of screen).


### Project Notes ###
# - Reintroduce restriction to selected bores? Originally was 5 with my existing project (Colour_Indicator_Data_FilterMapTest.py), this one can handle more than 20 though on my machine so could leave as is.
# - Need to double check / reintroduce the specific data architecture from our provided datasets (CSVs - this version uses shapefiles or similar currently), possibly as a separate dashboard mode, 
#   so that users can just add their own downloaded data into the data folder and see the map update (maybe in real time if auto-re-run is enabled).
#        - Unless we can get automatic data downloads working...?
# - One problem I noticed is the code currently pulls the available website for a bore from the data (in shapefile & original CSVs) under the 'water.nt.gov.au' url specified in the water_data col, when new url is 'ntg.aquaticinformatics.net'. 
#     A redirect is auto prompted through our "Open station in NT Water Data Portal" (groundwater-monitoring locations dashboard mode) button which leads to to "https://water.nt.gov.au/Data/Location/Summary/Location/G0060008/Interval/Latest" and not 
#     "https://ntg.aquaticinformatics.net/Data/Location/Summary/Location/G0060008/Interval/Latest" like it should. 
#     - May need to disregard use of this column and instead rebuild the URL using the Bore / Station IDs - come back to this.
# - May need to adjust markers, they automatically add / remove data from comparison and don't give you a chance to read popup. Might need more info too, but info is displayed alongside comp graph + below in a table anyway.
# - Need to add a toggle for the BOM Climate Data dashboard that lets user choose to enable clicking on a BOM marker to select for rainfall comparison plot
#   or to leave off to use only the drop down menu selector on the dashboard controls panel (left side)
# - Need to make my Legend selective, so disable it automatically when the existing legend is loaded (for chem analysis mode etc)
# - BOM Data consists of Daily Rainfall only at the moment, other options are: Weather & Climate, Temperature, Solar Exposure. Rainfall seemed most relevant for now in current stage.
# - Adding extra BOM data, you will currently need to manually edit bom_stations.csv. Will address later.


# Note: I used google AI to assist with finding a solution to the map refreshing problem, the fix identified was to use streamlit fragments to isolate parts that would need constant re-running
# and under the advice of AI, have created a duplicate version of the code for relevant original sections (e.g. BORE-DETAILS, MONITORING-LOCATIONS, etc) and sections with my additions, separating the original + duplicate by if / else statements. 
# This does mean that with the if: else: statements, the code is 1000+ lines bigger than it would have been otherwise. 
# AI was also partially used for both consultation and implementation of some other code to help with troubleshooting, compatibility with existing code and data formats and bug fixes where necessary after making my own additions and edits. 


# Import relevant dependencies, will need to install them with "pip install -r requirements.txt" first, ideally in a venv.
from pathlib import Path
import html

import folium
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import pyogrio
import streamlit as st
from streamlit_folium import st_folium


# ---------------------------------------------------------
# PAGE SETTINGS
# ---------------------------------------------------------

st.set_page_config(
    page_title="NT Water Management Dashboard",       # Renamed from "Ti Tree Water Dashboard" to something more general (NT because that's the data we have).
    page_icon="💧",
    layout="wide",
)

# May need to adjust title later when we finalise project, leaving as a placeholder for now while we workshop it (our data is Ti Tree mostly anyway)
st.title("NT Water Management Dashboard")           #"Ti Tree Water Dashboard")

st.caption(
    "This tool allows exploration of historical bore water quality, bore details and chemical composition, "
    "groundwater monitoring locations, and Australian Government - Bureau of Meteorology (BOM) climate data.\n\n Please use the dashboard controls on the left to select a dashboard mode, search for a location or bore/station on the map, and explore other relevant options available.\n\n"
    "NOTE: This dashboard primarily uses available Ti Tree bore data only (with BOM stations + data analysis available in the BOM Climate Data dashboard option), and is still in a developmental or proof-of-concept stage. Additional data and tool generalisation are planned for future updates. "
)

# Add the Acknowledgement of Country
st.markdown(
    """
    <div style="
        padding:0.85rem 1rem;
        margin:0.5rem 0 1.25rem 0;
        border-left:4px solid #b45309;
        border-radius:0.35rem;
        background-color:#fff7ed;
        color:#431407;
    ">
        <strong>Acknowledgement of Country</strong><br>
        We acknowledge the Traditional Custodians of the lands and
        waters represented in this dashboard. We pay our respects to
        Elders past and present and recognise their continuing
        connection to Country, culture, land and water.
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# MEASUREMENTS AND COLOURS
# ---------------------------------------------------------

measurements = {
    "Total dissolved solids": "TDS",
    "Laboratory electrical conductivity": "EC_LAB",
    "Chloride": "CHLORIDE",
    "Calculated NaCl": "NACL",
    "Laboratory pH": "PH_LAB",
    "Hardness": "HARD",
    "Alkalinity": "ALK_TOTAL",
    "Sodium": "NA_TOTAL",
    "Calcium": "CA_SOL",
    "Magnesium": "MG_SOL",
    "Sulphate": "SO4_TOTAL",
    "Nitrate": "NO3",
    "Fluoride": "F",
    "Iron": "FE_TOTAL",
    "Bicarbonate": "HCO3",
    "Field electrical conductivity (limited data)": "EC_FIELD",
    "Field pH (limited data)": "PH_FIELD",
    "Water temperature (limited data)": "TEMP",
}

selection_colours = [
    {"marker": "black", "hex": "#303030"},
    {"marker": "green", "hex": "#72b026"},
    {"marker": "orange", "hex": "#f69730"},
    {"marker": "purple", "hex": "#d252b9"},
    {"marker": "darkblue", "hex": "#0067a3"},
    {"marker": "darkred", "hex": "#a23336"},
    {"marker": "cadetblue", "hex": "#436978"},
    {"marker": "darkgreen", "hex": "#728224"},
    {"marker": "darkpurple", "hex": "#5b396b"},
    {"marker": "pink", "hex": "#ff91ea"},
    {"marker": "lightred", "hex": "#ff8e7f"},
    {"marker": "beige", "hex": "#ffcb92"},
    {"marker": "lightblue", "hex": "#8adaff"},
    {"marker": "lightgreen", "hex": "#bbf970"},
    {"marker": "gray", "hex": "#575757"},
    {"marker": "lightgray", "hex": "#a3a3a3"},
]

# ---------------------------------------------------------
# FILE LOCATIONS
# ---------------------------------------------------------

# Defining all of the locations for our data (Shapefiles, CSVs) and relevant index files. Allowing for differences in naming conventions as well.

project_folder = Path(__file__).parent

def first_existing(*choices):
    for choice in choices:
        if choice.exists():
            return choice
    return choices[0]

data_folder = first_existing(
    project_folder / "data",
    project_folder / "Data",
)

nt_bores_folder = first_existing(
    data_folder / "nt_bores",
    data_folder / "NT_Bores",
)

ti_tree_folder = first_existing(
    data_folder / "ti_tree" / "data",
    data_folder / "Ti_Tree" / "data",
    data_folder / "ti_tree",
)

# BOM sample data is kept in its own folder so the original CSV files are not modified.
bom_folder = first_existing(
    project_folder / "Datasets" / "BOM-Datasets",
    data_folder / "BOM-Datasets",
    data_folder / "bom",
    data_folder / "bom_sample",
)

# Path to our manually edited (for now) index file 
bom_stations_file = bom_folder / "bom_stations.csv"

# ---------------------------------------------------------
# NATIONAL MAP LOCATIONS
# ---------------------------------------------------------

### -- Australian map focal points -- ###
# - Adding markers to indicate State + key locations (towns / cities) around Australia on the map
# Hard coded with lat/lon points, will use a coloured flag icon to distinguish it from the other markers / icons on map. 
# Can click on a marker and jump to it (code elsewhere), 3rd value below after lat/lon is the zoom level. 

AUSTRALIA_STATE_MARKERS = {
    "Australian Capital Territory": (-35.28, 149.13, 10),
    "New South Wales": (-32.00, 147.00, 6),
    "Northern Territory": (-19.50, 133.50, 6),
    "Queensland": (-22.58, 144.08, 6),
    "South Australia": (-30.00, 135.00, 6),
    "Tasmania": (-42.00, 146.50, 7),
    "Victoria": (-36.80, 144.00, 7),
    "Western Australia": (-25.50, 121.00, 6),
}

# Specifying some key towns / cities around Australia and their lat/lon to be markers.
KEY_LOCATIONS = [
    ("Alice Springs", "Northern Territory", -23.70, 133.88),
    ("Darwin", "Northern Territory", -12.46, 130.84),
    ("Katherine", "Northern Territory", -14.47, 132.26),
    ("Tennant Creek", "Northern Territory", -19.65, 134.19),
    ("Ti Tree", "Northern Territory", -21.10, 134.18),
    ("Perth", "Western Australia", -31.95, 115.86),
    ("Kalgoorlie", "Western Australia", -30.75, 121.47),
    ("Broome", "Western Australia", -17.96, 122.24),
    ("Geraldton", "Western Australia", -28.78, 114.61),
    ("Port Hedland", "Western Australia", -20.31, 118.58),
    ("Adelaide", "South Australia", -34.93, 138.60),
    ("Port Augusta", "South Australia", -32.49, 137.77),
    ("Whyalla", "South Australia", -33.03, 137.58),
    ("Mount Gambier", "South Australia", -37.83, 140.78),
    ("Brisbane", "Queensland", -27.47, 153.03),
    ("Cairns", "Queensland", -16.92, 145.77),
    ("Townsville", "Queensland", -19.26, 146.82),
    ("Rockhampton", "Queensland", -23.38, 150.51),
    ("Toowoomba", "Queensland", -27.56, 151.95),
    ("Sydney", "New South Wales", -33.87, 151.21),
    ("Newcastle", "New South Wales", -32.93, 151.78),
    ("Dubbo", "New South Wales", -32.26, 148.60),
    ("Wagga Wagga", "New South Wales", -35.12, 147.37),
    ("Broken Hill", "New South Wales", -31.95, 141.45),
    ("Melbourne", "Victoria", -37.81, 144.96),
    ("Geelong", "Victoria", -38.15, 144.36),
    ("Bendigo", "Victoria", -36.76, 144.28),
    ("Mildura", "Victoria", -34.19, 142.16),
    ("Hobart", "Tasmania", -42.88, 147.33),
    ("Launceston", "Tasmania", -41.43, 147.14),
    ("Devonport", "Tasmania", -41.18, 146.35),
    ("Burnie", "Tasmania", -41.05, 145.91),
    ("Canberra", "Australian Capital Territory", -35.28, 149.13),
]

bores_file = nt_bores_folder / "Bores.shp"
quality_file = nt_bores_folder / "Bores_water_quality.shp"
monitoring_file = nt_bores_folder / "Bores_groundwater_level.shp"

boundary_file = ti_tree_folder / "ttbaq_250_bnd.shp"
salinity_file = ti_tree_folder / "ttbaq_250_sal.shp"
aquifer_file = ti_tree_folder / "ttbaq_250_aqt.shp"
water_depth_file = ti_tree_folder / "ttbaq_250_wd.shp"
contour_file = ti_tree_folder / "ttbaq_250_cnt.shp"

required_files = [
    bores_file,
    quality_file,
    monitoring_file,
    boundary_file,
    salinity_file,
    aquifer_file,
    water_depth_file,
    contour_file,
]

missing_files = [
    str(path)
    for path in required_files
    if not path.exists()
]

if missing_files:
    st.error(
        "The dashboard cannot find all required data files. "
        "Check that the extracted data folders are beside app.py."
    )
    st.code("\n".join(missing_files))
    st.stop()

# ---------------------------------------------------------
# DATA FUNCTIONS
# ---------------------------------------------------------

def normalise_bore_number(value):
    if pd.isna(value):
        return None

    text = str(value).strip().upper().replace(" ", "")

    if text.startswith("RN"):
        digits = "".join(
            character
            for character in text[2:]
            if character.isdigit()
        )

        if digits:
            return f"RN{int(digits):06d}"

    return text or None

def parse_nt_date(series):
    return pd.to_datetime(
        series.astype("string").str.slice(0, 8),
        format="%Y%m%d",
        errors="coerce",
    )

# Use the bom_stations.csv index file. Manually mapping states to station IDs for now to avoid editing the index (we use it for other scripts / tests currently) 
# with the column names: Station, StationName, Latitude and Longitude.  
# We add only derived columns (State and DataFile) to avoid editing the CSV, as below. 
BOM_STATION_STATES = {
    "009021": "Western Australia",
    "010558": "Western Australia",
    "014050": "Northern Territory",
    "023055": "South Australia",
    "031049": "Queensland",
    "033307": "Queensland",
    "040913": "Queensland",
    "066006": "New South Wales",
    "086282": "Victoria",
    "094029": "Tasmania",
}

def load_bom_stations():
    # Load all available BOM stations from the index, add our derived columns State and DataFile
    if not bom_stations_file.exists():
        return pd.DataFrame(
            columns=["Station", "StationName", "Latitude", "Longitude", "State", "DataFile"]
        )

    stations = pd.read_csv(
        bom_stations_file,
        dtype={"Station": "string"},
    )

    # Match the station numbers to the rainfall files and add some metadata to display (no edits to CSV)
    stations["Station"] = stations["Station"].str.zfill(6)
    stations["State"] = stations["Station"].map(BOM_STATION_STATES).fillna("Unknown")

    data_files = {
        path.stem.split("_")[1]: path
        for path in bom_folder.glob("IDCJAC0009_*_Data.csv")
        if len(path.stem.split("_")) > 1
    }
    stations["DataFile"] = stations["Station"].map(data_files)

    return stations.dropna(subset=["Latitude", "Longitude"]).copy()

# Load the daily rainfall CSVs for each BOM station - will only load one at a time (the currently selected one)
@st.cache_data(show_spinner=False)
def load_bom_rainfall(station_id):
    if bom_stations.empty:
        return pd.DataFrame()

    match = bom_stations.loc[
        bom_stations["Station"].eq(str(station_id).zfill(6))
    ]
    if match.empty or pd.isna(match.iloc[0]["DataFile"]):
        return pd.DataFrame()

    path = Path(match.iloc[0]["DataFile"])
    if not path.exists():
        return pd.DataFrame()

    data = pd.read_csv(path)
    data["Date"] = pd.to_datetime(
        dict(year=data["Year"], month=data["Month"], day=data["Day"]),
        errors="coerce",
    )
    data["Rainfall"] = pd.to_numeric(
        data["Rainfall amount (millimetres)"],
        errors="coerce",
    )
    return data.dropna(subset=["Date"])

bom_stations = load_bom_stations()

@st.cache_data(show_spinner="Loading and preparing Ti Tree data...")
def load_data():
    boundary = gpd.read_file(
        boundary_file
    ).to_crs(epsg=4326)

    salinity = gpd.read_file(
        salinity_file
    ).to_crs(epsg=4326)

    aquifer = gpd.read_file(
        aquifer_file
    ).to_crs(epsg=4326)

    water_depth = gpd.read_file(
        water_depth_file
    ).to_crs(epsg=4326)

    contours = gpd.read_file(
        contour_file
    ).to_crs(epsg=4326)

    study_area = boundary.geometry.union_all()

    quality = pyogrio.read_dataframe(
        quality_file,
        columns=[
            "BORE_NO",
            "SAMPLEDATE",
            *measurements.values(),
        ],
    ).to_crs(epsg=4326)

    quality["BORE_NO"] = quality["BORE_NO"].map(
        normalise_bore_number
    )

    quality["SAMPLEDATE"] = pd.to_datetime(
        quality["SAMPLEDATE"],
        errors="coerce",
    )

    for column in measurements.values():
        quality[column] = pd.to_numeric(
            quality[column],
            errors="coerce",
        )

    quality = quality.dropna(
        subset=[
            "BORE_NO",
            "SAMPLEDATE",
            "geometry",
        ]
    )

    quality = quality[
        quality.geometry.intersects(study_area)
    ].copy()

    bore_summary = (
        quality.groupby("BORE_NO")
        .agg(
            SAMPLE_COUNT=("BORE_NO", "size"),
            FIRST_SAMPLE=("SAMPLEDATE", "min"),
            LATEST_SAMPLE=("SAMPLEDATE", "max"),
        )
        .reset_index()
    )

    quality_locations = (
        quality.sort_values("SAMPLEDATE")
        .drop_duplicates(
            "BORE_NO",
            keep="last",
        )[
            [
                "BORE_NO",
                "geometry",
            ]
        ]
        .merge(
            bore_summary,
            on="BORE_NO",
            how="left",
        )
    )

    quality_locations = gpd.GeoDataFrame(
        quality_locations,
        geometry="geometry",
        crs="EPSG:4326",
    )

    quality_locations["latitude"] = (
        quality_locations.geometry.y
    )

    quality_locations["longitude"] = (
        quality_locations.geometry.x
    )

    bores = pyogrio.read_dataframe(
        bores_file,
        columns=[
            "BORE_NO",
            "BORE_NAME",
            "LOCALITY",
            "BOREREPORT",
            "DRY_RISK",
            "RISK_CLASS",
            "STATUS",
            "STATUSCONS",
            "PURPOSE",
            "MONITORED",
            "YIELD",
            "COMPL_DATE",
            "COMPLDEPTH",
            "DRILLDEPTH",
            "WATERLEVEL",
            "TESTDATE",
        ],
    ).to_crs(epsg=4326)

    bores["BORE_NO"] = bores["BORE_NO"].map(
        normalise_bore_number
    )

    bores["COMPL_DATE"] = parse_nt_date(
        bores["COMPL_DATE"]
    )

    bores["TESTDATE"] = parse_nt_date(
        bores["TESTDATE"]
    )

    for column in [
        "RISK_CLASS",
        "YIELD",
        "COMPLDEPTH",
        "DRILLDEPTH",
        "WATERLEVEL",
    ]:
        bores[column] = pd.to_numeric(
            bores[column],
            errors="coerce",
        )

    bores = bores.dropna(
        subset=[
            "BORE_NO",
            "geometry",
        ]
    )

    bores = bores[
        bores.geometry.intersects(study_area)
    ].copy()

    bores = bores.drop_duplicates(
        "BORE_NO",
        keep="first",
    )

    bores["latitude"] = bores.geometry.y
    bores["longitude"] = bores.geometry.x

    monitoring = pyogrio.read_dataframe(
        monitoring_file,
        columns=[
            "STATION",
            "STATION_NA",
            "MONITOR_TY",
            "WATER_DATA",
            "COMMENCE",
            "CEASE",
            "ACTIVE",
        ],
    ).to_crs(epsg=4326)

    monitoring["COMMENCE"] = parse_nt_date(
        monitoring["COMMENCE"]
    )

    monitoring["CEASE"] = parse_nt_date(
        monitoring["CEASE"]
    )

    monitoring = monitoring.dropna(
        subset=[
            "STATION",
            "geometry",
        ]
    )

    monitoring = monitoring[
        monitoring.geometry.intersects(study_area)
    ].copy()

    monitoring = monitoring.drop_duplicates(
        "STATION",
        keep="first",
    )

    monitoring["latitude"] = monitoring.geometry.y
    monitoring["longitude"] = monitoring.geometry.x

    for display_layer in (
        boundary,
        salinity,
        aquifer,
        water_depth,
        contours,
    ):
        display_layer["geometry"] = (
            display_layer.geometry.simplify(
                tolerance=0.0005,
                preserve_topology=True,
            )
        )

    return (
        boundary,
        salinity,
        aquifer,
        water_depth,
        contours,
        quality,
        quality_locations,
        bores,
        monitoring,
    )

(
    boundary,
    salinity,
    aquifer,
    water_depth,
    contours,
    quality,
    quality_locations,
    bores,
    monitoring,
) = load_data()

minimum_x, minimum_y, maximum_x, maximum_y = boundary.total_bounds

default_centre = [
    (minimum_y + maximum_y) / 2,
    (minimum_x + maximum_x) / 2,
]

if "map_center" not in st.session_state:
    st.session_state.map_center = default_centre

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 8

if "map_bounds" not in st.session_state:
    st.session_state.map_bounds = None

# ---------------------------------------------------------
# SELECTION FUNCTIONS
# ---------------------------------------------------------

if "selected_bores" not in st.session_state:
    st.session_state.selected_bores = []

if "show_legend" not in st.session_state:
    st.session_state.show_legend = True

if "bom_climate_station_id" not in st.session_state:
    st.session_state.bom_climate_station_id = None

if "bore_colour_indexes" not in st.session_state:
    st.session_state.bore_colour_indexes = {}

if "last_processed_click_count" not in st.session_state:
    st.session_state.last_processed_click_count = None

def clear_selection():
    st.session_state.selected_bores = []
    st.session_state.bore_colour_indexes = {}
    st.session_state.last_processed_click_count = None

def select_bore(identifier):
    if identifier in st.session_state.selected_bores:
        return

    used_indexes = set(
        st.session_state.bore_colour_indexes.values()
    )

    available_index = next(
        (
            index
            for index in range(len(selection_colours))
            if index not in used_indexes
        ),
        len(st.session_state.selected_bores)
        % len(selection_colours),
    )

    st.session_state.selected_bores.append(identifier)

    st.session_state.bore_colour_indexes[
        identifier
    ] = available_index

def deselect_bore(identifier):
    if identifier in st.session_state.selected_bores:
        st.session_state.selected_bores.remove(identifier)

    st.session_state.bore_colour_indexes.pop(
        identifier,
        None,
    )

def bore_colour(identifier):
    colour_index = (
        st.session_state.bore_colour_indexes.get(
            identifier,
            0,
        )
    )

    return selection_colours[colour_index]

def bore_display_name(identifier):
    """Return Bore ID plus its name when the source data provides one."""
    if "BORE_NO" not in quality_locations.columns:
        return identifier

    matches = quality_locations.loc[
        quality_locations["BORE_NO"].eq(identifier)
    ]
    if matches.empty:
        return identifier

    name = matches.iloc[0].get("BORE_NAME")
    if pd.notna(name) and str(name).strip():
        return f"{identifier} - {name}"

    return identifier

def selected_badges():
    if not st.session_state.selected_bores:
        return

    badge_html = " ".join(
        (
            '<span style="display:inline-block; '
            'margin:2px 4px 6px 0; '
            'padding:4px 9px; '
            'border-radius:12px; '
            'color:white; '
            f'background:{bore_colour(identifier)["hex"]}; '
            f'font-weight:600;">{html.escape(str(bore_display_name(identifier)))}</span>'
        )
        for identifier in st.session_state.selected_bores
    )

    st.markdown(
        f"**Selected locations:**<br>{badge_html}",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------
# Sidebar options control which part of the map is being explored (named Dashboard Controls), and available features change as a result
# Added BOM Climate data as a dashboard mode, had to be separate because BOM's data is for rainfall and also 
# didn't want to mix existing groundwater data with new BOM data

st.sidebar.header("Dashboard Controls")

mode = st.sidebar.radio(
    "Choose a Dashboard Mode",
    options=[
        "Water-Quality Comparison",
        "Chemical-Threshold Map",
        "Bore Details and Static Comparison",
        "Groundwater-Monitoring Locations",
        "BOM Climate Data",
    ],
)

if st.session_state.get("active_mode") != mode:
    st.session_state.active_mode = mode
    clear_selection()

# Default to our Ti Tree data, which we've assigned to Northern Territory. Can still zoom out and explore other data on the map.
if "last_state_choice" not in st.session_state:
    st.session_state.last_state_choice = "Northern Territory"

if "last_search_result" not in st.session_state:
    st.session_state.last_search_result = None

st.sidebar.subheader("Map location")

state_options = list(AUSTRALIA_STATE_MARKERS.keys())

selected_state = st.sidebar.selectbox(
    "State / Territory",
    options=state_options,
    index=state_options.index(
        st.session_state.last_state_choice
    ),
    key="state_filter",
)

# Can change logic here, currently set to default to Ti Tree (as that's where our data is),
# but assigned to NT. NT is also obviously a territory but it's easier to group it with states under selected_state / australia_state_markers constant. 
if selected_state != st.session_state.last_state_choice:
    st.session_state.last_state_choice = selected_state

    if selected_state == "Northern Territory":
        # Ti Tree remains the default NT focus.
        st.session_state.map_center = default_centre
        st.session_state.map_zoom = 8
    else:
        latitude, longitude, zoom = AUSTRALIA_STATE_MARKERS[
            selected_state
        ]
        st.session_state.map_center = [
            latitude,
            longitude,
        ]
        st.session_state.map_zoom = zoom

search_text = st.sidebar.text_input(
    "Search Locations",
    #e.g. Bore ID, Bore Name, Monitoring Station Name, BOM Station, State, Town
    placeholder="Bore ID, Bore/Station Name, State, Town",
    type="search",
    autocomplete="off"
)

search_query = search_text.strip().lower()

search_types = st.sidebar.multiselect(
    "Search Location Types",
    options=[
        "State / Territory",
        "Town / city",
        "Bore",
        "Monitoring station",
        "BOM station",
    ],
    default=[
        "State / Territory",
        "Town / city",
        "Bore",
        "Monitoring station",
        "BOM station",
    ],
)

search_options = []
search_dataset_matches = {
    "bore_numbers": set(),
    "monitoring_stations": set(),
}

if search_query:
    # General state and town locations are navigation targets on the same map.
    if "State / Territory" in search_types:
        for state, (latitude, longitude, zoom) in AUSTRALIA_STATE_MARKERS.items():
            if search_query in state.lower():
                search_options.append(
                    (
                        f"State: {state}",
                        latitude,
                        longitude,
                        zoom,
                        "navigation",
                    )
                )

    if "Town / city" in search_types:
        for name, state, latitude, longitude in KEY_LOCATIONS:
            if search_query in f"{name} {state}".lower():
                search_options.append(
                    (
                        f"Location: {name} - {state}",
                        latitude,
                        longitude,
                        9,
                        "navigation",
                    )
                )

    if "Bore" in search_types:
        bore_mask = pd.Series(False, index=bores.index)
        for column in ["BORE_NO", "BORE_NAME", "LOCALITY"]:
            if column in bores.columns:
                bore_mask |= bores[column].astype("string").str.contains(
                    search_query,
                    case=False,
                    na=False,
                    regex=False,
                )

        matching_bores = bores.loc[bore_mask]
        search_dataset_matches["bore_numbers"] = set(
            matching_bores["BORE_NO"].dropna().tolist()
        )

        for _, row in matching_bores.head(50).iterrows():
            name = row.get("BORE_NAME")
            name = "" if pd.isna(name) else str(name)
            search_options.append(
                (
                    f"Bore: {row['BORE_NO']} - {name}",
                    float(row["latitude"]),
                    float(row["longitude"]),
                    13,
                    "bore",
                )
            )

    if "Monitoring station" in search_types:
        monitoring_mask = pd.Series(False, index=monitoring.index)
        for column in ["STATION", "STATION_NA"]:
            if column in monitoring.columns:
                monitoring_mask |= monitoring[column].astype("string").str.contains(
                    search_query,
                    case=False,
                    na=False,
                    regex=False,
                )

        matching_monitoring = monitoring.loc[monitoring_mask]
        search_dataset_matches["monitoring_stations"] = set(
            matching_monitoring["STATION"].dropna().tolist()
        )

        for _, row in matching_monitoring.head(50).iterrows():
            name = row.get("STATION_NA")
            name = "" if pd.isna(name) else str(name)
            search_options.append(
                (
                    f"Monitoring station: {row['STATION']} - {name}",
                    float(row["latitude"]),
                    float(row["longitude"]),
                    13,
                    "monitoring",
                )
            )

    if "BOM station" in search_types and not bom_stations.empty:
        bom_mask = (
            bom_stations["Station"].astype("string").str.contains(
                search_query,
                case=False,
                na=False,
                regex=False,
            )
            | bom_stations["StationName"].astype("string").str.contains(
                search_query,
                case=False,
                na=False,
                regex=False,
            )
        )

        for _, row in bom_stations.loc[bom_mask].head(50).iterrows():
            search_options.append(
                (
                    f"BOM Station ID: {row['Station']} - {row['StationName']}",
                    float(row["Latitude"]),
                    float(row["Longitude"]),
                    13,
                    "bom",
                )
            )

search_labels = [item[0] for item in search_options]

if search_labels:
    selected_search = st.sidebar.selectbox(
        "Matching locations",
        options=search_labels,
        key="search_result",
    )

    selected_index = search_labels.index(selected_search)

    if st.session_state.last_search_result != selected_search:
        st.session_state.last_search_result = selected_search
        _, latitude, longitude, zoom, _ = search_options[selected_index]
        st.session_state.map_center = [latitude, longitude]
        st.session_state.map_zoom = zoom
else:
    if search_query:
        st.sidebar.caption("No matching locations.")
    st.session_state.last_search_result = None

show_extent_only = st.sidebar.checkbox(
    "Only show locations within current map extent",
    value=False,
)

st.session_state.show_legend = st.sidebar.checkbox(
    "Show map legend",
    value=st.session_state.show_legend,
)

measurement_name = "Total dissolved solids"
measurement_column = measurements[measurement_name]
minimum_samples = 1
threshold_statistic = "Latest result"
threshold_value = 0.0

if mode in [
    "Water-Quality Comparison",
    "Chemical-Threshold Map",
]:
    measurement_name = st.sidebar.selectbox(
        "Choose a Water-Quality or Chemical Measurement",
        options=list(measurements.keys()),
    )

    measurement_column = measurements[
        measurement_name
    ]

    available_values = int(
        quality[measurement_column].notna().sum()
    )

    st.sidebar.caption(
        f"{available_values:,} usable Ti Tree results"
    )

    if available_values < 20:
        st.sidebar.warning(
            "This measurement has very limited Ti Tree data. "
            "Choose a laboratory measurement for a stronger comparison."
        )

if mode == "Water-Quality Comparison":
    minimum_samples = st.sidebar.slider(
        "Minimum results per displayed bore",
        min_value=1,
        max_value=20,
        value=2,
    )

if mode == "Chemical-Threshold Map":
    threshold_statistic = st.sidebar.selectbox(
        "Value used to colour each bore",
        options=[
            "Latest result",
            "Historical average",
            "Historical maximum",
            "Historical minimum",
        ],
    )

    valid_measurements = quality[
        measurement_column
    ].dropna()

    default_threshold = (
        float(valid_measurements.median())
        if not valid_measurements.empty
        else 0.0
    )

    threshold_step = max(
        abs(default_threshold) / 20,
        0.1,
    )

    threshold_value = st.sidebar.number_input(
        "Threshold value",
        value=default_threshold,
        step=float(threshold_step),
        format="%.2f",
    )

status_filter = []

if mode == "Bore Details and Static Comparison":
    status_options = sorted(
        value
        for value in bores["STATUS"].dropna().unique()
        if value
    )

    status_filter = st.sidebar.multiselect(
        "Bore status",
        options=status_options,
        default=status_options,
    )

if mode == "Groundwater-Monitoring Locations":
    status_options = sorted(
        value
        for value in monitoring["ACTIVE"].dropna().unique()
        if value
    )

    status_filter = st.sidebar.multiselect(
        "Monitoring status",
        options=status_options,
        default=status_options,
    )

if mode == "BOM Climate Data" and not bom_stations.empty:
    st.sidebar.markdown("### BOM Rainfall Data Sample")
    station_options = [
        f"{row['Station']} - {row['StationName']}"
        for _, row in bom_stations.iterrows()
    ]

    # Link the selectbox to the same session_state value as the climate panel - choosing a station will immediately change data. 
    current_station = str(
        st.session_state.bom_climate_station_id
        or bom_stations.iloc[0]["Station"]
    ).zfill(6)
    station_ids = bom_stations["Station"].astype(str).str.zfill(6).tolist()
    station_index = station_ids.index(current_station) if current_station in station_ids else 0

    selected_station_label = st.sidebar.selectbox(
        "BOM Rainfall Station (Select):",
        options=station_options,
        index=station_index,
        key="bom_climate_station_select",
    )
    selected_station_id = selected_station_label.split(" - ", 1)[0].zfill(6)
    if st.session_state.bom_climate_station_id != selected_station_id:
        st.session_state.bom_climate_station_id = selected_station_id

    st.sidebar.caption(
        "The data samples available for each listed station are provided by the Australian Bureau of Meteorology, and are only Daily Rainfall observations (currently)."
    )

if st.sidebar.button(
    "Clear all selected locations",
    use_container_width=True,
):
    clear_selection()
    st.rerun()

# ---------------------------------------------------------
# DISPLAYED LOCATIONS
# ---------------------------------------------------------
# Groundwater modes = bore / station records
# BOM Climate Data = leaves blank, BOM stuff has its own layer. 

if mode == "Water-Quality Comparison":
    measurement_counts = (
        quality.dropna(subset=[measurement_column])
        .groupby("BORE_NO")
        .size()
        .rename("MEASUREMENT_COUNT")
        .reset_index()
    )

    displayed_locations = quality_locations.merge(
        measurement_counts,
        on="BORE_NO",
        how="left",
    )

    displayed_locations["MEASUREMENT_COUNT"] = (
        displayed_locations["MEASUREMENT_COUNT"]
        .fillna(0)
        .astype(int)
    )

    displayed_locations = displayed_locations[
        displayed_locations["MEASUREMENT_COUNT"]
        >= minimum_samples
    ].copy()

    displayed_locations["SELECT_ID"] = (
        displayed_locations["BORE_NO"]
    )

elif mode == "Chemical-Threshold Map":
    measurement_data = quality.dropna(
        subset=[measurement_column]
    ).copy()

    if threshold_statistic == "Latest result":
        threshold_summary = (
            measurement_data.sort_values("SAMPLEDATE")
            .drop_duplicates(
                "BORE_NO",
                keep="last",
            )[
                [
                    "BORE_NO",
                    measurement_column,
                    "SAMPLEDATE",
                ]
            ]
            .rename(
                columns={
                    measurement_column: "MAP_VALUE",
                    "SAMPLEDATE": "MAP_DATE",
                }
            )
        )

    else:
        aggregation = {
            "Historical average": "mean",
            "Historical maximum": "max",
            "Historical minimum": "min",
        }[threshold_statistic]

        threshold_summary = (
            measurement_data.groupby(
                "BORE_NO",
                as_index=False,
            )[measurement_column]
            .agg(aggregation)
            .rename(
                columns={
                    measurement_column: "MAP_VALUE"
                }
            )
        )

        threshold_summary["MAP_DATE"] = pd.NaT

    displayed_locations = quality_locations.merge(
        threshold_summary,
        on="BORE_NO",
        how="left",
    )

    displayed_locations["SELECT_ID"] = (
        displayed_locations["BORE_NO"]
    )

elif mode == "Bore Details and Static Comparison":
    displayed_locations = bores[
        bores["STATUS"].isin(status_filter)
    ].copy()

    displayed_locations["SELECT_ID"] = (
        displayed_locations["BORE_NO"]
    )

elif mode == "BOM Climate Data":
    # BOM stations are rendered by their own map layer below. Groundwater stuff will not be shown or be available to select to compare.
    displayed_locations = pd.DataFrame(
        columns=["SELECT_ID", "latitude", "longitude"]
    )

else:
    displayed_locations = monitoring[
        monitoring["ACTIVE"].isin(status_filter)
    ].copy()

    displayed_locations["SELECT_ID"] = (
        displayed_locations["STATION"]
    )

# Search filters the active groundwater dataset only when the selected search types actually describe that dataset. 
# Other types are markers for the map like state, town/city, station etc
if search_query:
    matching_ids = set()

    if mode in [
        "Water-Quality Comparison",
        "Chemical-Threshold Map",
        "Bore Details and Static Comparison",
    ] and "Bore" in search_types:
        matching_ids.update(search_dataset_matches["bore_numbers"])

    if mode == "Groundwater-Monitoring Locations" and "Monitoring station" in search_types:
        matching_ids.update(search_dataset_matches["monitoring_stations"])

    if matching_ids:
        displayed_locations = displayed_locations[
            displayed_locations["SELECT_ID"].isin(matching_ids)
        ].copy()

# Re-use the bounds from previous map rendering, the viewport is not reset using these bounds though.
if (
    show_extent_only
    and st.session_state.map_bounds
):
    bounds = st.session_state.map_bounds

    displayed_locations = displayed_locations[
        displayed_locations["latitude"].between(
            bounds["south"],
            bounds["north"],
        )
        & displayed_locations["longitude"].between(
            bounds["west"],
            bounds["east"],
        )
    ].copy()

visible_identifiers = set(
    displayed_locations["SELECT_ID"].tolist()
)

for selected_identifier in list(
    st.session_state.selected_bores
):
    if selected_identifier not in visible_identifiers:
        deselect_bore(selected_identifier)

# ---------------------------------------------------------
# SUMMARY METRICS
# ---------------------------------------------------------

metric1, metric2, metric3, metric4 = st.columns(4)

if mode == "Water-Quality Comparison":
    metric1.metric(
        "Displayed bores",
        f"{len(displayed_locations):,}",
    )

    metric2.metric(
        "Usable results",
        f"{quality[measurement_column].notna().sum():,}",
    )

    metric3.metric(
        "Historical period",
        "1936–2011",
    )

    metric4.metric(
        "Selected",
        len(st.session_state.selected_bores),
    )

elif mode == "Chemical-Threshold Map":
    above_count = int(
        (
            displayed_locations["MAP_VALUE"]
            > threshold_value
        ).sum()
    )

    below_count = int(
        (
            displayed_locations["MAP_VALUE"]
            <= threshold_value
        ).sum()
    )

    missing_count = int(
        displayed_locations["MAP_VALUE"].isna().sum()
    )

    metric1.metric(
        "Above threshold",
        f"{above_count:,}",
    )

    metric2.metric(
        "At or below",
        f"{below_count:,}",
    )

    metric3.metric(
        "No result",
        f"{missing_count:,}",
    )

    metric4.metric(
        "Selected",
        len(st.session_state.selected_bores),
    )

elif mode == "Bore Details and Static Comparison":
    metric1.metric(
        "Displayed bores",
        f"{len(displayed_locations):,}",
    )

    metric2.metric(
        "With water level",
        f"{displayed_locations['WATERLEVEL'].notna().sum():,}",
    )

    metric3.metric(
        "With yield",
        f"{displayed_locations['YIELD'].notna().sum():,}",
    )

    metric4.metric(
        "Selected",
        len(st.session_state.selected_bores),
    )

# Add some summary metrics for the BOM climate data. Number of data files, the source data type, station info, etc.
elif mode == "BOM Climate Data":
    metric1.metric("BOM Stations Available", f"{len(bom_stations):,}")
    metric2.metric("Rainfall Data Files", f"{bom_stations['DataFile'].notna().sum():,}")
    metric3.metric("Source", "BOM Daily Rainfall")
    metric4.metric("Selected Station", st.session_state.bom_climate_station_id or "-")

else:
    current_count = int(
        (
            displayed_locations["ACTIVE"]
            == "Current"
        ).sum()
    )

    metric1.metric(
        "Monitoring locations",
        f"{len(displayed_locations):,}",
    )

    metric2.metric(
        "Currently active",
        f"{current_count:,}",
    )

    metric3.metric(
        "Location data only",
        "No level series",
    )

    metric4.metric(
        "Selected",
        len(st.session_state.selected_bores),
    )

# ---------------------------------------------------------
# MAP FUNCTIONS
# ---------------------------------------------------------

def safe_text(value, fallback="Not recorded"):
    if pd.isna(value) or str(value).strip() == "":
        return fallback
    return str(value)


def formatted_number(value, suffix=""):
    if pd.isna(value):
        return "Not recorded"
    return f"{float(value):,.2f}{suffix}"


def add_aquifer_layers(water_map):
    folium.GeoJson(
        salinity,
        name="Salinity zones",
        show=True,
        style_function=lambda feature: {
            "color": "#d97706",
            "weight": 1,
            "fillColor": "#fbbf24",
            "fillOpacity": 0.22,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "ACTTDS_DES",
                "NOTES",
            ],
            aliases=[
                "Classification:",
                "Description:",
            ],
        ),
    ).add_to(water_map)

    folium.GeoJson(
        aquifer,
        name="Aquifer thickness",
        show=False,
        style_function=lambda feature: {
            "color": "#0891b2",
            "weight": 1,
            "fillColor": "#67e8f9",
            "fillOpacity": 0.22,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["AQUIFER_TH"],
            aliases=["Aquifer thickness:"],
        ),
    ).add_to(water_map)

    folium.GeoJson(
        water_depth,
        name="Depth to groundwater",
        show=False,
        style_function=lambda feature: {
            "color": "#2563eb",
            "weight": 1,
            "fillColor": "#60a5fa",
            "fillOpacity": 0.18,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["DEPTH_TO"],
            aliases=["Depth to groundwater:"],
        ),
    ).add_to(water_map)

    folium.GeoJson(
        contours,
        name="Groundwater elevation contours",
        show=False,
        style_function=lambda feature: {
            "color": "#7c3aed",
            "weight": 2,
            "fillOpacity": 0,
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["DEPTH_AHD"],
            aliases=["Groundwater elevation:"],
        ),
    ).add_to(water_map)

    folium.GeoJson(
        boundary,
        name="Ti Tree Basin boundary",
        show=True,
        style_function=lambda feature: {
            "color": "#172554",
            "weight": 4,
            "fillOpacity": 0,
        },
    ).add_to(water_map)

def marker_details(row):
    identifier = row["SELECT_ID"]

    selected = (
        identifier
        in st.session_state.selected_bores
    )

    selection_text = (
        "Selected - click again to remove"
        if selected
        else "Click to select"
    )

    if selected:
        marker_colour = bore_colour(
            identifier
        )["marker"]

    elif mode == "Chemical-Threshold Map":
        if pd.isna(row.get("MAP_VALUE")):
            marker_colour = "gray"

        elif row["MAP_VALUE"] > threshold_value:
            marker_colour = "red"

        else:
            marker_colour = "blue"

    elif mode == "Groundwater-Monitoring Locations":
        marker_colour = (
            "green"
            if row["ACTIVE"] == "Current"
            else "gray"
        )

    else:
        marker_colour = "blue"

    if mode in [
        "Water-Quality Comparison",
        "Chemical-Threshold Map",
    ]:
        first_date = (
            row["FIRST_SAMPLE"].strftime("%d %b %Y")
            if pd.notna(row["FIRST_SAMPLE"])
            else "Unknown"
        )

        latest_date = (
            row["LATEST_SAMPLE"].strftime("%d %b %Y")
            if pd.notna(row["LATEST_SAMPLE"])
            else "Unknown"
        )

        extra = (
            f"Samples: {int(row['SAMPLE_COUNT'])}<br>"
            f"First sample: {first_date}<br>"
            f"Latest sample: {latest_date}"
        )

        if mode == "Chemical-Threshold Map":
            value_text = formatted_number(
                row.get("MAP_VALUE")
            )

            extra += (
                f"<br><strong>{threshold_statistic}:"
                f"</strong> {value_text}"
            )

    elif mode == "Bore Details and Static Comparison":
        extra = (
            f"Name: {safe_text(row.get('BORE_NAME'))}<br>"
            f"Status: {safe_text(row.get('STATUS'))}<br>"
            f"Purpose: {safe_text(row.get('PURPOSE'))}<br>"
            f"Water level: "
            f"{formatted_number(row.get('WATERLEVEL'), ' m')}<br>"
            f"Yield: "
            f"{formatted_number(row.get('YIELD'), ' L/s')}"
        )

    else:
        commence = (
            row["COMMENCE"].strftime("%d %b %Y")
            if pd.notna(row["COMMENCE"])
            else "Unknown"
        )

        extra = (
            f"Name: {safe_text(row.get('STATION_NA'))}<br>"
            f"Status: {safe_text(row.get('ACTIVE'))}<br>"
            f"Type: {safe_text(row.get('MONITOR_TY'))}<br>"
            f"Monitoring commenced: {commence}"
        )

    popup = f"""
    <div style="width:260px;">
        <strong>{bore_display_name(identifier)}</strong><br><br>
        {extra}<br><br>
        <strong>{selection_text}</strong>
    </div>
    """

    return (
        marker_colour,
        selection_text,
        popup,
    )

# ---------------------------------------------------------
# CREATE MAP AND PANEL
# ---------------------------------------------------------

map_column, panel_column = st.columns(
    [1.15, 1],
    gap="large",
)

# Group everything that needs to be rerun / refreshed fairly consistently so it can update independently, under an if / else block.
# Unfortunately this means duplicate of nearly whole main code, but worth it for the results - no more buggy map refreshing with map extent option unchecked.

if hasattr(st, "fragment"):
    @st.fragment
    def render_interactive_map():
        st.subheader("Interactive Australia Map")

        if mode == "Chemical-Threshold Map":
            st.caption(
                "Red pins are above the threshold, "
                "blue pins are at or below it, and "
                "grey pins have no result. Selected "
                "pins use unique colours."
            )

            with st.container(border=True):
                st.markdown("### Pin colour legend")
                st.markdown("🔴 **Above selected threshold**")
                st.markdown("🔵 **Equal to or below threshold**")
                st.markdown("⚫ **No chemical result available**")
            
            

        elif mode == "Groundwater-Monitoring Locations":
            st.caption(
                "Green pins are current monitoring locations "
                "and grey pins are not current. The supplied "
                "file contains locations and portal links."
            )

            with st.container(border=True):
                st.markdown("### Monitoring pin legend")
                st.markdown("🟢 **Current monitoring location**")
                st.markdown(
                    "⚫ **Monitoring location not currently active**"
                )
                st.markdown(
                    "🟠 🟣 ⚫ **Selected monitoring locations**"
                )

        else:
            st.caption(
                "Click a bore marker / pin to select it, and click the "
                "coloured pin again to remove it from comparison."
            )

        water_map = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.map_zoom,
            tiles=None,
            control_scale=True,
        ) 

        # Change show to True to set this map type to default, set False otherwise. Need to have one
        # map type selected by default so at least one has to be show = True.
        folium.TileLayer(
            tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            name="Terrain Map",
            attr=(
                "Map data © OpenStreetMap contributors, "
                "SRTM | Map style © OpenTopoMap"
            ),
            overlay=False,
            control=True,
            show=True,
            max_zoom=17,
        ).add_to(water_map)

        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ),
            name="Satellite Map",
            attr="Tiles © Esri",
            overlay=False,
            control=True,
            show=False,
        ).add_to(water_map)

        folium.TileLayer(
            tiles="OpenStreetMap",
            name="OpenStreetMap",
            overlay=False,
            control=True,
            show=False,
        ).add_to(water_map)

        add_aquifer_layers(water_map)

        # State, key-area and BOM markers use this same map.
        focus_layer = folium.FeatureGroup(
            name="Australian locations",
            show=True,
        )

        for state_name, (
            latitude,
            longitude,
            _,
        ) in AUSTRALIA_STATE_MARKERS.items():
            folium.Marker(
                location=[latitude, longitude],
                tooltip=f"State: {state_name}",
                popup=folium.Popup(
                    f"<strong>{html.escape(state_name)}</strong>",
                    max_width=250,
                ),
                icon=folium.Icon(
                    color="green",
                    #icon="map-marker",     # Can use map-marker for original marker, will use Flag for now
                    icon="flag",      
                    prefix="fa",
                ),
            ).add_to(focus_layer)

        for name, state, latitude, longitude in KEY_LOCATIONS:
            folium.CircleMarker(
                location=[latitude, longitude],
                radius=4,
                tooltip=f"{name} - {state}",
                popup=folium.Popup(
                    f"<strong>{html.escape(name)}</strong><br>"
                    f"{html.escape(state)}",
                    max_width=250,
                ),
                color="#444444",
                fill=True,
                fill_opacity=0.85,
            ).add_to(focus_layer)

        focus_layer.add_to(water_map)

        # Keep the BOM markers on the map, separate from groundwater ones so they can be hidden independently
        bom_layer = folium.FeatureGroup(
            name="BOM Stations",
            show=not bom_stations.empty,
        )

        for _, station in bom_stations.iterrows():
            station_id = str(station["Station"])
            station_name = str(station["StationName"])
            popup_html = (
                f"<strong>{html.escape(station_name)}</strong><br><br>"
                f"<strong>BOM Station ID:</strong> {html.escape(station_id)}<br>"
                f"<strong>State:</strong> {html.escape(str(station['State']))}<br>"
                f"<strong>Latitude:</strong> {station['Latitude']}<br>"
                f"<strong>Longitude:</strong> {station['Longitude']}<br>"
                f"<strong>Sample variable:</strong> Daily Rainfall"
            )
            folium.CircleMarker(
                location=[station["Latitude"], station["Longitude"]],
                radius=5,
                tooltip=f"BOM: {station_id} - {station_name}",
                popup=folium.Popup(popup_html, max_width=300),
                color="#005a9c",
                fill=True,
                fill_opacity=0.9,
            ).add_to(bom_layer)

        bom_layer.add_to(water_map)

        marker_layer = folium.FeatureGroup(
            name="Displayed locations"
        )

        for _, location in displayed_locations.iterrows():
            identifier = location["SELECT_ID"]

            (
                marker_colour,
                selection_text,
                popup,
            ) = marker_details(location)

            icon_name = (
                "eye"
                if mode == "Groundwater-Monitoring Locations"
                else "tint"
            )

            folium.Marker(
                location=[
                    location["latitude"],
                    location["longitude"],
                ],
                tooltip=(
                    f"{bore_display_name(identifier)} - {selection_text}"
                ),
                popup=folium.Popup(
                    popup,
                    max_width=290,
                ),
                icon=folium.Icon(
                    color=marker_colour,
                    icon=icon_name,
                    prefix="fa",
                ),
            ).add_to(marker_layer)

        layer_control = folium.LayerControl(
            position="bottomright",
            collapsed=True,
        )

        if st.session_state.show_legend:
            legend_items = [
                ("#3CA1CF", "Bore / Groundwater Marker"),
                ("green", "State / Territory Marker"),
                ("#444444", "Key Town / City Marker"),
                ("#005a9c", "BOM Station"),
            ]
            legend_html = "".join(
                f'<div style="margin:3px 0;"><span style="display:inline-block;width:13px;height:13px;'
                f'border-radius:50%;background:{colour};margin-right:7px;"></span>{label}</div>'
                for colour, label in legend_items
            )
            st.markdown(
                f'<div style="padding:8px 12px;border:1px solid #ddd;border-radius:6px;'
                f'margin-bottom:8px;background:white;"><strong>Legend</strong>{legend_html}</div>',
                unsafe_allow_html=True,
            )

        # Only get streamlit-folium to send marker clicks back to Streamlit, leave pan/zoom clicks inside Leaflet so we prevent a full dashboard rerun every time.
        returned_map_objects = [
            "last_object_clicked",
            "last_object_clicked_count",
        ]
        if show_extent_only:
            returned_map_objects.append("bounds")

        map_result = st_folium(
            water_map,
            height=700,
            key=f"ti_tree_map_{mode}",
            use_container_width=True,
            feature_group_to_add=marker_layer,
            layer_control=layer_control,
            returned_objects=returned_map_objects,
        )

        if show_extent_only:
            map_bounds = map_result.get("bounds")
            if isinstance(map_bounds, dict):
                southwest = map_bounds.get("_southWest", {})
                northeast = map_bounds.get("_northEast", {})
                if all(
                    key in southwest and key in northeast
                    for key in ("lat", "lng")
                ):
                    new_bounds = {
                        "south": southwest["lat"],
                        "west": southwest["lng"],
                        "north": northeast["lat"],
                        "east": northeast["lng"],
                    }
                    if new_bounds != st.session_state.map_bounds:
                        st.session_state.map_bounds = new_bounds
                        st.rerun()

        clicked_location = map_result.get(
            "last_object_clicked"
        )

        clicked_count = map_result.get(
            "last_object_clicked_count"
        )

        if (
            clicked_location
            and clicked_count is not None
            and clicked_count
            != st.session_state.last_processed_click_count
        ):
            st.session_state.last_processed_click_count = (
                clicked_count
            )

            clicked_latitude = clicked_location.get("lat")
            clicked_longitude = clicked_location.get("lng")

            if (
                clicked_latitude is not None
                and clicked_longitude is not None
            ):
                # Clicking a state or key town marker moves the map to that area with the previously set zoom levels
                focus_targets = []
                for state_name, (latitude, longitude, zoom) in AUSTRALIA_STATE_MARKERS.items():
                    focus_targets.append((latitude, longitude, zoom))
                for name, state_name, latitude, longitude in KEY_LOCATIONS:
                    focus_targets.append((latitude, longitude, 9))

                nearest_focus = None
                nearest_focus_distance = None
                for latitude, longitude, zoom in focus_targets:
                    distance = (
                        (latitude - clicked_latitude) ** 2
                        + (longitude - clicked_longitude) ** 2
                    )
                    if nearest_focus_distance is None or distance < nearest_focus_distance:
                        nearest_focus_distance = distance
                        nearest_focus = (latitude, longitude, zoom)

                if nearest_focus is not None and nearest_focus_distance < 0.000001:
                    latitude, longitude, zoom = nearest_focus
                    st.session_state.map_center = [latitude, longitude]
                    st.session_state.map_zoom = zoom
                    st.session_state.map_bounds = None
                    st.rerun()

                # In BOM Climate Data mode, clicking a BOM marker selects the station for the climate panel without changing the map view.
                # Need to recheck this, since I added the rainfall sample dropdown selector, this doesn't work like it previously did. 
                if mode == "BOM Climate Data" and not bom_stations.empty:
                    bom_distances = (
                        (bom_stations["Latitude"] - clicked_latitude) ** 2
                        + (bom_stations["Longitude"] - clicked_longitude) ** 2
                    )
                    bom_index = bom_distances.idxmin()
                    if bom_distances.loc[bom_index] < 0.000001:
                        st.session_state.bom_climate_station_id = str(
                            bom_stations.loc[bom_index, "Station"]
                        )
                        st.rerun()

            if (
                clicked_latitude is not None
                and clicked_longitude is not None
                and not displayed_locations.empty
            ):
                distances = (
                    (
                        displayed_locations["latitude"]
                        - clicked_latitude
                    )
                    ** 2
                    + (
                        displayed_locations["longitude"]
                        - clicked_longitude
                    )
                    ** 2
                )

                nearest_index = distances.idxmin()

                if distances.loc[nearest_index] < 0.000001:
                    clicked_identifier = (
                        displayed_locations.loc[
                            nearest_index,
                            "SELECT_ID",
                        ]
                    )

                    if (
                        clicked_identifier
                        in st.session_state.selected_bores
                    ):
                        deselect_bore(clicked_identifier)

                    else:
                        select_bore(clicked_identifier)

                    st.rerun()

    # ---------------------------------------------------------
    # WATER-QUALITY GRAPH
    # ---------------------------------------------------------

    def render_quality_panel():
        st.subheader(
            "Historical Water-Quality Comparison"
        )

        st.caption(
            "The graph updates automatically. Pin colours "
            "and graph-line colours match."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select one or more bore pins on the map."
            )
            return

        selected_badges()

        valid_dates = quality["SAMPLEDATE"].dropna()

        earliest_date = valid_dates.min().date()
        latest_date = valid_dates.max().date()

        date_range = st.date_input(
            "Graph date range",
            value=(
                earliest_date,
                latest_date,
            ),
            min_value=earliest_date,
            max_value=latest_date,
            key=(
                f"date_range_{mode}_"
                f"{measurement_column}"
            ),
        )

        graph_data = quality[
            quality["BORE_NO"].isin(
                st.session_state.selected_bores
            )
        ].dropna(
            subset=[measurement_column]
        ).copy()

        if (
            isinstance(date_range, (tuple, list))
            and len(date_range) == 2
        ):
            graph_data = graph_data[
                graph_data["SAMPLEDATE"].between(
                    pd.Timestamp(date_range[0]),
                    pd.Timestamp(date_range[1]),
                )
            ]

        graph_data = (
            graph_data.groupby(
                [
                    "BORE_NO",
                    "SAMPLEDATE",
                ],
                as_index=False,
            )[measurement_column]
            .mean()
            .sort_values(
                [
                    "BORE_NO",
                    "SAMPLEDATE",
                ]
            )
        )

        if graph_data.empty:
            st.warning(
                f"The selected bores have no "
                f"{measurement_name} results in this period."
            )
            return

        figure = go.Figure()

        for identifier in st.session_state.selected_bores:
            bore_data = graph_data[
                graph_data["BORE_NO"] == identifier
            ]

            if bore_data.empty:
                continue

            line_colour = bore_colour(
                identifier
            )["hex"]

            figure.add_trace(
                go.Scatter(
                    x=bore_data["SAMPLEDATE"],
                    y=bore_data[measurement_column],
                    mode="lines+markers",
                    name=bore_display_name(identifier),
                    line={
                        "color": line_colour,
                        "width": 3,
                    },
                    marker={
                        "color": line_colour,
                        "size": 8,
                    },
                    hovertemplate=(
                        f"{bore_display_name(identifier)}<br>"
                        "%{x|%d %b %Y}<br>"
                        f"{measurement_name}: "
                        "%{y:,.2f}<extra></extra>"
                    ),
                )
            )

        figure.update_layout(
            title=f"{measurement_name} comparison",
            hovermode="x unified",
            height=540,
            legend_title_text="Bore",
            margin={
                "l": 40,
                "r": 20,
                "t": 70,
                "b": 100,
            },
            legend={
                "orientation": "h",
                "yanchor": "top",
                "y": -0.20,
                "xanchor": "center",
                "x": 0.5,
            },
        )

        figure.update_xaxes(
            title_text="Sample date"
        )

        figure.update_yaxes(
            title_text=(
                f"{measurement_name} "
                "(source dataset units)"
            )
        )

        filename = (
            f"ti_tree_"
            f"{measurement_column.lower()}_comparison"
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": filename,
                    "width": 1400,
                    "height": 800,
                    "scale": 2,
                },
            },
        )

        st.caption(
            "Download PNG using the camera icon "
            "in the graph toolbar."
        )

        download1, download2 = st.columns(2)

        with download1:
            st.download_button(
                "Download interactive graph",
                data=figure.to_html(
                    full_html=True,
                    include_plotlyjs="cdn",
                ),
                file_name=f"{filename}.html",
                mime="text/html",
                use_container_width=True,
            )

        with download2:
            st.download_button(
                "Download graph data (CSV)",
                data=graph_data.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name=f"{filename}_data.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with st.expander(
            "Measurements used in the graph"
        ):
            st.dataframe(
                graph_data[
                    [
                        "BORE_NO",
                        "SAMPLEDATE",
                        measurement_column,
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    # ---------------------------------------------------------
    # BORE DETAILS
    # ---------------------------------------------------------

    def zone_value(point, layer, field):
        matches = layer[
            layer.geometry.covers(point)
        ]

        if matches.empty:
            return "Not mapped at this location"

        return safe_text(
            matches.iloc[0].get(field)
        )

    def nearest_contour(point):
        point_projected = gpd.GeoSeries(
            [point],
            crs="EPSG:4326",
        ).to_crs(
            epsg=28353
        ).iloc[0]

        contours_projected = contours.to_crs(
            epsg=28353
        )

        nearest_index = (
            contours_projected.geometry
            .distance(point_projected)
            .idxmin()
        )

        return safe_text(
            contours.loc[
                nearest_index
            ].get("DEPTH_AHD")
        )

    def render_bore_details_panel():
        st.subheader(
            "Bore Details and Static Comparison"
        )

        st.caption(
            "These are individual recorded bore attributes, "
            "not a groundwater-level time series."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select one or more bore pins on the map."
            )
            return

        selected_badges()

        selected_data = bores[
            bores["BORE_NO"].isin(
                st.session_state.selected_bores
            )
        ].copy()

        metric_options = {
            "Recorded water level": (
                "WATERLEVEL",
                "m",
            ),
            "Bore yield": (
                "YIELD",
                "L/s",
            ),
            "Completion depth": (
                "COMPLDEPTH",
                "m",
            ),
            "Drilling depth": (
                "DRILLDEPTH",
                "m",
            ),
        }

        metric_name = st.selectbox(
            "Static bore field to compare",
            options=list(metric_options),
        )

        metric_column, metric_unit = (
            metric_options[metric_name]
        )

        chart_data = selected_data.dropna(
            subset=[metric_column]
        )

        if chart_data.empty:
            st.warning(
                "The selected bores have no recorded "
                f"{metric_name.lower()}."
            )

        else:
            figure = go.Figure()

            for _, row in chart_data.iterrows():
                identifier = row["BORE_NO"]

                figure.add_trace(
                    go.Bar(
                        x=[identifier],
                        y=[row[metric_column]],
                        name=bore_display_name(identifier),
                        marker_color=bore_colour(
                            identifier
                        )["hex"],
                        hovertemplate=(
                            f"{bore_display_name(identifier)}<br>"
                            f"{metric_name}: "
                            f"%{{y:,.2f}} "
                            f"{metric_unit}"
                            "<extra></extra>"
                        ),
                    )
                )

            figure.update_layout(
                title=f"{metric_name} comparison",
                height=440,
                showlegend=False,
                xaxis_title="Bore",
                yaxis_title=(
                    f"{metric_name} ({metric_unit})"
                ),
                margin={
                    "l": 40,
                    "r": 20,
                    "t": 70,
                    "b": 60,
                },
            )

            st.plotly_chart(
                figure,
                use_container_width=True,
                config={
                    "displaylogo": False,
                    "toImageButtonOptions": {
                        "format": "png",
                        "filename": (
                            f"ti_tree_"
                            f"{metric_column.lower()}"
                        ),
                        "width": 1200,
                        "height": 700,
                        "scale": 2,
                    },
                },
            )

        table_rows = []

        for _, row in selected_data.iterrows():
            table_rows.append(
                {
                    "Bore": row["BORE_NO"],
                    "Name": safe_text(
                        row["BORE_NAME"]
                    ),
                    "Status": safe_text(
                        row["STATUS"]
                    ),
                    "Purpose": safe_text(
                        row["PURPOSE"]
                    ),
                    "Water level (m)": (
                        row["WATERLEVEL"]
                    ),
                    "Yield (L/s)": row["YIELD"],
                    "Completion depth (m)": (
                        row["COMPLDEPTH"]
                    ),
                    "Drilling depth (m)": (
                        row["DRILLDEPTH"]
                    ),
                    "Salinity zone": zone_value(
                        row.geometry,
                        salinity,
                        "NOTES",
                    ),
                    "Aquifer thickness": zone_value(
                        row.geometry,
                        aquifer,
                        "AQUIFER_TH",
                    ),
                    "Mapped depth to groundwater": (
                        zone_value(
                            row.geometry,
                            water_depth,
                            "DEPTH_TO",
                        )
                    ),
                    "Nearest groundwater contour": (
                        nearest_contour(
                            row.geometry
                        )
                    ),
                }
            )

        details_table = pd.DataFrame(table_rows)

        with st.expander(
            "Selected bore details",
            expanded=True,
        ):
            st.dataframe(
                details_table,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "Download selected bore details (CSV)",
            data=details_table.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "ti_tree_selected_bore_details.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    # ---------------------------------------------------------
    # MONITORING LOCATIONS
    # ---------------------------------------------------------

    def render_monitoring_panel():
        st.subheader(
            "Groundwater-Monitoring Locations"
        )

        st.caption(
            "The supplied layer contains station details "
            "and NT Water Data Portal links, but not the "
            "historical groundwater-level measurements."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select a monitoring-location pin on the map."
            )
            return

        selected_badges()

        selected_data = monitoring[
            monitoring["STATION"].isin(
                st.session_state.selected_bores
            )
        ].copy()

        for _, station in selected_data.iterrows():
            with st.container(border=True):
                st.markdown(
                    f"#### {station['STATION']}"
                )

                st.write(
                    "**Name:** "
                    f"{safe_text(station['STATION_NA'])}"
                )

                st.write(
                    "**Status:** "
                    f"{safe_text(station['ACTIVE'])}"
                )

                st.write(
                    "**Type:** "
                    f"{safe_text(station['MONITOR_TY'])}"
                )

                commence = (
                    station["COMMENCE"].strftime(
                        "%d %B %Y"
                    )
                    if pd.notna(station["COMMENCE"])
                    else "Not recorded"
                )

                cease = (
                    station["CEASE"].strftime(
                        "%d %B %Y"
                    )
                    if pd.notna(station["CEASE"])
                    else "Not recorded"
                )

                st.write(
                    f"**Monitoring commenced:** {commence}"
                )

                st.write(
                    f"**Monitoring ceased:** {cease}"
                )

                portal_url = station.get("WATER_DATA")

                if (
                    pd.notna(portal_url)
                    and str(portal_url).startswith("http")
                ):
                    st.link_button(
                        "Open station in NT Water Data Portal",
                        str(portal_url),
                        use_container_width=True,
                    )

        download_columns = [
            "STATION",
            "STATION_NA",
            "MONITOR_TY",
            "ACTIVE",
            "COMMENCE",
            "CEASE",
            "WATER_DATA",
            "latitude",
            "longitude",
        ]

        st.download_button(
            "Download selected monitoring locations (CSV)",
            data=selected_data[
                download_columns
            ].to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "ti_tree_monitoring_locations.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

else:
    def render_interactive_map():
        st.subheader("Interactive Australia Map")

        if mode == "Chemical-Threshold Map":
            st.caption(
                "Red pins are above the threshold, "
                "blue pins are at or below it, and "
                "grey pins have no result. Selected "
                "pins use unique colours."
            )

            with st.container(border=True):
                st.markdown("### Pin colour legend")
                st.markdown("🔴 **Above selected threshold**")
                st.markdown("🔵 **Equal to or below threshold**")
                st.markdown("⚫ **No chemical result available**")
            
            

        elif mode == "Groundwater-Monitoring Locations":
            st.caption(
                "Green pins are current monitoring locations "
                "and grey pins are not current. The supplied "
                "file contains locations and portal links."
            )

            with st.container(border=True):
                st.markdown("### Monitoring pin legend")
                st.markdown("🟢 **Current monitoring location**")
                st.markdown(
                    "⚫ **Monitoring location not currently active**"
                )
                st.markdown(
                    "🟠 🟣 ⚫ **Selected monitoring locations**"
                )

        else:
            st.caption(
                "Click a pin to select it. Click the "
                "coloured pin again to remove it."
            )

        water_map = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.map_zoom,
            tiles=None,
            control_scale=True,
        )

        folium.TileLayer(
            tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            name="Terrain Map",
            attr=(
                "Map data © OpenStreetMap contributors, "
                "SRTM | Map style © OpenTopoMap"
            ),
            overlay=False,
            control=True,
            show=True,
            max_zoom=17,
        ).add_to(water_map)

        folium.TileLayer(
            tiles=(
                "https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"
            ),
            name="Satellite Map",
            attr="Tiles © Esri",
            overlay=False,
            control=True,
            show=False,
        ).add_to(water_map)

        folium.TileLayer(
            tiles="OpenStreetMap",
            name="OpenStreetMap",
            overlay=False,
            control=True,
            show=False,
        ).add_to(water_map)

        add_aquifer_layers(water_map)

        # State, key-area and BOM markers use this same map.
        focus_layer = folium.FeatureGroup(
            name="Australian locations",
            show=True,
        )

        for state_name, (
            latitude,
            longitude,
            _,
        ) in AUSTRALIA_STATE_MARKERS.items():
            folium.Marker(
                location=[latitude, longitude],
                tooltip=f"State: {state_name}",
                popup=folium.Popup(
                    f"<strong>{html.escape(state_name)}</strong>",
                    max_width=250,
                ),
                icon=folium.Icon(
                    color="green",
                    #icon="map-marker",     # Can use map-marker for original marker, will use Flag for now
                    icon="flag",      
                    prefix="fa",
                ),
            ).add_to(focus_layer)

        for name, state, latitude, longitude in KEY_LOCATIONS:
            folium.CircleMarker(
                location=[latitude, longitude],
                radius=4,
                tooltip=f"{name} - {state}",
                popup=folium.Popup(
                    f"<strong>{html.escape(name)}</strong><br>"
                    f"{html.escape(state)}",
                    max_width=250,
                ),
                color="#444444",
                fill=True,
                fill_opacity=0.85,
            ).add_to(focus_layer)

        focus_layer.add_to(water_map)

        # BOM markers stay on the map, but they are separate from other markers and can be hidden independently using grid layers.
        bom_layer = folium.FeatureGroup(
            name="BOM Stations",
            show=not bom_stations.empty,
        )

        for _, station in bom_stations.iterrows():
            station_id = str(station["Station"])
            station_name = str(station["StationName"])
            popup_html = (
                f"<strong>{html.escape(station_name)}</strong><br><br>"
                f"<strong>BOM Station:</strong> {html.escape(station_id)}<br>"
                f"<strong>State:</strong> {html.escape(str(station['State']))}<br>"
                f"<strong>Latitude:</strong> {station['Latitude']}<br>"
                f"<strong>Longitude:</strong> {station['Longitude']}<br>"
                f"<strong>Sample variable:</strong> Daily Rainfall"
            )
            folium.CircleMarker(
                location=[station["Latitude"], station["Longitude"]],
                radius=5,
                tooltip=f"BOM: {station_id} - {station_name}",
                popup=folium.Popup(popup_html, max_width=300),
                color="#005a9c",
                fill=True,
                fill_opacity=0.9,
            ).add_to(bom_layer)

        bom_layer.add_to(water_map)

        marker_layer = folium.FeatureGroup(
            name="Displayed locations"
        )

        for _, location in displayed_locations.iterrows():
            identifier = location["SELECT_ID"]

            (
                marker_colour,
                selection_text,
                popup,
            ) = marker_details(location)

            icon_name = (
                "eye"
                if mode == "Groundwater-Monitoring Locations"
                else "tint"
            )

            folium.Marker(
                location=[
                    location["latitude"],
                    location["longitude"],
                ],
                tooltip=(
                    f"{bore_display_name(identifier)} - {selection_text}"
                ),
                popup=folium.Popup(
                    popup,
                    max_width=290,
                ),
                icon=folium.Icon(
                    color=marker_colour,
                    icon=icon_name,
                    prefix="fa",
                ),
            ).add_to(marker_layer)

        layer_control = folium.LayerControl(
            position="bottomright",
            collapsed=True,
        )

        if st.session_state.show_legend:
            legend_items = [
                ("#3CA1CF", "Bore / Groundwater Marker"),
                ("green", "State / Territory Marker"),
                ("#444444", "Key Town / City Marker"),
                ("#005a9c", "BOM Station"),
            ]
            legend_html = "".join(
                f'<div style="margin:3px 0;"><span style="display:inline-block;width:13px;height:13px;'
                f'border-radius:50%;background:{colour};margin-right:7px;"></span>{label}</div>'
                for colour, label in legend_items
            )
            st.markdown(
                f'<div style="padding:8px 12px;border:1px solid #ddd;border-radius:6px;'
                f'margin-bottom:8px;background:white;"><strong>Legend</strong>{legend_html}</div>',
                unsafe_allow_html=True,
            )

        # Only get streamlit-folium to send marker clicks back to Streamlit, pan/zoom clicks stay inside Leaflet to prevent a full dashboard rerun.
        returned_map_objects = [
            "last_object_clicked",
            "last_object_clicked_count",
        ]
        if show_extent_only:
            returned_map_objects.append("bounds")

        map_result = st_folium(
            water_map,
            height=700,
            key=f"ti_tree_map_{mode}",
            use_container_width=True,
            feature_group_to_add=marker_layer,
            layer_control=layer_control,
            returned_objects=returned_map_objects,
        )

        if show_extent_only:
            map_bounds = map_result.get("bounds")
            if isinstance(map_bounds, dict):
                southwest = map_bounds.get("_southWest", {})
                northeast = map_bounds.get("_northEast", {})
                if all(
                    key in southwest and key in northeast
                    for key in ("lat", "lng")
                ):
                    new_bounds = {
                        "south": southwest["lat"],
                        "west": southwest["lng"],
                        "north": northeast["lat"],
                        "east": northeast["lng"],
                    }
                    if new_bounds != st.session_state.map_bounds:
                        st.session_state.map_bounds = new_bounds
                        st.rerun()

        clicked_location = map_result.get(
            "last_object_clicked"
        )

        clicked_count = map_result.get(
            "last_object_clicked_count"
        )

        if (
            clicked_location
            and clicked_count is not None
            and clicked_count
            != st.session_state.last_processed_click_count
        ):
            st.session_state.last_processed_click_count = (
                clicked_count
            )

            clicked_latitude = clicked_location.get("lat")
            clicked_longitude = clicked_location.get("lng")

            if (
                clicked_latitude is not None
                and clicked_longitude is not None
            ):
                # Clicking a state or key town marker moves the same map to that area with the zoom set earlier
                focus_targets = []
                for state_name, (latitude, longitude, zoom) in AUSTRALIA_STATE_MARKERS.items():
                    focus_targets.append((latitude, longitude, zoom))
                for name, state_name, latitude, longitude in KEY_LOCATIONS:
                    focus_targets.append((latitude, longitude, 9))

                nearest_focus = None
                nearest_focus_distance = None
                for latitude, longitude, zoom in focus_targets:
                    distance = (
                        (latitude - clicked_latitude) ** 2
                        + (longitude - clicked_longitude) ** 2
                    )
                    if nearest_focus_distance is None or distance < nearest_focus_distance:
                        nearest_focus_distance = distance
                        nearest_focus = (latitude, longitude, zoom)

                if nearest_focus is not None and nearest_focus_distance < 0.000001:
                    latitude, longitude, zoom = nearest_focus
                    st.session_state.map_center = [latitude, longitude]
                    st.session_state.map_zoom = zoom
                    st.session_state.map_bounds = None
                    st.rerun()

            if (
                clicked_latitude is not None
                and clicked_longitude is not None
                and not displayed_locations.empty
            ):
                distances = (
                    (
                        displayed_locations["latitude"]
                        - clicked_latitude
                    )
                    ** 2
                    + (
                        displayed_locations["longitude"]
                        - clicked_longitude
                    )
                    ** 2
                )

                nearest_index = distances.idxmin()

                if distances.loc[nearest_index] < 0.000001:
                    clicked_identifier = (
                        displayed_locations.loc[
                            nearest_index,
                            "SELECT_ID",
                        ]
                    )

                    if (
                        clicked_identifier
                        in st.session_state.selected_bores
                    ):
                        deselect_bore(clicked_identifier)

                    else:
                        select_bore(clicked_identifier)

                    st.rerun()


    # ---------------------------------------------------------
    # WATER-QUALITY GRAPH
    # ---------------------------------------------------------

    def render_quality_panel():
        st.subheader(
            "Historical Water-Quality Comparison"
        )

        st.caption(
            "The graph updates automatically. Pin colours "
            "and graph-line colours match."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select one or more bore pins on the map."
            )
            return

        selected_badges()

        valid_dates = quality["SAMPLEDATE"].dropna()

        earliest_date = valid_dates.min().date()
        latest_date = valid_dates.max().date()

        date_range = st.date_input(
            "Graph date range",
            value=(
                earliest_date,
                latest_date,
            ),
            min_value=earliest_date,
            max_value=latest_date,
            key=(
                f"date_range_{mode}_"
                f"{measurement_column}"
            ),
        )

        graph_data = quality[
            quality["BORE_NO"].isin(
                st.session_state.selected_bores
            )
        ].dropna(
            subset=[measurement_column]
        ).copy()

        if (
            isinstance(date_range, (tuple, list))
            and len(date_range) == 2
        ):
            graph_data = graph_data[
                graph_data["SAMPLEDATE"].between(
                    pd.Timestamp(date_range[0]),
                    pd.Timestamp(date_range[1]),
                )
            ]

        graph_data = (
            graph_data.groupby(
                [
                    "BORE_NO",
                    "SAMPLEDATE",
                ],
                as_index=False,
            )[measurement_column]
            .mean()
            .sort_values(
                [
                    "BORE_NO",
                    "SAMPLEDATE",
                ]
            )
        )

        if graph_data.empty:
            st.warning(
                f"The selected bores have no "
                f"{measurement_name} results in this period."
            )
            return

        figure = go.Figure()

        for identifier in st.session_state.selected_bores:
            bore_data = graph_data[
                graph_data["BORE_NO"] == identifier
            ]

            if bore_data.empty:
                continue

            line_colour = bore_colour(
                identifier
            )["hex"]

            figure.add_trace(
                go.Scatter(
                    x=bore_data["SAMPLEDATE"],
                    y=bore_data[measurement_column],
                    mode="lines+markers",
                    name=bore_display_name(identifier),
                    line={
                        "color": line_colour,
                        "width": 3,
                    },
                    marker={
                        "color": line_colour,
                        "size": 8,
                    },
                    hovertemplate=(
                        f"{bore_display_name(identifier)}<br>"
                        "%{x|%d %b %Y}<br>"
                        f"{measurement_name}: "
                        "%{y:,.2f}<extra></extra>"
                    ),
                )
            )

        figure.update_layout(
            title=f"{measurement_name} comparison",
            hovermode="x unified",
            height=540,
            legend_title_text="Bore",
            margin={
                "l": 40,
                "r": 20,
                "t": 70,
                "b": 100,
            },
            legend={
                "orientation": "h",
                "yanchor": "top",
                "y": -0.20,
                "xanchor": "center",
                "x": 0.5,
            },
        )

        figure.update_xaxes(
            title_text="Sample date"
        )

        figure.update_yaxes(
            title_text=(
                f"{measurement_name} "
                "(source dataset units)"
            )
        )

        filename = (
            f"ti_tree_"
            f"{measurement_column.lower()}_comparison"
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": filename,
                    "width": 1400,
                    "height": 800,
                    "scale": 2,
                },
            },
        )

        st.caption(
            "Download PNG using the camera icon "
            "in the graph toolbar."
        )

        download1, download2 = st.columns(2)

        with download1:
            st.download_button(
                "Download interactive graph",
                data=figure.to_html(
                    full_html=True,
                    include_plotlyjs="cdn",
                ),
                file_name=f"{filename}.html",
                mime="text/html",
                use_container_width=True,
            )

        with download2:
            st.download_button(
                "Download graph data (CSV)",
                data=graph_data.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name=f"{filename}_data.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with st.expander(
            "Measurements used in the graph"
        ):
            st.dataframe(
                graph_data[
                    [
                        "BORE_NO",
                        "SAMPLEDATE",
                        measurement_column,
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    # ---------------------------------------------------------
    # BORE DETAILS
    # ---------------------------------------------------------

    def zone_value(point, layer, field):
        matches = layer[
            layer.geometry.covers(point)
        ]

        if matches.empty:
            return "Not mapped at this location"

        return safe_text(
            matches.iloc[0].get(field)
        )


    def nearest_contour(point):
        point_projected = gpd.GeoSeries(
            [point],
            crs="EPSG:4326",
        ).to_crs(
            epsg=28353
        ).iloc[0]

        contours_projected = contours.to_crs(
            epsg=28353
        )

        nearest_index = (
            contours_projected.geometry
            .distance(point_projected)
            .idxmin()
        )

        return safe_text(
            contours.loc[
                nearest_index
            ].get("DEPTH_AHD")
        )


    def render_bore_details_panel():
        st.subheader(
            "Bore Details and Static Comparison"
        )

        st.caption(
            "These are individual recorded bore attributes, "
            "not a groundwater-level time series."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select one or more bore pins on the map."
            )
            return

        selected_badges()

        selected_data = bores[
            bores["BORE_NO"].isin(
                st.session_state.selected_bores
            )
        ].copy()

        metric_options = {
            "Recorded water level": (
                "WATERLEVEL",
                "m",
            ),
            "Bore yield": (
                "YIELD",
                "L/s",
            ),
            "Completion depth": (
                "COMPLDEPTH",
                "m",
            ),
            "Drilling depth": (
                "DRILLDEPTH",
                "m",
            ),
        }

        metric_name = st.selectbox(
            "Static bore field to compare",
            options=list(metric_options),
        )

        metric_column, metric_unit = (
            metric_options[metric_name]
        )

        chart_data = selected_data.dropna(
            subset=[metric_column]
        )

        if chart_data.empty:
            st.warning(
                "The selected bores have no recorded "
                f"{metric_name.lower()}."
            )

        else:
            figure = go.Figure()

            for _, row in chart_data.iterrows():
                identifier = row["BORE_NO"]

                figure.add_trace(
                    go.Bar(
                        x=[identifier],
                        y=[row[metric_column]],
                        name=bore_display_name(identifier),
                        marker_color=bore_colour(
                            identifier
                        )["hex"],
                        hovertemplate=(
                            f"{bore_display_name(identifier)}<br>"
                            f"{metric_name}: "
                            f"%{{y:,.2f}} "
                            f"{metric_unit}"
                            "<extra></extra>"
                        ),
                    )
                )

            figure.update_layout(
                title=f"{metric_name} comparison",
                height=440,
                showlegend=False,
                xaxis_title="Bore",
                yaxis_title=(
                    f"{metric_name} ({metric_unit})"
                ),
                margin={
                    "l": 40,
                    "r": 20,
                    "t": 70,
                    "b": 60,
                },
            )

            st.plotly_chart(
                figure,
                use_container_width=True,
                config={
                    "displaylogo": False,
                    "toImageButtonOptions": {
                        "format": "png",
                        "filename": (
                            f"ti_tree_"
                            f"{metric_column.lower()}"
                        ),
                        "width": 1200,
                        "height": 700,
                        "scale": 2,
                    },
                },
            )

        table_rows = []

        for _, row in selected_data.iterrows():
            table_rows.append(
                {
                    "Bore": row["BORE_NO"],
                    "Name": safe_text(
                        row["BORE_NAME"]
                    ),
                    "Status": safe_text(
                        row["STATUS"]
                    ),
                    "Purpose": safe_text(
                        row["PURPOSE"]
                    ),
                    "Water level (m)": (
                        row["WATERLEVEL"]
                    ),
                    "Yield (L/s)": row["YIELD"],
                    "Completion depth (m)": (
                        row["COMPLDEPTH"]
                    ),
                    "Drilling depth (m)": (
                        row["DRILLDEPTH"]
                    ),
                    "Salinity zone": zone_value(
                        row.geometry,
                        salinity,
                        "NOTES",
                    ),
                    "Aquifer thickness": zone_value(
                        row.geometry,
                        aquifer,
                        "AQUIFER_TH",
                    ),
                    "Mapped depth to groundwater": (
                        zone_value(
                            row.geometry,
                            water_depth,
                            "DEPTH_TO",
                        )
                    ),
                    "Nearest groundwater contour": (
                        nearest_contour(
                            row.geometry
                        )
                    ),
                }
            )

        details_table = pd.DataFrame(table_rows)

        with st.expander(
            "Selected bore details",
            expanded=True,
        ):
            st.dataframe(
                details_table,
                use_container_width=True,
                hide_index=True,
            )

        st.download_button(
            "Download selected bore details (CSV)",
            data=details_table.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "ti_tree_selected_bore_details.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    # ---------------------------------------------------------
    # MONITORING LOCATIONS
    # ---------------------------------------------------------

    def render_monitoring_panel():
        st.subheader(
            "Groundwater-Monitoring Locations"
        )

        st.caption(
            "The supplied layer contains station details "
            "and NT Water Data Portal links, but not the "
            "historical groundwater-level measurements."
        )

        if not st.session_state.selected_bores:
            st.info(
                "Select a monitoring-location pin on the map."
            )
            return

        selected_badges()

        selected_data = monitoring[
            monitoring["STATION"].isin(
                st.session_state.selected_bores
            )
        ].copy()

        for _, station in selected_data.iterrows():
            with st.container(border=True):
                st.markdown(
                    f"#### {station['STATION']}"
                )

                st.write(
                    "**Name:** "
                    f"{safe_text(station['STATION_NA'])}"
                )

                st.write(
                    "**Status:** "
                    f"{safe_text(station['ACTIVE'])}"
                )

                st.write(
                    "**Type:** "
                    f"{safe_text(station['MONITOR_TY'])}"
                )

                commence = (
                    station["COMMENCE"].strftime(
                        "%d %B %Y"
                    )
                    if pd.notna(station["COMMENCE"])
                    else "Not recorded"
                )

                cease = (
                    station["CEASE"].strftime(
                        "%d %B %Y"
                    )
                    if pd.notna(station["CEASE"])
                    else "Not recorded"
                )

                st.write(
                    f"**Monitoring commenced:** {commence}"
                )

                st.write(
                    f"**Monitoring ceased:** {cease}"
                )

                portal_url = station.get("WATER_DATA")

                if (
                    pd.notna(portal_url)
                    and str(portal_url).startswith("http")
                ):
                    st.link_button(
                        "Open station in NT Water Data Portal",
                        str(portal_url),
                        use_container_width=True,
                    )

        download_columns = [
            "STATION",
            "STATION_NA",
            "MONITOR_TY",
            "ACTIVE",
            "COMMENCE",
            "CEASE",
            "WATER_DATA",
            "latitude",
            "longitude",
        ]

        st.download_button(
            "Download selected monitoring locations (CSV)",
            data=selected_data[
                download_columns
            ].to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "ti_tree_monitoring_locations.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

# ---------------------------------------------------------
# BOM CLIMATE DATA PANEL
# ---------------------------------------------------------

def climate_water_year(series):
    """Return Australian-style water years (September to August)."""
    return series.dt.year.where(series.dt.month >= 9, series.dt.year - 1)

def annual_station_rainfall(station_id):
    rainfall = load_bom_rainfall(station_id)
    if rainfall.empty:
        return pd.DataFrame(columns=["WaterYear", "Rainfall", "ValidDays"])

    rainfall = rainfall.copy()
    rainfall["WaterYear"] = climate_water_year(rainfall["Date"]).astype("Int64")
    rainfall = rainfall.dropna(subset=["Rainfall", "WaterYear"])
    return (
        rainfall.groupby("WaterYear", as_index=False)
        .agg(Rainfall=("Rainfall", "sum"), ValidDays=("Rainfall", "size"))
    )

# Render a small panel on the right of the map, like other dashboard modes, but for annual + monthly rainfall data plots.
def render_bom_climate_panel():
    st.subheader("BOM Rainfall Observations")
    st.caption(
        "Only the supplied BOM data files are used for analysis. Visualise an observed-data sample's annual and monthly rainfall. " 
        "No climate projection or groundwater forecasting is currently available. Please select a BOM station using the dashboard controls menu."
    )

    if bom_stations.empty:
        st.warning("No BOM station data were found. Check the BOM-Datasets folder.")
        return

    # Normalise station number to 6 digits before comparing / matching to Station column in bom_stations.csv.
    station_id = str(
        st.session_state.bom_climate_station_id
        or bom_stations.iloc[0]["Station"]
    ).zfill(6)
    station_rows = bom_stations[
        bom_stations["Station"].astype(str).str.zfill(6).eq(station_id)
    ]
    if station_rows.empty:
        station_id = str(bom_stations.iloc[0]["Station"])
        station_rows = bom_stations.iloc[[0]]
        st.session_state.bom_climate_station_id = station_id

    station = station_rows.iloc[0]
    station_name = str(station["StationName"])
    rainfall = load_bom_rainfall(station_id)

    if rainfall.empty:
        st.warning(f"No rainfall observations were found for {station_id} - {station_name}.")
        return

    valid = rainfall.dropna(subset=["Rainfall"]).copy()
    if valid.empty:
        st.warning("The station file contains no usable rainfall values.")
        return

    first_date = valid["Date"].min()
    last_date = valid["Date"].max()

    st.subheader(
        f"Selected BOM Station: {station_name}"
    )
    # Set up this way so we can minimise streamlit truncating the data displayed, not perfect but works fine on standard size display

    # Using 3 columns, > 3 = truncated data like 31,000mm rainfall = 31,... (not ideal)
    c1, c2, c3 = st.columns(3)
    c1.metric("BOM StationID", str(station_id))
    c2.metric("Total Records", f"{len(valid):,}")
    c3.metric("Years Covered", f"{valid['Date'].dt.year.nunique():,}")
    c1.metric("Total Observed Rainfall", f"{valid['Rainfall'].sum():,.0f} mm")
    c2.metric("Record Start", f"{first_date:%d %b %Y}")
    c3.metric("Record End", f"{last_date:%d %b %Y}")

    with st.expander("Additional Station + Data Details"):
        st.write(f"**Station:** {station_id} - {station_name}")
        st.write(f"**State:** {station['State']}")
        st.write(f"**Latitude:** {station['Latitude']}")
        st.write(f"**Longitude:** {station['Longitude']}")
        st.write(f"**Rainfall file:** {Path(station['DataFile']).name if pd.notna(station['DataFile']) else 'Not found'}")
        st.caption(
            "Information retrieved from the rainfall file listed above, available through the Australian Government - Bureau of Meteorology website at https://www.bom.gov.au/climate/data/. "
        )
    
    # Annual totals make the supplied long daily series easier to compare.
    annual = (
        valid.assign(Year=valid["Date"].dt.year)
        .groupby("Year", as_index=False)["Rainfall"]
        .sum()
    )
    fig = go.Figure(
        go.Bar(x=annual["Year"], y=annual["Rainfall"], name="Annual Rainfall")
    )
    fig.update_layout(
        title="Annual Rainfall (Observed BOM Data)",
        height=420,
        xaxis_title="Year",
        yaxis_title="Rainfall (mm)",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Monthly climatology is useful for seeing the seasonal pattern in each sample station.
    monthly = (
        valid.assign(Month=valid["Date"].dt.month)
        .groupby("Month", as_index=False)["Rainfall"]
        .mean()
    )
    monthly["MonthName"] = pd.to_datetime(
        monthly["Month"].astype(str), format="%m", errors="coerce"
    ).dt.strftime("%b")
    fig_month = go.Figure(
        go.Bar(x=monthly["MonthName"], y=monthly["Rainfall"], name="Average daily rainfall")
    )
    fig_month.update_layout(
        title="Average Daily Rainfall by Month (Observed BOM Data)",
        height=360,
        xaxis_title="Month",
        yaxis_title="Average daily rainfall (mm)",
    )
    st.plotly_chart(fig_month, use_container_width=True)

with map_column:
    render_interactive_map()

with panel_column:
    if mode in [
        "Water-Quality Comparison",
        "Chemical-Threshold Map",
    ]:
        render_quality_panel()

    elif mode == "Bore Details and Static Comparison":
        render_bore_details_panel()

    elif mode == "BOM Climate Data":
        render_bom_climate_panel()

    else:
        render_monitoring_panel()

# ---------------------------------------------------------
# DATA NOTES
# ---------------------------------------------------------

st.divider()

with st.expander("Important data notes"):
    st.markdown(
        """
        - Water-quality results in the supplied Ti Tree subset run
          from 1936 to 2011. They are historical observations and
          should not be described as current water conditions.
        - A line between two samples only connects recorded
          observations. It does not prove that values changed
          smoothly between those dates.
        - The general bore file contains one recorded water-level
          field for many bores. It does not contain a groundwater-
          level time series.
        - The groundwater-monitoring file contains station
          locations, status and portal links. Historical
          measurements must be obtained separately from the
          NT Water Data Portal.
        - Mapped salinity, aquifer thickness and depth-to-
          groundwater layers are regional interpretations and may
          differ from an individual bore result.
        """
    )

# Add a footer with our group details in it and the unit / project + year this prototype is for.     
st.divider()  
st.caption(body="Created by Group 34 for HIT401: Capstone Project, 2026. Built using Streamlit.", text_alignment="center")