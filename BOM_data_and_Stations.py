# Trying to incorporate the bom data, moved from main project script to this script temporarily while we sort out main function. 
# When done, we need to incorporate this data in under hopefully a data selector feature (choose source of data, filter by category / type - Field v Publish, etc) when selection feature is figured out
# - or we know more about what the solution needs to do.

## Loads the bom rainfall data into a dataframe, grouping by station + date ##
# Also experimenting with finding the nearest station to the location,
# (for use in addressing tasks like mapping rivers with bores within 1km range, chem composition, etc, just generalised versions currently)

##########################
# Tried to incorporate the web scraping feature (get latest data from source), BOM denies the request and recommends an alternative. Still need to explore this but response was:

# 403
# https://www.bom.gov.au/jsp/ncc/cdio/weatherData/av?p_display_type=dailyZippedDataFile&p_stn_num=010558&p_c=-22416965&p_nccObsCode=136&p_startYear=2024 
# text/html
# <p>Your access is blocked due to the detection of a potential automated access request. The Bureau of Meteorology website does not support web scraping: if you are trying to access Bureau data through automated means, you should stop. You may like to consider the following options:</p> 
# <ul>
# <li>An anonymous FTP channel: <a href="http://www.bom.gov.au/catalogue/anon-ftp.shtml">http://www.bom.gov.au/catalogue/anon-ftp.shtml</a> -  this is free to access, but use is subject to the default terms 

# Anonymous FTP channel is really only for personal use, so I guess this is not viable for our project and will need to be abandoned. User will need to download their own dataset, or we only provide the results + not the data? 
##########################

import pandas as pd
from pathlib import Path
#from scipy.spatial import cKDTree  # - Swapped in place of BallTree, as research into why the distance calculations were clearly inaccurate in prior version revealed BallTree as a better option.
import numpy as np
from sklearn.neighbors import BallTree


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
# - Need to actually add station 015643 for it to show though, currently using dummy data provided so work out how to scrape latest from all stations quick & easily.
stations = pd.read_csv("bom_stations.csv")  # columns: Station, Latitude, Longitude

# Clean station column names just in case (more for down the track in development)
stations.columns = stations.columns.str.strip().str.strip('"')

print("\n=== Stations ===")
print("Stations columns:", stations.columns.tolist())
print("Number of stations:", len(stations))

# Ensure the lat/lon for each station is numeric
stations["Latitude"] = pd.to_numeric(stations["Latitude"], errors="coerce")
stations["Longitude"] = pd.to_numeric(stations["Longitude"], errors="coerce")

# Remove any rows with missing coordinates (not necessary now but for later - add dummy data with broken coords to test)
stations = stations.dropna(subset=["Latitude", "Longitude"]).copy()

# Remove coordinates outside the valid geographic range for Australia (neg Lat + pos Lon)
stations = stations[
    stations["Latitude"].between(-90, 90) &
    stations["Longitude"].between(-180, 180)
].copy()

# Print list of valid stations (no effect without dummy data)
print("Stations with valid coordinates:", len(stations))

## Find the nearest station to a bore location, currently just testing with nearby lat/lon coords.
test_points = pd.DataFrame({
    "Name": ["Point A", "Point B", "Point C", "Point D"],
    "Latitude": [-21.5, -33.5, -22.13, -31.90],      
    "Longitude": [134.5, 150.75, 133.41, 115.90],
})

# # Using scipy's cKDTree class to index k-dimensional points (finding nearest neighbouring stations by lat/lon)
# tree = cKDTree(stations[["Latitude", "Longitude"]].values)
# dists, idxs = tree.query(test_points[["Latitude", "Longitude"]].values)

# - cKDTree implementation wasn't as accurate as the one in place now, BallTree, so have commented it out for now. 

# Clean the test points / ensure they're numeric first before using them
# Adding this now so we don't need to add it later, may implement a 'click nearby -> auto select closest bore marker' feature but hardcoded values used currently.
test_points["Latitude"] = pd.to_numeric(test_points["Latitude"],errors="coerce")

test_points["Longitude"] = pd.to_numeric(test_points["Longitude"],errors="coerce")

# Remove any invalid test points to eliminate error possibilities 
test_points = test_points.dropna(subset=["Latitude", "Longitude"]).copy()

test_points = test_points[
    test_points["Latitude"].between(-90, 90) &
    test_points["Longitude"].between(-180, 180)
].copy()

## Build the BallTree by using haversine distance metric - had to look this up, possibly reference if necessary (google auto AI search results)
# Must convert coordinates to radians in order of latitude, longitude to use though

station_coordinates_radians = np.deg2rad(stations[["Latitude", "Longitude"]].to_numpy()) 

tree = BallTree(station_coordinates_radians, metric="haversine")

# Convert test-point coordinates from degrees to radians
sample_coordinates_radians = np.deg2rad(test_points[["Latitude", "Longitude"]].to_numpy())

# Query the nearest station - distance is returned as an angular distance in radians
dists_radians, idxs = tree.query(sample_coordinates_radians,k=1)

# Set the radius of the Earth for conversion calculations
EARTH_RADIUS_KM = 6_371.0088

# Convert angular distance in radians to kilometres
test_points["DistToStation_km"] = (
    dists_radians[:, 0] * EARTH_RADIUS_KM
)

# Retrieve the information for the nearest station
nearest_station_rows = stations.iloc[idxs[:, 0]].reset_index(drop=True)

test_points["NearestStation"] = (nearest_station_rows["Station"].to_numpy())

# Add StationName only if the column exists
if "StationName" in stations.columns:
    test_points["Station_Name"] = (
        nearest_station_rows["StationName"].to_numpy()
    )
else:
    test_points["Station_Name"] = "N/A"


# Add the selected station's coordinates for checking
test_points["StationLatitude"] = (
    nearest_station_rows["Latitude"].to_numpy()
)

test_points["StationLongitude"] = (
    nearest_station_rows["Longitude"].to_numpy()
)

# test_points["NearestStation"] = stations.iloc[idxs]["Station"].values
# test_points["Station_Name"] = stations.iloc[idxs]["StationName"].values
# test_points["DistToStation_km"] = (dists * 111_000) / 1000  # Convert degrees to meters then km, apparently 1 degree lat = 111,000m (111km).  

# E.g. our current only station is Perth Airport (009021), so like 1000km away from test point A. I'll add some more stations though from the list.
# - Added more points from our provided datasets - these are from locations in each state, so nearest point even right at Ti Tree will not find Station 015643 at Territory Grape Farm NT because we haven't added it yet.

print("\n === Nearest Station to Test Points ===")
print(test_points)

## Calculations for later analysis, depends what we have to do going forward but finding average rainfall by station is somewhat valuable ##

# Calculate average rainfall, grouped by station
avg_rain_by_station = rain_daily.groupby("Station")["Rainfall_mm"].mean().sort_values(ascending=False)

print("\nAverage daily rainfall by station (mm):")
print(avg_rain_by_station)

# - Rainfall time series for a specific station
# Turn into a plot later, maybe when this is incorporated into main map program.
if avg_rain_by_station.empty:
    print("\n There's no station rainfall data available for the time series.")
else:
    station_id = avg_rain_by_station.index[0]  # pick the top station as example, from above avg rain by station
    top_station = rain_daily[rain_daily["Station"] == station_id].copy()

    print(f"\nRainfall time series for station {station_id}:")
    print(top_station)
