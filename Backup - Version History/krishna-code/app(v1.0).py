from pathlib import Path
import hashlib

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
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
    "Click multiple bore pins, choose a water-quality "
    "measurement and compare the selected locations."
)


# ---------------------------------------------------------
# AVAILABLE WATER-QUALITY MEASUREMENTS
# ---------------------------------------------------------

measurements = {
    "Total dissolved solids": "TDS",
    "Laboratory electrical conductivity": "EC_LAB",
    "Field electrical conductivity": "EC_FIELD",
    "Chloride": "CHLORIDE",
    "Calculated NaCl": "NACL",
    "Laboratory pH": "PH_LAB",
    "Field pH": "PH_FIELD",
    "Water temperature": "TEMP",
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
}


# ---------------------------------------------------------
# FILE LOCATIONS
# ---------------------------------------------------------

project_folder = Path(__file__).parent

quality_file = (
    project_folder
    / "data"
    / "nt_bores"
    / "Bores_water_quality.shp"
)

boundary_file = (
    project_folder
    / "data"
    / "ti_tree"
    / "data"
    / "ttbaq_250_bnd.shp"
)

salinity_file = (
    project_folder
    / "data"
    / "ti_tree"
    / "data"
    / "ttbaq_250_sal.shp"
)

aquifer_file = (
    project_folder
    / "data"
    / "ti_tree"
    / "data"
    / "ttbaq_250_aqt.shp"
)

water_depth_file = (
    project_folder
    / "data"
    / "ti_tree"
    / "data"
    / "ttbaq_250_wd.shp"
)

contour_file = (
    project_folder
    / "data"
    / "ti_tree"
    / "data"
    / "ttbaq_250_cnt.shp"
)


# ---------------------------------------------------------
# LOAD AND PREPARE DATA
# ---------------------------------------------------------

@st.cache_data(show_spinner="Loading Ti Tree bore data...")
def load_data():
    boundary = gpd.read_file(boundary_file)
    salinity = gpd.read_file(salinity_file)
    aquifer = gpd.read_file(aquifer_file)
    water_depth = gpd.read_file(water_depth_file)
    contours = gpd.read_file(contour_file)

    quality = pyogrio.read_dataframe(
        quality_file,
        columns=[
            "BORE_NO",
            "SAMPLEDATE",
            *measurements.values(),
        ],
    )

    # Convert every layer to latitude and longitude
    boundary = boundary.to_crs(epsg=4326)
    salinity = salinity.to_crs(epsg=4326)
    aquifer = aquifer.to_crs(epsg=4326)
    water_depth = water_depth.to_crs(epsg=4326)
    contours = contours.to_crs(epsg=4326)
    quality = quality.to_crs(epsg=4326)

    # Convert sample dates to proper dates
    quality["SAMPLEDATE"] = pd.to_datetime(
        quality["SAMPLEDATE"],
        errors="coerce",
    )

    quality = quality.dropna(
        subset=[
            "BORE_NO",
            "SAMPLEDATE",
            "geometry",
        ]
    )

    # Convert measurements into numbers
    for column in measurements.values():
        quality[column] = pd.to_numeric(
            quality[column],
            errors="coerce",
        )

    # Keep only samples inside the Ti Tree Basin
    study_area = boundary.geometry.union_all()

    quality = quality[
        quality.geometry.intersects(study_area)
    ].copy()

    # Calculate sample information for each bore
    bore_summary = (
        quality.groupby("BORE_NO")
        .agg(
            SAMPLE_COUNT=("BORE_NO", "size"),
            FIRST_SAMPLE=("SAMPLEDATE", "min"),
            LATEST_SAMPLE=("SAMPLEDATE", "max"),
        )
        .reset_index()
    )

    # Keep one location for each bore
    bore_locations = (
        quality.sort_values("SAMPLEDATE")
        .drop_duplicates(
            subset=["BORE_NO"],
            keep="last",
        )
        [["BORE_NO", "geometry"]]
    )

    bore_locations = bore_locations.merge(
        bore_summary,
        on="BORE_NO",
        how="left",
    )

    bore_locations = gpd.GeoDataFrame(
        bore_locations,
        geometry="geometry",
        crs="EPSG:4326",
    )

    bore_locations["latitude"] = (
        bore_locations.geometry.y
    )

    bore_locations["longitude"] = (
        bore_locations.geometry.x
    )

    return (
        boundary,
        salinity,
        aquifer,
        water_depth,
        contours,
        quality,
        bore_locations,
    )


(
    boundary,
    salinity,
    aquifer,
    water_depth,
    contours,
    quality,
    bore_locations,
) = load_data()


# ---------------------------------------------------------
# SELECTED BORE MEMORY
# ---------------------------------------------------------

if "selected_bores" not in st.session_state:
    st.session_state.selected_bores = []


# ---------------------------------------------------------
# SIDEBAR CONTROLS
# ---------------------------------------------------------

st.sidebar.header("Comparison controls")

measurement_name = st.sidebar.selectbox(
    "Choose a measurement",
    options=list(measurements.keys()),
)

measurement_column = measurements[measurement_name]

