#####
#
#   HIT401 - Group 34
#   "Folium Test (folium-test.py)"
#   see description below
#   
#####

# Research suggested that folium is a good library to use for what we want to achieve, but Tkinter is also a valid option we could explore. 
# 
# This program is for testing folium as a potential way to hopefully improve how easily someone with minimal technical knowledge can access the water information,
# by trying to generate a map, place markers on it, incorporate using CSV data, and eventually load the data plots we create from the CSVs 
#    + render it on the screen under the markers (our goals for now).
#
#  

# Testing a simple map with some markers at the lat + lon from three of the datasets (using hardcoded values, not extracted from CSV)

import folium

# Setting start coordinates close to the lat + lon that will be used by the markers, saves time searching for them if map starts somewhere else.
map_center = [-22.17, 133.75]
mymap = folium.Map(location=map_center, zoom_start=5)

# Create three markers, good test range I guess
# Lat / Lon slightly off from recorded values to space out the markers while testing.
marker1 = folium.Marker(
        location=(-22.163176, 133.441561), 
        popup=(f"Marker 1 here - Depth Below Ground Field Visit Data"), 
        tooltip="Click for Details", 
        icon=folium.Icon(color="red", icon="info-sign")
    ).add_to(mymap)

marker2 = folium.Marker(
        location=(-22.163176, 134.441561),              
        popup=(f"Marker 2 here - WE Field Visit Data"), 
        tooltip="Click for Details", 
        icon=folium.Icon(color="green", icon="info-sign")
    ).add_to(mymap)

marker3 = folium.Marker(
        location=(-21.23014, 133.401658), 
        popup=(f"Marker 3 here - Depth Below Ground Field Visit Data"), 
        tooltip="Click for Details", 
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(mymap)

# Save the map to an HTML file, then open with integrated browser or open HTML file in local browser. 
mymap.save("Folium_Test.html")
print("The map has successfully been created, look for 'Folium_Test.html' now.") # Print a success statement if this works

# Attempt loading CSV data into a marker later in here or mainprojectcode instead, come back to this*