### Latest supplied from OneDrive, V1.2 (V1.0 = originally pushed app.py, V1.1 = last added OneDrive file, V1.2 = current available)

from pathlib import Path

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
    page_title="Ti Tree Water Dashboard",
    page_icon="💧",
    layout="wide",
)

st.title("Ti Tree Water Dashboard")

st.caption(
    "Explore historical bore water quality, bore construction, "
    "groundwater monitoring locations and Ti Tree aquifer layers."
)

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
# ---------------------------------------------------------
# EXECUTIVE SUMMARY METRICS (KPIs)
# ---------------------------------------------------------

kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
with kpi_col1:
    st.metric(label="Total Study Bores", value=f"{len(bores):,}")
with kpi_col2:
    st.metric(label="Quality Monitored Bores", value=f"{len(quality_locations):,}")
with kpi_col3:
    st.metric(label="Water Quality Samples", value=f"{len(quality):,}")
with kpi_col4:
    active_cnt = len(monitoring[monitoring["ACTIVE"] == "Yes"]) if "ACTIVE" in monitoring.columns else len(monitoring)
    st.metric(label="Monitoring Bores", value=f"{active_cnt:,}")

st.divider()

# ---------------------------------------------------------
# SELECTION FUNCTIONS
# ---------------------------------------------------------

if "selected_bores" not in st.session_state:
    st.session_state.selected_bores = []

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
            f'font-weight:600;">{identifier}</span>'
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

st.sidebar.header("Dashboard controls")

mode = st.sidebar.radio(
    "Choose a dashboard mode",
    options=[
        "Water-quality comparison",
        "Chemical-threshold map",
        "Bore details and static comparison",
        "Groundwater-monitoring locations",
    ],
)

if st.session_state.get("active_mode") != mode:
    st.session_state.active_mode = mode
    clear_selection()

measurement_name = "Total dissolved solids"
measurement_column = measurements[measurement_name]
minimum_samples = 1
threshold_statistic = "Latest result"
threshold_value = 0.0

if mode in [
    "Water-quality comparison",
    "Chemical-threshold map",
]:
    measurement_name = st.sidebar.selectbox(
        "Choose a measurement",
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

if mode == "Water-quality comparison":
    minimum_samples = st.sidebar.slider(
        "Minimum results per displayed bore",
        min_value=1,
        max_value=20,
        value=2,
    )

if mode == "Chemical-threshold map":
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

if mode == "Bore details and static comparison":
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

if mode == "Groundwater-monitoring locations":
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

if st.sidebar.button(
    "Clear all selected locations",
    use_container_width=True,
):
    clear_selection()
    st.rerun()


# ---------------------------------------------------------
# DISPLAYED LOCATIONS
# ---------------------------------------------------------

if mode == "Water-quality comparison":
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

elif mode == "Chemical-threshold map":
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

elif mode == "Bore details and static comparison":
    displayed_locations = bores[
        bores["STATUS"].isin(status_filter)
    ].copy()

    displayed_locations["SELECT_ID"] = (
        displayed_locations["BORE_NO"]
    )

else:
    displayed_locations = monitoring[
        monitoring["ACTIVE"].isin(status_filter)
    ].copy()

    displayed_locations["SELECT_ID"] = (
        displayed_locations["STATION"]
    )

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

if mode == "Water-quality comparison":
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

elif mode == "Chemical-threshold map":
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

elif mode == "Bore details and static comparison":
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
        "Selected — click again to remove"
        if selected
        else "Click to select"
    )

    if selected:
        marker_colour = bore_colour(
            identifier
        )["marker"]

    elif mode == "Chemical-threshold map":
        if pd.isna(row.get("MAP_VALUE")):
            marker_colour = "gray"

        elif row["MAP_VALUE"] > threshold_value:
            marker_colour = "red"

        else:
            marker_colour = "blue"

    elif mode == "Groundwater-monitoring locations":
        marker_colour = (
            "green"
            if row["ACTIVE"] == "Current"
            else "gray"
        )

    else:
        marker_colour = "blue"

    if mode in [
        "Water-quality comparison",
        "Chemical-threshold map",
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

        if mode == "Chemical-threshold map":
            value_text = formatted_number(
                row.get("MAP_VALUE")
            )

            extra += (
                f"<br><strong>{threshold_statistic}:"
                f"</strong> {value_text}"
            )

    elif mode == "Bore details and static comparison":
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
        <strong>{identifier}</strong><br><br>
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

minimum_x, minimum_y, maximum_x, maximum_y = (
    boundary.total_bounds
)

default_centre = [
    (minimum_y + maximum_y) / 2,
    (minimum_x + maximum_x) / 2,
]

if "map_center" not in st.session_state:
    st.session_state.map_center = default_centre

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 8

map_column, panel_column = st.columns(
    [1.15, 1],
    gap="large",
)

with map_column:
    st.subheader("Interactive Ti Tree map")

    if mode == "Chemical-threshold map":
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
            
            

    elif mode == "Groundwater-monitoring locations":
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
            if mode == "Groundwater-monitoring locations"
            else "tint"
        )

        folium.Marker(
            location=[
                location["latitude"],
                location["longitude"],
            ],
            tooltip=(
                f"{identifier} — {selection_text}"
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

    map_result = st_folium(
        water_map,
        height=700,
        key=f"ti_tree_map_{mode}",
        use_container_width=True,
        feature_group_to_add=marker_layer,
        layer_control=layer_control,
        returned_objects=[
            "last_object_clicked",
            "last_object_clicked_count",
            "center",
            "zoom",
        ],
    )

    if map_result.get("center"):
        centre = map_result["center"]

        st.session_state.map_center = [
            centre["lat"],
            centre["lng"],
        ]

    if map_result.get("zoom") is not None:
        st.session_state.map_zoom = (
            map_result["zoom"]
        )

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
        "Historical water-quality comparison"
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
                name=identifier,
                line={
                    "color": line_colour,
                    "width": 3,
                },
                marker={
                    "color": line_colour,
                    "size": 8,
                },
                hovertemplate=(
                    f"Bore {identifier}<br>"
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
        "Bore details and static comparison"
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
                    name=identifier,
                    marker_color=bore_colour(
                        identifier
                    )["hex"],
                    hovertemplate=(
                        f"{identifier}<br>"
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
        "Groundwater-monitoring locations"
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


with panel_column:
    if mode in [
        "Water-quality comparison",
        "Chemical-threshold map",
    ]:
        render_quality_panel()

    elif mode == "Bore details and static comparison":
        render_bore_details_panel()

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