minimum_samples = st.sidebar.slider(
    "Minimum samples per bore",
    min_value=1,
    max_value=20,
    value=2,
)

if st.sidebar.button("Clear all selected bores"):
    st.session_state.selected_bores = []
    st.rerun()


# ---------------------------------------------------------
# FILTER THE DISPLAYED BORES
# ---------------------------------------------------------

displayed_bores = bore_locations[
    bore_locations["SAMPLE_COUNT"] >= minimum_samples
].copy()

visible_bore_numbers = set(
    displayed_bores["BORE_NO"].tolist()
)

st.session_state.selected_bores = [
    bore_number
    for bore_number in st.session_state.selected_bores
    if bore_number in visible_bore_numbers
]


# ---------------------------------------------------------
# SUMMARY INFORMATION
# ---------------------------------------------------------

summary_column1, summary_column2, summary_column3 = (
    st.columns(3)
)

summary_column1.metric(
    "Displayed bore locations",
    f"{len(displayed_bores):,}",
)

summary_column2.metric(
    "Ti Tree water-quality samples",
    f"{len(quality):,}",
)

summary_column3.metric(
    "Selected bores",
    len(st.session_state.selected_bores),
)


# ---------------------------------------------------------
# CREATE THE MAP
# ---------------------------------------------------------

minimum_x, minimum_y, maximum_x, maximum_y = (
    boundary.total_bounds
)

centre_latitude = (minimum_y + maximum_y) / 2
centre_longitude = (minimum_x + maximum_x) / 2

water_map = folium.Map(
    location=[
        centre_latitude,
        centre_longitude,
    ],
    zoom_start=8,
    tiles="OpenStreetMap",
    control_scale=True,
)


# ---------------------------------------------------------
# SALINITY LAYER
# ---------------------------------------------------------

