# -*- coding: utf-8 -*-
"""
Created on Fri Jul 18 11:23:45 2025

@author: dirvine
"""

import os
import csv

# Set the folder to search
folder_path = r'C:\Users\dirvine\OneDrive - Charles Darwin University\Projects\Ti_Tree\Bores\GroundwaterHeads_20250718'  # <- Change as needed

# Get all .png files
png_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]

# Strip extensions
filenames_no_ext = [os.path.splitext(f)[0] for f in png_files]

# Output CSV path
output_csv = os.path.join(folder_path, "head_time_series_bores.csv")

# Write to CSV
with open(output_csv, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Bore ID"])  # Optional header
    for name in filenames_no_ext:
        writer.writerow([name])

print(f"✅ CSV written to: {output_csv}")
