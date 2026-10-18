## Test file / active work environment file for testing:
# - Cleaning datasets, creating dataframes and testing addition and viability of additional features  
# - Folium with adjustable / non-static data + plots like in folium-test.py, trying to get the interactive map working with features requested
# (note - check email with list of tasks from Cat)

# Add additional comments later, for now just title the sections and come back to after team meeting.

# Still need to work out filtering data CSVs selected by category & type, and not overwriting previously selected ones. 
# Will come back to this but works well enough as is for now. DBG + WE are the same data anyway so it's likely not that effected right now, will be with other data later.

import pandas as pd
from pathlib import Path
import re
import matplotlib.pyplot as plt
import io, base64
import folium
from scipy.spatial import cKDTree

### Load the data from NT Natural Resource Maps folder (Bores.csv) into a dataframe ###

#  - Might need to update this csv from source, may be outdated data in content or format, not sure.
#  - ^ Save for intended auto update from source feature to be implemented later?

bores = pd.read_csv(
    "Datasets/NT-NaturalResourceMapsBoreData/Bores.csv",
    engine="python",
    on_bad_lines="warn",        # Print to terminal the lines of the CSV that are bad in some way, usually a space in RN XXXXX or a "" / , or something.
    quotechar='"',              # End each 
    quoting=3,
)

# Clean the column names by stripping whitespace, surrounding quotes
bores.columns = bores.columns.str.strip().str.strip('"')

# Data includes things like Purpose, Status, etc - should this be incorporated into the plot on each marker as relevant information? *Copied to Project Notes* 

# Standardise BoreID across the CSVs, Bores.csv uses 'Bore no' so converting to 'BoreID' is easier to deal with.
bores["BoreID"] = bores["Bore no"].astype(str).str.strip().str.strip('"').str.upper()
bores["Latitude"] = pd.to_numeric(bores["Latitude"], errors="coerce")       # Set value as NaN if there's any errors.
bores["Longitude"] = pd.to_numeric(bores["Longitude"], errors="coerce")

# Setting the zoom to encompass Ti Tree region when you open the folium map html file, might not be necessary though.
ti_tree_area = (
    bores["Latitude"].between(-23, -19) &
    bores["Longitude"].between(131, 136)
)

bores_ti_tree = bores[ti_tree_area].copy()

# Some information that may be relevant, it's printed to terminal at the moment but could try to put it on the map itself (like NTG AI does with filters)
print("=== Bores ===")
print("\nTotal bores from current data (disregarding skipped):", len(bores))                 # Get the total number of bores in the Bores CSV
print("\nBores in the Ti Tree area:", len(bores_ti_tree))             # Get the number of bores only in the Ti Tree area 
print("\nSample BoreIDs:", bores["BoreID"].dropna().unique()[:5])     # Print 5 of the BoreIDs to the terminal, mainly used for testing data was being passed correctly at each stage. Remove later?


### Load the Groundwater CSVs from Datasets/GroundwaterHeads_20250718 ###

# - Load them recursively, as each dataset is under it's own subfolder (LocationExport).
# - Currently it seems the CSV selected is only the Depth Below Ground one, whether that's because recursive search fails
#   or because it finds the top one last (such as searching and loading from the bottom up with overwrites idk)
# - Add filtering by Field vs Publish data later. 

groundwater_folder = Path(r"Datasets/GroundwaterHeads_20250718")

pattern = re.compile(r"@(RN\d{6})-")    # Set the search filter (pattern / search string) to the BoreID in the CSV filename (numbers after RN) - e.g. @RN005626.  

groundwater_data = {}  # BoreID -> DataFrame

# Check if the groundwater folder can be found at the path specified, if not print the path tried to the terminal. If yes, recursively list all files available.
if not groundwater_folder.exists():
    print("\nThe Groundwater folder was NOT found at the file path:", groundwater_folder.resolve())
    print("Please verify the folder exists.")           # Actually this could cause problems later, especially if we implement an update data from source feature eventually.
                                                        # Address this problem later, will move into Project Notes too.
else:
    print("\nThe Groundwater folder was successfully found at the file path:", groundwater_folder.resolve())
    csv_files = list(groundwater_folder.rglob("*.csv"))             #rglob for recursive search of all files matching the pattern above (filtering by @RN(6 digits) in title)
    print("\nNumber of CSV files found (including recursive search):", len(csv_files)) # This is likely finding all those additional CSVs (bores with wl data, etc) - maybe remove these? Come back to.

    for f in csv_files:
        map = pattern.search(f.stem)
        if not map:
            continue
        bore_id = map.group(1)  # e.g. "RN005626"

        # Skip first 2 rows, use row 3 as header
        df = pd.read_csv(
            f,
            skiprows=2,
            header=0,
            engine="python"
        )

        # Detect timestamp and value columns dynamically
        timestamp_col = None
        val_col = None

        for c in df.columns:
            c_lower = str(c).lower()
            # Find the timestamp column - contains 'timestamp' but not 'event' 
            if "timestamp" in c_lower and "event" not in c_lower:
                timestamp_col = c
            # Find the value column - contains 'value' and 'm'
            if "value" in c_lower and "m" in c_lower:
                val_col = c

        if timestamp_col is None or val_col is None:
            # If there's no columns that match, dataset might not be valid. Print error statement (commented out for now) 
            # print("Skipping file - (no timestamp/value columns in this CSV):", f)
            continue

        df["Timestamp"] = pd.to_datetime(df[timestamp_col], errors="coerce")
        df = df[["Timestamp", val_col]].dropna(subset=["Timestamp", val_col])
        df = df.sort_values("Timestamp")
        df.rename(columns={val_col: "Value (m)"}, inplace=True)

        groundwater_data[bore_id] = df

    print("\nNumber of groundwater time series loaded:", len(groundwater_data))
    if groundwater_data:
        print("\nSample BoreIDs in groundwater_data:", list(groundwater_data.keys())[:5])