folium.GeoJson(
    salinity,
    name="Salinity zones",
    style_function=lambda feature: {
        "color": "#d97706",
        "weight": 1,
        "fillColor": "#fbbf24",
        "fillOpacity": 0.25,
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


# ---------------------------------------------------------
# AQUIFER-THICKNESS LAYER
# ---------------------------------------------------------

folium.GeoJson(
    aquifer,
    name="Aquifer thickness",
    show=False,
    style_function=lambda feature: {
        "color": "#0891b2",
        "weight": 1,
        "fillColor": "#67e8f9",
        "fillOpacity": 0.25,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["AQUIFER_TH"],
        aliases=["Aquifer thickness:"],
    ),
).add_to(water_map)


# ---------------------------------------------------------
# DEPTH-TO-GROUNDWATER LAYER
# ---------------------------------------------------------

folium.GeoJson(
    water_depth,
    name="Depth to groundwater",
    show=False,
    style_function=lambda feature: {
        "color": "#2563eb",
        "weight": 1,
        "fillColor": "#60a5fa",
        "fillOpacity": 0.20,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["DEPTH_TO"],
        aliases=["Depth to groundwater:"],
    ),
).add_to(water_map)


# ---------------------------------------------------------
# GROUNDWATER ELEVATION CONTOURS
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# TI TREE BASIN BOUNDARY
# ---------------------------------------------------------

folium.GeoJson(
    boundary,
    name="Ti Tree Basin boundary",
    style_function=lambda feature: {
        "color": "#172554",
        "weight": 4,
        "fillOpacity": 0,
    },
).add_to(water_map)


# ---------------------------------------------------------
# BORE MARKERS
# ---------------------------------------------------------

bore_layer = folium.FeatureGroup(
    name="Bores with water-quality samples"
)

for _, bore in displayed_bores.iterrows():
    bore_number = bore["BORE_NO"]

    if bore_number in st.session_state.selected_bores:
        marker_colour = "purple"
        selection_text = "Selected — click again to remove"
    else:
        marker_colour = "blue"
        selection_text = "Click to select"

    if pd.notna(bore["FIRST_SAMPLE"]):
        first_date = bore["FIRST_SAMPLE"].strftime(
            "%d %b %Y"
        )
    else:
        first_date = "Unknown"

    if pd.notna(bore["LATEST_SAMPLE"]):
        latest_date = bore["LATEST_SAMPLE"].strftime(
            "%d %b %Y"
        )
    else:
        latest_date = "Unknown"

    popup_information = f"""
    <div style="width: 240px;">
        <strong>Bore {bore_number}</strong>
        <br><br>
        Samples: {int(bore['SAMPLE_COUNT'])}
        <br>
        First sample: {first_date}
        <br>
        Latest sample: {latest_date}
        <br><br>
        <strong>{selection_text}</strong>
    </div>
    """

    folium.Marker(
        location=[
            bore["latitude"],
            bore["longitude"],
        ],
        tooltip=f"{bore_number} — {selection_text}",
        popup=folium.Popup(
            popup_information,
            max_width=270,
        ),
        icon=folium.Icon(
            color=marker_colour,
            icon="tint",
            prefix="fa",
        ),
    ).add_to(bore_layer)


bore_layer.add_to(water_map)


# ---------------------------------------------------------
# MAP CONTROLS
# ---------------------------------------------------------

folium.LayerControl(
    collapsed=False
).add_to(water_map)

water_map.fit_bounds(
    [
        [minimum_y, minimum_x],
        [maximum_y, maximum_x],
    ]
)


# ---------------------------------------------------------
# DISPLAY THE MAP
# ---------------------------------------------------------

selection_signature = hashlib.md5(
    "|".join(
        sorted(st.session_state.selected_bores)
    ).encode("utf-8")
).hexdigest()[:10]

map_result = st_folium(
    water_map,
    width=None,
    height=620,
    key=f"ti_tree_map_{selection_signature}",
    returned_objects=[
        "last_object_clicked",
    ],
)


# ---------------------------------------------------------
# DETECT THE CLICKED BORE
# ---------------------------------------------------------

clicked_location = map_result.get(
    "last_object_clicked"
)

if clicked_location:
    clicked_latitude = clicked_location.get("lat")
    clicked_longitude = clicked_location.get("lng")

    if (
        clicked_latitude is not None
        and clicked_longitude is not None
        and not displayed_bores.empty
    ):
        distances = (
            (
                displayed_bores["latitude"]
                - clicked_latitude
            ) ** 2
            +
            (
                displayed_bores["longitude"]
                - clicked_longitude
            ) ** 2
        )

        nearest_index = distances.idxmin()
        nearest_distance = distances.loc[nearest_index]

        if nearest_distance < 0.000001:
            clicked_bore = displayed_bores.loc[
                nearest_index,
                "BORE_NO",
            ]

            if clicked_bore in st.session_state.selected_bores:
                st.session_state.selected_bores.remove(
                    clicked_bore
                )
            else:
                st.session_state.selected_bores.append(
                    clicked_bore
                )

            st.rerun()


# ---------------------------------------------------------
# DISPLAY SELECTED BORES
# ---------------------------------------------------------

st.subheader("Selected bores")

if not st.session_state.selected_bores:
    st.info(
        "No bores are selected. Click the blue pins on the map."
    )

else:
    selected_columns = st.columns(
        min(
            len(st.session_state.selected_bores),
            4,
        )
    )

    for position, bore_number in enumerate(
        st.session_state.selected_bores
    ):
        selected_column = selected_columns[
            position % len(selected_columns)
        ]

        with selected_column:
            st.write(f"**{bore_number}**")

            if st.button(
                "Remove",
                key=f"remove_{bore_number}",
            ):
                st.session_state.selected_bores.remove(
                    bore_number
                )
                st.rerun()


# ---------------------------------------------------------
# WATER-QUALITY COMPARISON GRAPH
# ---------------------------------------------------------

st.subheader("Water-quality comparison")

if st.session_state.selected_bores:
    valid_dates = quality["SAMPLEDATE"].dropna()

    earliest_date = valid_dates.min().date()
    latest_date = valid_dates.max().date()

    date_range = st.date_input(
        "Choose the graph date range",
        value=(
            earliest_date,
            latest_date,
        ),
        min_value=earliest_date,
        max_value=latest_date,
    )

    if st.button(
        "Get comparison graph",
        type="primary",
    ):
        graph_data = quality[
            quality["BORE_NO"].isin(
                st.session_state.selected_bores
            )
        ].copy()

        graph_data = graph_data.dropna(
            subset=[
                measurement_column,
            ]
        )

        if len(date_range) == 2:
            start_date = pd.Timestamp(
                date_range[0]
            )

            end_date = pd.Timestamp(
                date_range[1]
            )

            graph_data = graph_data[
                graph_data["SAMPLEDATE"].between(
                    start_date,
                    end_date,
                )
            ]

        # Average repeated measurements recorded for
        # the same bore on the same date
        graph_data = (
            graph_data.groupby(
                [
                    "BORE_NO",
                    "SAMPLEDATE",
                ],
                as_index=False,
            )[measurement_column]
            .mean()
        )

        graph_data = graph_data.sort_values(
            [
                "BORE_NO",
                "SAMPLEDATE",
            ]
        )

        if graph_data.empty:
            st.warning(
                "The selected bores do not have results for "
                f"{measurement_name} in this date range."
            )

        else:
            figure = px.line(
                graph_data,
                x="SAMPLEDATE",
                y=measurement_column,
                color="BORE_NO",
                markers=True,
                labels={
                    "SAMPLEDATE": "Sample date",
                    measurement_column: (
                        f"{measurement_name} "
                        "(source dataset units)"
                    ),
                    "BORE_NO": "Bore number",
                },
                title=f"{measurement_name} comparison",
            )

            figure.update_layout(
                hovermode="x unified",
                legend_title_text="Bore",
                margin=dict(
                    l=40,
                    r=40,
                    t=70,
                    b=120,
                ),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.22,
                    xanchor="center",
                    x=0.5,
                ),
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

            st.plotly_chart(
                figure,
                width="stretch",
            )

            st.subheader(
                "Measurements used in the graph"
            )

            st.dataframe(
                graph_data[
                    [
                        "BORE_NO",
                        "SAMPLEDATE",
                        measurement_column,
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

else:
    st.caption(
        "Select at least one bore before creating a graph."
    )
    