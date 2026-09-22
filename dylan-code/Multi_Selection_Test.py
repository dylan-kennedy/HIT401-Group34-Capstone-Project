## Test file / active work environment file for testing:

# An extension of Folium_Bore_Implementation_Test, borrowing most of the code from that file but adding & testing multi-bore selection, 
# a comparison graph inside a comparison panel, and I tried to incorporate more of the data but can't seem to load all 5026 bores into one map 
# (at least not in the time frame I let it run for with old and slow hardware)
# - A separate file because some logic needed to change to add + test these features. 

# I'm new to JS and JSON, so AI consultation through Google's AI was used in the corresponding portions of this code but modified by me where necessary.
# I do not have a record of the original prompts used as I closed the tabs and/or let the sessions expire, but I gave it 
# a general prompt about what would be best to use alongside Folium for a live-updating plot that compares multiple datasets in Python, 
# and the response was to use JS for the comparison panel plot in combination with JSON and Plotly with some script examples provided. Segments of code were provided
# to the AI in order to diagnose errors and get assistance to ensure this portion of the code was working for the end result.

# Import all necessary libraries
import folium
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
import json
import re
from pathlib import Path

## -- Set the file paths to the data -- ##
BORES_CSV = Path("Datasets/NT-NaturalResourceMapsBoreData/Bores.csv")

GROUNDWATER_FOLDER = Path(r"Datasets/GroundwaterHeads_20250718")

MAP_FILE = "ti_tree_bores_map.html"

# -- Filter for the map -- 
# - Set to True to only show Ti Tree bores with groundwater data (using for testing atm, full mode has a lot to load - 5026 Bores)
# - Set to False to show all the bores available with our data, including ones with no available groundwater data. 
#   - Currently not working, or takes a really long time with my old hardware so can't tell if all load at once. Might need to load a different way to speed this up...
#   - Have commented out for now, and also commented out section where it is referenced and replaced with forced Ti Tree bores w/ groundwater only.

GROUNDWATER_ONLY = True

# When BOM data is implemented, can use something like RAINWATER_ONLY for rainfall as an available data measurement type? 
# RAINWATER_ONLY = ?

# Add up to 5 bores into the comparison panel graph for comparison, can add more or less but 5 seems appropriate for now.
MAX_COMPARISON_BORES = 5

## -- Load the Bore Data and metadata -- ##

bores = pd.read_csv(
    BORES_CSV,
    engine="python",
    on_bad_lines="warn",
    quotechar='"',
    quoting=3
)

# Remove any whitespace or quotes from headers (strip and clean data headers)
bores.columns = bores.columns.astype(str).str.strip().str.strip('"')

required_bore_columns = {"Bore no", "Latitude", "Longitude"}

missing_columns = required_bore_columns - set(bores.columns)

# Unlikely to be missing these columns with our current set but if we implement updating from source, good to have this check in place now. 
if missing_columns:
    raise ValueError(
        "The following required columns are missing from Bores.csv: "
        f"{sorted(missing_columns)}\n"
        f"Columns found: {bores.columns.tolist()}"
    )

# Standardise the Bore IDs by converting Bores.csv's Bore no into BoreID to match the other CSVs
bores["BoreID"] = bores["Bore no"].astype(str).str.strip().str.strip('"').str.upper()

# Convert the Lat + Lon coordinates to numbers so no errors arise
bores["Latitude"] = pd.to_numeric(bores["Latitude"], errors="coerce")
bores["Longitude"] = pd.to_numeric(bores["Longitude"], errors="coerce")

# Set the zoom to encompass the Ti Tree region by default when opening the map.
ti_tree_area = (
    bores["Latitude"].between(-23, -19)
    & bores["Longitude"].between(131, 136)
)

bores_ti_tree = bores[ti_tree_area].copy()