### Compare Bore data with Groundwater Data to find overlaps ###
# - Print the information found to terminal. Mainly relevant for use later.

bore_ids_groundwater = set(groundwater_data.keys())
bore_ids_bores = set(bores["BoreID"].unique())
bore_ids_complete = bore_ids_groundwater & bore_ids_bores
bore_ids_ti_tree = set(bores_ti_tree["BoreID"].unique())
bore_ids_ready = bore_ids_complete & bore_ids_ti_tree

print("\n=== Overlaps ===")
print("\nBoreIDs in bores:", len(bore_ids_bores))
print("\nBoreIDs in groundwater:", len(bore_ids_groundwater))
print("\nBoreIDs in both:", len(bore_ids_complete))
print("\nBoreIDs in Ti Tree:", len(bore_ids_ti_tree))
print("\nBoreIDs ready (complete + Ti Tree):", len(bore_ids_ready))
if bore_ids_ready:
    print("\nSample ready BoreIDs:", sorted(bore_ids_ready)[:5])

### Create the plots that will appear within the folium markers ###
# Note - need to play around with the plot settings until we find exactly what we're after. Could possibly do specialised, like in plot_data.py (singular + twin plots), etc

def bore_plot(bore_id, bore_row):
    fig, ax1 = plt.subplots(figsize=(8, 4)) # Adjust the size of the plot, 8,4 seems good but I used 10,5 previously. 
    #Depends what data is plotted really, maybe make it auto adjust size?

    # Groundwater time series plot
    if bore_id in groundwater_data:
        groundwater_df = groundwater_data[bore_id]
        ax1.plot(groundwater_df["Timestamp"], groundwater_df["Value (m)"], color="blue", label="Groundwater level (m)")
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Depth below ground (m)", color="blue")
        ax1.tick_params(axis="y", labelcolor="blue")
        #ax1.invert_yaxis()
    else:
        ax1.text(0.5, 0.5, "No groundwater data available", transform=ax1.transAxes, ha="center")

    title_parts = [f"Bore: {bore_id}"]
    if "Name" in bore_row and pd.notna(bore_row["Name"]):
        title_parts.append(str(bore_row["Name"]))
    ax1.set_title(" | ".join(title_parts))

    fig.autofmt_xdate()
    fig.tight_layout()

    temp = io.BytesIO()
    fig.savefig(temp, format="png", bbox_inches="tight")
    temp.seek(0)
    img_base64 = base64.b64encode(temp.read()).decode()
    plt.close(fig)

    html = f"""
    <div style="font-family: sans-serif; font-size: 12px; min-width: 260px;">
      <b>{bore_id}</b><br>
      <img src="data:image/png;base64,{img_base64}" style="max-width: 280px;">
    </div>
    """
    return html

### Build the folium map now and embed the generated plots into bore markers on map ###

map = folium.Map(location=[-21.5, 134.5], zoom_start=7)

# Start the map with the Ti Tree bores showing (currently our only data plotted anyway)

bores_to_map = bores_ti_tree[
    bores_ti_tree["BoreID"].isin(bore_ids_complete)
].copy()

# Ensure only valid coordinates are used by removing rows with missing values.
bores_to_map = bores_to_map.dropna(subset=["Latitude", "Longitude"])

print("\n=== Folium Map ===")
print("\nBores to map:", len(bores_to_map))

for _, row in bores_to_map.iterrows():
    bore_id = row["BoreID"]
    lat = row["Latitude"]
    lon = row["Longitude"]

    # Check if the data is NaN (Not a Number), skip to next row
    if pd.isna(lat) or pd.isna(lon):
        continue

    popup_html = bore_plot(bore_id, row)

    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(popup_html, max_width=320),
        tooltip=f"Bore {bore_id}"
    ).add_to(map)

map.save("ti_tree_bores_map.html")
print("\nThe map has been saved as 'ti_tree_bores_map.html'. Please open in integrated browser.\n")
# Note - must use integrated browser, opening locally results in the map portion being replaced with a warning tile because this doesn't follow the usage policy for openstreetmaps servers. 
# Will need to do something about this later on I guess, not sure if there's other ways to access it besides VS Code's integrated browser so...
