#####
#
#   HIT401 - Group 34
#   "Folium Test (folium-test.py)"
#   see description below
#   
#####

# General Project Notes
# - Focus on Ti Tree Basin for now.
# - Cross reference bore data identifiers (e.g. RN005626) with the bore data list / other CSVs? 
#       - End goal might be being able to automatically download up to date data, save it in the CSV index used here with all necessary features?
#       - Much like the solution already in place, 
#       - Work out how to automatically retrieve data from source (maybe through the direct link for location, might need a CSV of location names + the 'download CSV' link so the user can get it easily?)
# - Incorporate BOM rainfall and NTG bore data, focusing on Ti Tree Basin first.
# - Analyse data first - e.g. a graph of bore data vs bore level is the same graph so no point comparing the two. - See 

# Tasks Advised
# 1 - "It would be good if they can automatically extract this data for the region of interest, that is a good idea."
# 2 - "From this data I have asked the to consider seasonal changes like you do for rainfall, they could do that for bore data matched to local rainfall? To consider replenishment."
# 3 - "I have suggested that they improve on the NTG bore map and enable users to click a location on a terrain map to add a bore reading to a single graph for comparison."

# Think about:
# What are the best types of data to compare / contrast
# What information would this give us, and how might it be relevant for a groundwater report card
# What does a groundwater report card generally look like


# Folium-Test.py Notes
# Maybe add something like a GUI prompt for the user to filter location for data? Idk might be too complex atm
# Could use a GUI for the data comparison tool, like 'choose first location + type of data (field / publish)', then 'choose second location + type'
# - then generate a twin-plot (both data sets on the one graph) showing how both compare? Might need to work out how to get opposing data sets to look 
# like a valuable comparison and not a jumbled mess / unintelligible graph first though

# New Notes
# Would having to open the generated html file to view the map be too much? I think Tkinter is an all-in-one 'run code' solution, but from what I read it
# didn't have some of the features that folium has, so not sure yet which would be better.


#### Might want to comment this out otherwise it runs every time, unless you only highlight the Folium code part and then hit 'Run' I guess. ###

# Testing how to download and load CSV data to address updating data to latest available on code launch, which we are likely gonna need
import requests

# Use a direct link to a CSV, can't work out how to get around the 'Download CSV' button you have to click on NTG aquatic information site for their data
url = "https://www.timestored.com/data/sample/dowjones.csv" # Generic URL with a CSV for testing

# Send an HTTP get request to the url above, then check if the request was successful.
response = requests.get(url)
if response.status_code == 200:
    # Open a file locally with write permissions, inject the data and save it to root folder
    with open("TestingWithDowJonesCSV.csv", "wb") as f:
        f.write(response.content)
    print("The CSV was successfully downloaded and has been saved, check the TestingWithDowJonesCSV.csv file now.")
else:
    print(f"Couldn't download the file, the response received was {response.status_code}")

# Test this by running to get the file, then deleting some lines, then running again to update the contents to latest.
# It works, but there's no prompt about overwriting the file (guess it's not necessary for our use when we want to update to latest data 
# every time and we keep the formatting the same, even with some mistakes in the data)


# Start working on folium markers with our CSV data and plots here later - Done, well at least a working test version for now.

import folium
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import base64
from io import BytesIO

# Notes:
# Remember that idea for a gui prompt with filter by location, just like ntg aquatics info website has. Might be relevant if we can work out how to do it
# I mentioned it in folium test I think


# Open the CSV, read the data and generate the dataframe, parsing timestamp as datetime64 again.
def load_csv(file_path):
    df_title = pd.read_csv(file_path, header=None, nrows=1, usecols=[0])
    plot_title = str(df_title.iloc[0, 0])

    df = pd.read_csv(
        file_path,
        skiprows=2,
        parse_dates=["Timestamp (UTC+09:30)"],
    )
    df = df.set_index("Timestamp (UTC+09:30)")
    return plot_title, df

