#####
#
#   HIT401 - Group 34
#   "Data Plot Program (plot_data.py)"
#   Generates basic plots from the data in the GroundwaterHeads CSVs for viewing
#   
#####

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import tkinter as tk
from tkinter import filedialog
import csv

# Notes
# Data uses YYYYMMDD format


# Wrap the first style (single plot) in a function, same with twin-plot in development while testing.
# Maybe also work out what the best type of plots are to use, and all the plot options that go with them (trend lines, etc)

def single_plot():
    # Assign the CSV to be used a file path 
    
    # Uncomment for static file path, then comment out user choice block below 
    #file_path = "Datasets/GroundwaterHeads_20250718/LocationExport-RN005626-20250718020600/DataSetExport-Depth Below Ground.Field Visits@RN005626-20250718020600.csv"
    # Might need to shorten this path later as multiple datasets will be used...
    # Use a user prompt to select a CSV instead? Come back to this idea. - now below

    # User chooses the CSV file they want to plot instead
    file_path = filedialog.askopenfilename(
        title="Select your CSV data file",
        filetypes=[("CSV Files", "*.csv")]  # Strictly limits the view to CSVs only
    )

    # Is testing the data / sanitising it necessary here? Might be, I haven't done it yet but if we use this feature in main project I will add if necessary

    # Open the CSV, read the title data from cell A1 (first cell of the CSV)
    df_title = pd.read_csv(file_path, header=None, nrows=1, usecols=[0])
    plot_title = df_title.iloc[0, 0]

    # Read the data from the CSV now, skipping to Row 3 (where the column headers begin)
    # - Of course this will only work for the CSVs in 'GroundwaterHeads_20250718' parent folder,
    #   figure out data extraction by column header (looking through CSV, finding the data header 
    #   - possibly BoreID which would be RN005626 for this data, but this data starts with Timestamp rather than BoreID)
    df = pd.read_csv(
        file_path,
        skiprows=2,                            # Skipping the title and comments, starting at data column headers
        parse_dates=["Timestamp (UTC+09:30)"],  # Parse the timestamp as datetime64 objects instead of a string like '1975-10-21'       
    )

    # Set the timestamp as the index to make plotting easier
    df = df.set_index("Timestamp (UTC+09:30)")

    # Make a basic time-series plot to display the data
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df.index, df["Value (m)"], label="Value (m)")

    ax.set_xlabel("Time (UTC+09:30)")
    ax.set_ylabel("Value (m)")
    ax.set_title(plot_title)

    # Change the data formatting for the x-axis from just the year (1980, 1990, etc) to more specific like (1975-06-21). Hours & Mins might not be necessary, most of this data is blank / null.  
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    fig.autofmt_xdate(rotation=45)

    ax.legend()
    plt.tight_layout()
    plt.show()

# Plotting two sets of data against each other (hardcoded file paths still)
def twin_plot():
    # Print a message to terminal to say the twin-plot is the selected plot type being generated
    print("Plotting the twin-plot now, using RN005626 - Depth Below Ground (Field Visits) and Water Elevation (AHD)(Field Visits).")
    #print("Plotting the twin-plot now, using RN016704 - Depth Below Ground (Field Visits) and Water Elevation (AHD)(Field Visits).")
   
    #Load RN005626 CSVs for Depth Below Ground & Water Elevation (Field Visits).
    # Might need to get some different but worthwhile data to compare as well, all data in this folder is Water Elevation and Depth Below Ground.
    df_depth = pd.read_csv("Datasets/GroundwaterHeads_20250718/LocationExport-RN005626-20250718020600/DataSetExport-Depth Below Ground.Field Visits@RN005626-20250718020600.csv", skiprows=2,
                        parse_dates=["Timestamp (UTC+09:30)"]
                        ).set_index("Timestamp (UTC+09:30)")

    df_elev = pd.read_csv("Datasets/GroundwaterHeads_20250718/LocationExport-RN005626-20250718020600/DataSetExport-Water Elevation (AHD).Field Visits@RN005626-20250718020600.csv", skiprows=2,
                        parse_dates=["Timestamp (UTC+09:30)"]
                        ).set_index("Timestamp (UTC+09:30)")

    # Load a different dataset, both from RN016704
    # df_depth = pd.read_csv("Datasets/GroundwaterHeads_20250718/LocationExport-RN016704-20250718020358/DataSetExport-Depth Below Ground.Field Visits@RN016704-20250718020357.csv", skiprows=2,
    #                        parse_dates=["Timestamp (UTC+09:30)"]
    #                       ).set_index("Timestamp (UTC+09:30)")

    # df_elev = pd.read_csv("Datasets/GroundwaterHeads_20250718/LocationExport-RN016704-20250718020358/DataSetExport-Water Elevation (AHD).Field Visits@RN016704-20250718020358.csv", skiprows=2,
    #                       parse_dates=["Timestamp (UTC+09:30)"]
    #                      ).set_index("Timestamp (UTC+09:30)")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df_depth.index, df_depth["Value (m)"], label="Depth below ground (m)")
    ax.plot(df_elev.index, df_elev["Value (m)"], label="Surface water elevation (m)")

    ax.set_xlabel("Time (UTC+09:30)")
    ax.set_ylabel("Value (m)")
    ax.legend()
    plt.tight_layout()
    plt.show()

    # Comparison using twin y-axes, DBG on the left and WE on the right.
    fig, ax1 = plt.subplots(figsize=(10, 5))

    color1 = "tab:blue"
    color2 = "tab:red"
    color3 = "tab:green"
    ax1.set_xlabel("Time (UTC+09:30)")
    ax1.set_ylabel("Depth below ground (m)", color=color1)
    ax1.plot(df_depth.index, df_depth["Value (m)"], color=color1, label="Depth")
    ax1.tick_params(axis="y", labelcolor=color1)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Surface water elevation (m)", color=color2)
    ax2.plot(df_elev.index, df_elev["Value (m)"], color=color3, label="Elevation")
    ax2.tick_params(axis="y", labelcolor=color2)

    ax2.set_title("RN005626 - Depth Below Ground (m) vs Surface Water Elevation (m)")
    fig.tight_layout()
    plt.show()

# Uncomment chosen plot, comment out the other one to test each one.
single_plot()
#twin_plot()