# Keep the printed information from previous program file, still haven't incorporated it into a display on the map yet. 
print("=== Bores ===")
print("\nTotal bores from current data:", len(bores))                 # Get the total number of bores in the Bores CSV
print("\nBores in the Ti Tree area:", len(bores_ti_tree))             # Get the number of bores only in the Ti Tree area 
print("\nSample BoreIDs:", bores["BoreID"].dropna().unique()[:5])     # Print 5 of the BoreIDs to the terminal, mainly used for testing data was being passed correctly at each stage. Remove later?

## -- Load the Groundwater CSVs from Datasets/GroundwaterHeads_20250718 -- ###
# As before in original file, but modified for more accuracy. Now looking for keywords (the Bore identifier (@RN(XXXXXX))). 

# Set search filter / pattern to find the BoreID by looking for @RN(XXXXXX)
# e.g. file name like DataSetExport-Depth Below Ground.Field Visits@RN005626-20250718020600.csv = @RN005626
bore_id_pattern = re.compile(r"@(RN\d{6})-")

# Load data into the dataframe, structure is groundwater_data["RN005626"] = DataFrame
groundwater_data = {}

# Don't need to alert user for successful folder find every time now, just alert if folder not found.
if not GROUNDWATER_FOLDER.exists():
    raise FileNotFoundError(
        "Groundwater folder was not found at the expected file path: \n"
        f"{GROUNDWATER_FOLDER.resolve()}"
    )

# There are 64 CSVs available, which is also counting the non-LocationExport subfolder CSVs too - maybe remove these? 
groundwater_files = list(GROUNDWATER_FOLDER.rglob("*.csv"))

print("\n=== Groundwater ===")
print("\nGroundwater folder:", GROUNDWATER_FOLDER.resolve())
print("\nCSV files found recursively:", len(groundwater_files))

for file_path in groundwater_files:
    match = bore_id_pattern.search(file_path.stem)

    if not match:
        print("Skipping file because no BoreID was found:", file_path.name)
        continue

    bore_id = match.group(1) # e.g. "RN005626"

    # Skip 2 rows, using row 3 as the header. Load the data.
    try:
        groundwater_df = pd.read_csv(
            file_path,
            skiprows=2,
            header=0,
            engine="python"
        )

    # Display error for unreadable / unfindable data CSVs. 
    except Exception as error:
        print(
            f"\nCould not read {file_path.name}: {error}"
        )
        continue

    # Clean the groundwater data column names
    groundwater_df.columns = groundwater_df.columns.astype(str).str.strip().str.strip('"')

    # Detect timestamp and value columns dynamically
    timestamp_column = None
    value_column = None

    for column in groundwater_df.columns:
        column_lower = column.lower()

        # Find the timestamp column - contains 'timestamp' but not 'event' 
        if ("timestamp" in column_lower and "event" not in column_lower):
            timestamp_column = column

        # Find the value column - contains 'value' and 'm'
        if "value" in column_lower:
            value_column = column

    # If there's no columns that match, dataset might not be valid.
    if timestamp_column is None or value_column is None:
        print(f"\nSkipping file because timestamp/value columns were not found: {file_path.name}")
        print("\nColumns found:", groundwater_df.columns.tolist())
        continue

    # Convert data types
    groundwater_df["Timestamp"] = pd.to_datetime(groundwater_df[timestamp_column], errors="coerce", dayfirst=False)

    groundwater_df["Value (m)"] = pd.to_numeric(groundwater_df[value_column], errors="coerce")

    groundwater_df = (groundwater_df[["Timestamp", "Value (m)"]].dropna(subset=["Timestamp", "Value (m)"]).sort_values("Timestamp"))

    # Skipped files include the 4 CSVs in the Groundwater folder not under LocationExport subfolders, no BoreID column found.
    if groundwater_df.empty:
        print("\nSkipping file because it contains no usable records:", file_path.name)
        continue

    groundwater_data[bore_id] = groundwater_df

print("\nGroundwater time series loaded:", len(groundwater_data))

if groundwater_data:
    print("\nSample groundwater BoreIDs:", list(groundwater_data.keys())[:5])

