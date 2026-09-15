# Trying to incorporate the bom data, moved from main project script to this script temporarily while we sort out main function. 
# When done, we need to incorporate this data in under hopefully a data selector feature (choose source of data, filter by category / type - Field v Publish, etc) when selection feature is figured out
# - or we know more about what the solution needs to do.

## Loads the bom rainfall data into a dataframe, grouping by station + date ##
# Also experimenting with finding the nearest station to the location,
# (for use in addressing tasks like mapping rivers with bores within 1km range, chem composition, etc, just generalised versions currently)

import pandas as pd
from pathlib import Path
from scipy.spatial import cKDTree


## Load the Rain water data from the BOM datasets. ##
rain_folder = Path(r"Datasets/BOM-Datasets")

# Read the CSVs - they all begin with the same IDCJAC0009 product code, followed by <station_name> so that's what we'll use to separate data.
rain_dfs = []
for f in rain_folder.glob("IDCJAC0009_*.csv"):
    df = pd.read_csv(f)
    rain_dfs.append(df)

# If no data CSVs match the file name format, return an error.
if not rain_dfs:
    raise FileNotFoundError(
        f"No rainfall CSVs matched IDCJAC0009_*.csv in {rain_folder.resolve()}"
    )

rain_all = pd.concat(rain_dfs, ignore_index=True)

# Create a proper datetime in YYYY-MM-DD format
rain_all["Date"] = pd.to_datetime(
    rain_all[["Year", "Month", "Day"]].astype(str).agg("-".join, axis=1)
)

# Clean the rainfall data
rain_all["Rainfall_mm"] = pd.to_numeric(rain_all["Rainfall amount (millimetres)"], errors="coerce")

rain_all["Station"] = rain_all["Bureau of Meteorology station number"].astype(str).str.zfill(6)

rain_daily = rain_all.groupby(["Station", "Date"])["Rainfall_mm"].sum().reset_index().sort_values(["Station", "Date"])

print("=== Rainfall ===")
print("Rainfall daily records:", len(rain_daily))
print("Stations with rainfall:", rain_daily["Station"].nunique())


### Load BOM Stations list (currently manually created CSV, for testing), assign nearest station to each bore. ###
# - e.g. a bore at Ti Tree will have the nearest station "015643 Territory Grape Farm NT (42.0km away)" according to BOM website
stations = pd.read_csv("bom_stations.csv")  # columns: Station, Latitude, Longitude

#

# Clean station column names just in case
stations.columns = stations.columns.str.strip().str.strip('"')

print("\n=== Stations ===")
print("Stations columns:", stations.columns.tolist())
print("Number of stations:", len(stations))

# Ensure numeric lat/lon for stations
stations["Latitude"] = pd.to_numeric(stations["Latitude"], errors="coerce")
stations["Longitude"] = pd.to_numeric(stations["Longitude"], errors="coerce")
stations = stations.dropna(subset=["Latitude", "Longitude"])



## Find the nearest station to a bore location, currently just testing with nearby lat/lon coords.

test_points = pd.DataFrame({
    "Name": ["Point A", "Point B", "Point C", "Point D"],
    "Latitude": [-21.5, -22.0, -22.13, 31.90],
    "Longitude": [134.5, 133.0, 133.41, 115.90],
})

# Using scipy's cKDTree class to index k-dimensional points (finding nearest neighbouring stations by lat/lon)
tree = cKDTree(stations[["Latitude", "Longitude"]].values)
dists, idxs = tree.query(test_points[["Latitude", "Longitude"]].values)

# Note - we only have a dummy bom_stations.csv with one row - station 009021 in it, add more to truly test this later.

test_points["NearestStation"] = stations.iloc[idxs]["Station"].values
test_points["Station_Name"] = stations.iloc[idxs]["StationName"].values
test_points["DistToStation_km"] = (dists * 111_000) / 1000  # Convert degrees to meters then km, apparently 1 degree lat = 111,000m (111km).  
# E.g. our current only station is Perth Airport (009021), so 6276.90km away from test point A. I'll add some more stations though from the list.


print("\n === Nearest Station to Test Points ===")
print(test_points)

## Calculations for later analysis, depends what we have to do going forward but finding average rainfall by station is somewhat valuable ##

avg_rain_by_station = rain_daily.groupby("Station")["Rainfall_mm"].mean().sort_values(ascending=False)
# Add station name alongside station number, will need to cross reference bom data with bom_stations.csv to add though so not priority right now.

print("\nAverage daily rainfall by station (mm):")
print(avg_rain_by_station)

# - Rainfall time series for a specific station
# Turn into a plot later, maybe when this is incorporated into main map program.
station_id = avg_rain_by_station.index[0]  # pick the top station as example, from above avg rain by station
top_station = rain_daily[rain_daily["Station"] == station_id].copy()

print(f"\nRainfall time series for station {station_id}:")
print(top_station)
