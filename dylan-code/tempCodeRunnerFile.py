
# def create_map(output_html="foliumTestMap.html"):
#     center_lat = df["Latitude"].mean()
#     center_lon = df["Longitude"].mean()

#     map = folium.Map(location=[df.Latitude.mean(), df.Longitude.mean()], 
#                  zoom_start=3, control_scale=True)

#     folium.Marker(location=[df.Latitude.mean(), df.Longitude.mean()]).add_to(map)

#     #Loop through each row in the dataframe
#     # for i,row in df.iterrows():
#     #     #Setup the content of the popup
#     #     iframe = folium.IFrame('Well Name:' + str(row["Well Name"]))
        
#     #     #Initialise the popup using the iframe
#     #     popup = folium.Popup(iframe, min_width=300, max_width=300)
        
#     #     #Add each row to the map
#     #     folium.Marker(location=[row['Latitude'],row['Longitude']],
#     #                 popup = popup, c=row['Purpose']).add_to(map)
# folium.Marker(location=[df.Latitude.mean(), df.Longitude.mean()], 
#               icon=folium.Icon(color='red', icon='pushpin')).add_to(map)
    
#     #m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

# #    m.save(output_html)


# create_map(output_html="TestMap.html")