## -- Select the bores to be displayed -- ##
# Currently only have Groundwater data, but this section was for if Rainfall was implemented, while I remembered
if GROUNDWATER_ONLY:
    available_bore_ids = set(groundwater_data.keys())
    bores_to_map = bores_ti_tree[bores_ti_tree["BoreID"].isin(available_bore_ids)].copy()

# else if RAINWATER_ONLY:
    # set available bores to rainwater data, map the rainwater data only, etc

else:
    bores_to_map = bores_ti_tree.copy()

## Removed BoreID overlap portion for now. ##

bores_to_map = bores_to_map.dropna(subset=["Latitude", "Longitude"])

print("\n=== Map Data ===")
print("\nBores selected for mapping:", len(bores_to_map))

print("\nBoreIDs selected:", bores_to_map["BoreID"].tolist())


## -- Create the bore plots on the map marker popup displays -- ## 
def plot_bore_popup(bore_id, bore_row, groundwater_data):
    # This will create an individual bore graph displayed, as well as an 'add/remove comparison' button 
    # to add the data plot to the comparison panel. 
    # The BoreID is stored in a separate variable data-bore-id on the click of the button because using 'onclick' didn't work correctly. 
    
    figure, axis = plt.subplots(figsize=(8, 4))

    # Groundwater time series plot
    if bore_id in groundwater_data:
        groundwater_df = groundwater_data[bore_id]

        axis.plot(
            groundwater_df["Timestamp"],
            groundwater_df["Value (m)"],
            color="blue",
            marker="o",
            markersize=2,
            linewidth=1,
            label="Groundwater Value"
        )

        axis.set_xlabel("Date")
        axis.set_ylabel("Value (m)")
        axis.set_title(f"Bore {bore_id}")
        axis.grid(True, alpha=0.3)

        # Comment out for Water Elevation data, Uncomment for Depth Below Ground (will need to automate this in future updates)
        axis.invert_yaxis()

    # If data is unavailable and marker is still placed, add a placeholder to the marker content window
    else:
        axis.text(
            0.5,
            0.5,
            "There is no groundwater data available",
            transform=axis.transAxes,
            ha="center",
            va="center"
        )

        axis.set_title(f"Bore {bore_id}")

    figure.autofmt_xdate()
    figure.tight_layout()

    image_buffer = io.BytesIO()

    # Save the plot as a png image in a Base64 buffer
    figure.savefig(image_buffer, format="png", bbox_inches="tight")

    image_buffer.seek(0)

    image_base64 = base64.b64encode(image_buffer.read()).decode()

    plt.close(figure)

    bore_name = bore_row.get("Name", "")

    if pd.isna(bore_name):
        bore_name = ""

    # Escape (convert data into a safe format) the metadata displayed as HTML
    bore_name = (
        str(bore_name)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    # Escape the BoreID to use in an HTML attribute.
    bore_id_attribute = (
        str(bore_id)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    # Prepare the HTML for the map for this portion
    # Consists of Bore ID, Bore Name, the plotted data, and the Add/Remove Comparison button. 

    return f"""
    <div style="
        font-family: Arial, sans-serif;
        font-size: 12px;
        min-width: 290px;
    ">
        <div>
            <b>Bore ID:</b> {bore_id_attribute}<br>
            <b>Name:</b> {bore_name}
        </div>

        <img
            src="data:image/png;base64,{image_base64}"
            style="
                max-width: 280px;
                display: block;
                margin-top: 6px;
            "
        >

        <button
            type="button"
            class="comparison-toggle-button"
            data-bore-id="{bore_id_attribute}"
            style="
                margin-top: 8px;
                padding: 5px 8px;
                cursor: pointer;
            "
        >
            Add/remove comparison
        </button>
    </div>
    """

## -- Create the Folium Map -- ##
map_object = folium.Map(location=[-21.5, 134.5], zoom_start=7, control_scale=True)

## -- Embed the comparison data as JSON -- ##
# Need to update the markers in real time for this feature to work so research led me to JSON + JS. 

comparison_data = {}

for bore_id in bores_to_map["BoreID"].dropna().unique():
    bore_id = str(bore_id)

    if bore_id not in groundwater_data:
        continue

    groundwater_df = groundwater_data[bore_id].copy()

    groundwater_df["Timestamp"] = pd.to_datetime(groundwater_df["Timestamp"], errors="coerce")

    groundwater_df["Value (m)"] = pd.to_numeric(groundwater_df["Value (m)"], errors="coerce")

    groundwater_df = groundwater_df.dropna(subset=["Timestamp", "Value (m)"])

    if groundwater_df.empty:
        continue

    groundwater_df = groundwater_df.sort_values("Timestamp")

    comparison_data[bore_id] = {
        "timestamps": (
            groundwater_df["Timestamp"]
            .dt.strftime("%Y-%m-%d %H:%M:%S")
            .tolist()
        ),
        "values": (
            groundwater_df["Value (m)"]
            .astype(float)
            .tolist()
        )
    }

comparison_json = json.dumps(comparison_data, allow_nan=False)

print("\nComparison series embedded:", len(comparison_data))

print("Embedded BoreIDs:", list(comparison_data.keys()))

## -- Add the comparison panel to the map, on the right-hand-side -- ##
# Comparison panel has a title 'Bore Comparison', list of selected bores by bore ID, a warning if too many 
# bores have been selected (reset bores button is available for this), and the comparison plot.

comparison_panel = """
<div id="comparison-panel"
     style="
       position: fixed;
       top: 10px;
       right: 10px;
       width: 420px;
       height: 405px;
       background-color: white;
       border: 2px solid #666;
       border-radius: 6px;
       z-index: 9999;
       padding: 8px;
       box-shadow: 0 2px 8px rgba(0,0,0,0.3);
       font-family: Arial, sans-serif;
     ">

    <div style="font-weight: bold; margin-bottom: 4px;">
        Bore comparison
    </div>

    <div id="selected-bores"
         style="font-size: 12px; margin-bottom: 4px;">
        Selected bores: none
    </div>

    <div id="comparison-warning"
         style="
            color: #b00020;
            font-size: 12px;
            min-height: 18px;
         ">
    </div>

    <button
        id="clear-comparison"
        type="button"
        style="margin-bottom: 5px; cursor: pointer;"
    >
        Clear selection
    </button>

    <div
        id="comparison-plot"
        style="width: 100%; height: 330px;"
    >
    </div>
</div>
"""

# Embed the comparison panel within the generated folium map.
map_object.get_root().html.add_child(folium.Element(comparison_panel))

## -- Add the markers to the map -- ##

for _, row in bores_to_map.iterrows():
    bore_id = str(row["BoreID"])
    latitude = float(row["Latitude"])
    longitude = float(row["Longitude"])

    popup_html = plot_bore_popup(
        bore_id,
        row,
        groundwater_data
    )

    folium.Marker(
        location=[latitude, longitude],
        popup=folium.Popup(
            popup_html,
            max_width=330
        ),
        tooltip=f"Open bore {bore_id}"
    ).add_to(map_object)


## -- Add Plotly.js -- ##
# Plotly is needed for the real-time rendering of the map and updates aspect.
# Folium and Plotly both use HTML + JS

plotly_script = """
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
"""

map_object.get_root().header.add_child(folium.Element(plotly_script))

## -- Add the comparison Javascript -- ##
# Mostly AI Generated JS but many variables and text were adapted by me for use with this python script as needed. See earlier note for more info.  
comparison_javascript = f"""
<script>
const comparisonData = {comparison_json};
const selectedBores = [];
const MAX_BORES = {MAX_COMPARISON_BORES};

function updateSelectedBoresText() {{
    const selectedElement =
        document.getElementById("selected-bores");

    if (!selectedElement) {{
        return;
    }}

    if (selectedBores.length === 0) {{
        selectedElement.textContent =
            "Selected bores: none";
    }} else {{
        selectedElement.textContent =
            "Selected bores: "
            + selectedBores.join(", ");
    }}
}}

function showComparisonWarning(message) {{
    const warningElement =
        document.getElementById("comparison-warning");

    if (warningElement) {{
        warningElement.textContent = message;
    }}
}}

function redrawComparisonPlot() {{
    const plotElement =
        document.getElementById("comparison-plot");

    if (!plotElement) {{
        console.warn(
            "The comparison plot element was not found."
        );
        return;
    }}

    if (typeof Plotly === "undefined") {{
        console.error(
            "Plotly failed to load."
        );
        return;
    }}

    const traces = [];

    selectedBores.forEach(function(boreId) {{
        const bore = comparisonData[boreId];

        if (!bore) {{
            console.warn(
                "There is no available embedded data for BoreID:",
                boreId
            );
            return;
        }}

        traces.push({{
            x: bore.timestamps,
            y: bore.values,
            type: "scatter",
            mode: "lines+markers",
            name: boreId,
            connectgaps: false
        }});
    }});

    const layout = {{
        title: {{
            text: "Groundwater Comparison Graph"
        }},
        xaxis: {{
            title: {{
                text: "Date"
            }}
        }},
        yaxis: {{
            title: {{
                text: "Groundwater value (m)"
            }}
        }},
        margin: {{
            l: 55,
            r: 15,
            t: 45,
            b: 45
        }},
        legend: {{
            orientation: "h"
        }},
        hovermode: "x unified",
        uirevision: "keep-view"
    }};

    Plotly.react(
        "comparison-plot",
        traces,
        layout,
        {{
            responsive: true,
            displaylogo: false
        }}
    );

    updateSelectedBoresText();
}}

function toggleBore(boreId) {{
    console.log("Toggling bore:", boreId);

    const existingIndex =
        selectedBores.indexOf(boreId);

    if (existingIndex !== -1) {{
        selectedBores.splice(existingIndex, 1);
        showComparisonWarning("");
        redrawComparisonPlot();
        return;
    }}

    if (selectedBores.length >= MAX_BORES) {{
        showComparisonWarning(
            "Maximum of "
            + MAX_BORES
            + " can be compared at the same time. Please remove at least one (or use the reset button) to continue."
        );
        return;
    }}

    if (!comparisonData[boreId]) {{
        showComparisonWarning(
            "No comparison data is available currently for "
            + boreId
            + "."
        );
        return;
    }}

    selectedBores.push(boreId);
    showComparisonWarning("");
    redrawComparisonPlot();
}}

function setupComparisonButtonHandler() {{
    document.addEventListener(
        "click",
        function(event) {{
            const button = event.target.closest(
                ".comparison-toggle-button"
            );

            if (!button) {{
                return;
            }}

            const boreId =
                button.getAttribute("data-bore-id");

            if (!boreId) {{
                console.warn(
                    "The comparison button has no BoreID attributed."
                );
                return;
            }}

            toggleBore(boreId);
        }}
    );
}}

document.addEventListener(
    "DOMContentLoaded",
    function() {{
        setupComparisonButtonHandler();
        redrawComparisonPlot();

        const clearButton =
            document.getElementById("clear-comparison");

        if (clearButton) {{
            clearButton.addEventListener(
                "click",
                function() {{
                    selectedBores.length = 0;
                    showComparisonWarning("");
                    redrawComparisonPlot();
                }}
            );
        }}
    }}
);
</script>
"""

map_object.get_root().html.add_child(folium.Element(comparison_javascript))

## -- Update the map & create the HTML file -- ##
# Map File name is 'ti_tree_bores.html' as set earlier

map_object.save(MAP_FILE)

print(f"\nMap saved as: {MAP_FILE}")

print("Open the map HTML file using the integrated browser (right click > Open in Integrated Browser), then click on a marker.\n")
