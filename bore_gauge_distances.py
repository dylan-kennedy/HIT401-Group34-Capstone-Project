"""
HIT401 Group 34 - distance from the Woodforde River gauge (G0280010) to every bore in
Bores_Ti_Tree.csv and locations_index.csv. Generated for item 3 (map: river + bores
within 1km) - re-run this if more points are added along the river's course, since it
currently only measures distance to the single gauge coordinate, not the full river.
"""

import csv
import math

GAUGE_LAT, GAUGE_LON = -22.367427, 133.323877  # Woodforde River - Arden Soak, G0280010
OUTPUT_FILE = "bore_gauge_distances_G0280010.csv"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    rows = []

    with open("Datasets/GroundwaterHeads_20250718/Bores_Ti_Tree.csv") as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row["Latitude"]), float(row["Longitude"])
            except (ValueError, KeyError):
                continue
            dist = haversine_km(GAUGE_LAT, GAUGE_LON, lat, lon)
            rows.append((dist, row["Bore no"].strip('"'), lat, lon, "Bores_Ti_Tree.csv"))

    with open("locations_index.csv") as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (ValueError, KeyError):
                continue
            dist = haversine_km(GAUGE_LAT, GAUGE_LON, lat, lon)
            rows.append((dist, row["file_name"], lat, lon, "locations_index.csv"))

    rows.sort(key=lambda r: r[0])

    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["distance_km", "id_or_name", "lat", "lon", "source_file"])
        for dist, ident, lat, lon, src in rows:
            writer.writerow([f"{dist:.3f}", ident, lat, lon, src])

    print(f"Saved {OUTPUT_FILE} ({len(rows)} records)")
    print(f"Nearest: {rows[0][1]} at {rows[0][0]:.3f} km")
    for thresh in (1, 5, 10, 20):
        n = sum(1 for r in rows if r[0] <= thresh)
        print(f"  <= {thresh:>2} km: {n}")


if __name__ == "__main__":
    main()