# Create the plots using the CSV data from load_csv function. I'll use the code from the single_plot function in plot_data.py for now to test.
def create_plot(file_path, figsize=(8, 4)):
    plot_title, df = load_csv(file_path)
    fig, ax1 = plt.subplots(figsize=figsize)

    color = "blue"
    ax1.set_xlabel("Time (UTC+09:30)")
    ax1.set_ylabel(plot_title, color=color)
    ax1.plot(df.index, df["Value (m)"], color=color, label=plot_title)
    ax1.tick_params(axis="y", labelcolor=color)
    ax1.legend(loc="best")

    # Format the date again, try just the year/m/d though rather than adding hours and minutes - re-add later if desired or we use different data than GroundwaterHeads folder.
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate(rotation=45)
    plt.tight_layout()

# Could add the code for twin plot here if we want to view those on the markers as well eventually.

# Had to use a guide online to get this to work and can reference if necessary, but found out the easiest way to do it is to store the plot in bytes 
# (a buffer) instead of converting to PNG and saving locally as a file, and then using those bytes to render the plot under the relevant marker.
# Done by encoding the image into html <img> tag as below this segment, which folium can embed in the output and load onto the map under the marker.
 
    temp = BytesIO()
    fig.savefig(temp, format="png", dpi=150)
    plt.close(fig)
    temp.seek(0)
    return temp.read()

def png_to_imgTag(png_bytes):
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return (f'<img src="data:image/png;base64,{b64}" style="max-width: 400px;"/>')    # Now in the form of an Image tag to be embedded in the html file generated as output further below  

# Using a manually made dummy index CSV file for now until we work out how to link all the data files together, 
# possibly by BoreID / finding other shared columns. Key-Pair relationships from database unit, might need a refresher
def create_map(index_csv, folder_path, output_html=''):
    index = pd.read_csv(index_csv)

    # Get the average lat / lon between the data to center the map by default (so if we use other data, the map isn't put straight on Ti Tree automatically)
    lat_center = index["lat"].mean()
    lon_center = index["lon"].mean()

    # Set the location for the folium map to these coordinates
    map = folium.Map(location=[lat_center, lon_center], zoom_start=5)

    # Iterate through the rows under each column ("ID", "Location", "Lat", "Lon")
    for i, row in index.iterrows():
        file_name = row["file_name"]
        location_name = row["location_name"]
        lat = row["lat"]
        lon = row["lon"]

        file_path = os.path.join(folder_path, file_name) # Combine file name and folder path into one, a file path.

        # Plot the CSVs and convert them to img tags by calling create_plot and png_to_imgTag functions
        png_bytes = create_plot(file_path)
        img_tag = png_to_imgTag(png_bytes)

        # Add the information to go along with the popup on the marker, must use HTML here (standard div, body, header and paragraph tags etc)
        popup_text = (f"""
        <div style="font-family: Arial, sans-serif; max-width: 450px;">
            <h4 style="margin:0 0 8px 0;">{location_name}</h4>
            {img_tag}
            <p style="font-size:12px; color:#555;"> If you're reading this, this worked finally. Need to find out where we go from here now... </p>
            <p style="font-size:12px; color:#555;"> <--- Maybe the button to get latest data from site could go here once we figure it out / ready to implement? --->        
            <button type="button">Test (no function)</button>
        </div>
        """)
        # The button & latest data feature - (would have to make sure it's by type so we don't mix and match different sources idk, 
        # maybe blue = NTG Aquatic Information, Green = NT_NaturalResourceMaps, Red / other = BoM data?)  
        # Currently popup info is shared across all markers though so would have to separate it if we need button, otherwise button = same function for every marker.

        # Generate the markers in the right locations with the right info, still under the for loop so don't need to do markers individually like earlier test. 
        
        folium.Marker(
            location = [lat, lon],
            popup = folium.Popup(popup_text, max_width=500),
            tooltip = location_name
        ).add_to(map) # Append each marker to map.

    # Save the map under the given file name below this block when calling the create_map() function.
    map.save(output_html)
    print(f"Map saved to {output_html}. Open it in your browser.")   # Print this to the terminal to both indicate success, and the name of the file to look for.

# Specify the index CSV location, and the folder path with the data CSVs (I've created a new one temporarily, "temp_CSVs", to not accidentally mess up the original datasets)
index_csv = "locations_index.csv"
folder_path = "temp_CSVs"

# Run the create_map function to generate map, then right click the generated html file and click 'Open in Integrated Browser' to view result (or open it in file explorer to view in local browser works too)
create_map(index_csv, folder_path, output_html="Folium_Marker_CSV_Test.html")





