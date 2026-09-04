# -*- coding: utf-8 -*-
"""
Created on Fri Jul 18 10:40:28 2025

@author: dirvine
"""

import os
import re
import pandas as pd
import matplotlib.pyplot as plt

#%% plot settings

plt.style.use('default')
plt.rc("axes", linewidth=0.5)
plt.rcParams.update({'font.size': 10})
plt.rcParams.update({'legend.labelspacing': 0.1})
plt.matplotlib.rc('font', **{'sans-serif': 'Arial', 'family': 'sans-serif'})
plt.rcParams['lines.linewidth'] = 1
plt.rcParams['xtick.direction'] = 'inout'
plt.rcParams['ytick.direction'] = 'inout'

#%% set root path (contains all subfolders)
root_path = r'C:\Users\dirvine\OneDrive - Charles Darwin University\Projects\Ti_Tree\Bores\GroundwaterHeads_20250718'
output_folder = root_path  # Save all plots here

# Ensure output directory exists
os.makedirs(output_folder, exist_ok=True)

#%% get all subfolders
subfolders = [os.path.join(root_path, f) for f in os.listdir(root_path)
              if os.path.isdir(os.path.join(root_path, f))]

print(f"Found {len(subfolders)} subfolders.")

#%% loop over each subfolder
for folder_path in subfolders:
    print(f"\n--- Processing folder: {folder_path} ---")

    files = os.listdir(folder_path)
    field_visits_file = None
    publish_file = None
    bore_id = None

    for f in files:
        if f.endswith(".csv") and "(AHD)" in f:
            if "Field Visits" in f:
                field_visits_file = f
            elif "Publish" in f:
                publish_file = f
            if not bore_id:
                match = re.search(r'@RN\d{6}-', f)
                if match:
                    bore_id = match.group(0)[1:-1]  # Remove @ and -

    print("Field Visits file:", field_visits_file)
    print("Publish file:", publish_file)
    print("Bore ID:", bore_id)

    if not bore_id or not (field_visits_file and publish_file):
        print("  ⚠️ Skipping: Required files not found or bore ID missing.")
        continue

    # --- PUBLISH FILE ---
    try:
        publish_path = os.path.join(folder_path, publish_file)
        df_pub = pd.read_csv(publish_path, skiprows=2)
        print(f"Header of Publish file:\n{df_pub.columns.tolist()}")
        df_pub = df_pub.iloc[:, [0, 2]].dropna()
        df_pub.iloc[:, 0] = pd.to_datetime(df_pub.iloc[:, 0], dayfirst=True, errors='coerce')
        df_pub = df_pub.dropna(subset=[df_pub.columns[0]])
        df_pub = df_pub.set_index(df_pub.columns[0])
        df_pub = df_pub.resample('D').mean()
    except Exception as e:
        print(f"  ⚠️ Error processing Publish file: {e}")
        continue

    # --- FIELD VISITS FILE ---
    try:
        visits_path = os.path.join(folder_path, field_visits_file)
        df_visits = pd.read_csv(visits_path, skiprows=2)
        print(f"Header of Field Visits file:\n{df_visits.columns.tolist()}")
        df_visits = df_visits.iloc[:, [0, 2]].dropna()
        df_visits.iloc[:, 0] = pd.to_datetime(df_visits.iloc[:, 0], dayfirst=True, errors='coerce')
        df_visits = df_visits.dropna(subset=[df_visits.columns[0]])
        df_visits = df_visits.set_index(df_visits.columns[0])
        df_visits = df_visits.resample('D').mean()
    except Exception as e:
        print(f"  ⚠️ Error processing Field Visits file: {e}")
        continue

    #%% plot
    fig, ax = plt.subplots(figsize=(17.5 / 2.54, 8 / 2.54))  # cm to inches
    ax.plot(df_pub.index, df_pub['Value (m)'], label='Logger data', linewidth=1.5,  zorder = 1)
    ax.plot(df_visits.index, df_visits['Value (m)'], 'o', label='Field visits', markersize=5, markeredgewidth=0, alpha=0.7, zorder=5)
    ax.set_title(bore_id)
    ax.set_xlabel("Date")
    ax.set_ylabel("Head (mAHD)")
    ax.legend()
    fig.tight_layout()

    # Save plot in root directory
    output_path = os.path.join(output_folder, f"{bore_id}.png")
    plt.savefig(output_path)
    plt.close(fig)
    print(f"  ✅ Plot saved to {output_path}")
