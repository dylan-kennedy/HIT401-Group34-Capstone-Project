"""
Tests for webapp/server.py's API, run in-process against the real caches built by
build_cache.py (so this only works after that script has been run at least once — same
requirement as running the server itself).

Covers: a known bore with data, a bore with none, a gauge, a BOM station, a place with
nothing nearby, search (a hit and a miss), and the two climate endpoints — using FastAPI's
TestClient (httpx under the hood), no real network socket needed.

Run with:
    ~/venvs/hit401_web/bin/python webapp/tests/test_api.py
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # webapp/

warnings.filterwarnings("ignore", category=DeprecationWarning)    # the httpx/TestClient notice

import server
from fastapi.testclient import TestClient

client = TestClient(server.app)


# ---------------------------------------------------------
# /api/meta and /api/locations
# ---------------------------------------------------------

def test_meta_counts_are_internally_consistent():
    data = client.get("/api/meta").json()
    counts = data["counts"]
    assert counts["bores"] > 40000                      # NT-wide, not just Ti Tree
    assert counts["bores_with_water_level"] == 16        # the real-files number, not 48
    assert counts["bores_claiming_water_level"] == 48
    assert counts["bores_with_water_level"] < counts["bores_claiming_water_level"]
    assert counts["bom_stations_nt"] == 2
    assert counts["bom_stations"] == 11


def test_locations_payload_has_all_three_types_and_matches_meta_counts():
    locations = client.get("/api/locations").json()
    meta = client.get("/api/meta").json()
    assert len(locations["bores"]) == meta["counts"]["bores"]
    assert len(locations["gauges"]) == meta["counts"]["river_stream_gauges"]
    assert len(locations["bom_stations"]) == meta["counts"]["bom_stations"]
    assert all(b["type"] == "bore" for b in locations["bores"][:5])


def test_locations_response_is_gzip_encoded_when_accepted():
    resp = client.get("/api/locations", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"


# ---------------------------------------------------------
# a known bore WITH data (RN006543 — water level + water quality + monitoring)
# ---------------------------------------------------------

def test_known_bore_with_data():
    resp = client.get("/api/location/bore/RN006543")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["data_available"]["water_quality"] is True
    assert detail["data_available"]["water_level"] is True
    assert detail["data_available"]["monitoring_location"] is True
    assert len(detail["water_quality_summary"]) > 0
    assert any("newer" in n for n in detail["data_quality_notes"])   # the duplicate-folder note


def test_known_bore_water_quality_series_has_points():
    resp = client.get("/api/water-quality/RN006543", params={"parameter": "TDS"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dates"]) == len(data["values"]) > 0


def test_known_bore_water_level_series_has_points():
    resp = client.get("/api/water-level/RN006543")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["months"]) > 100     # this bore's record runs back to 1974


# ---------------------------------------------------------
# a bore with NO special data at all
# ---------------------------------------------------------

def test_bore_with_no_data_returns_a_clear_checklist_not_an_error():
    bores = server.BORES
    plain = bores[~bores["has_water_level"] & ~bores["has_water_quality"]
                  & ~bores["is_monitoring_location"]].iloc[0]["bore_no"]
    resp = client.get(f"/api/location/bore/{plain}")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["data_available"]["water_quality"] is False
    assert detail["data_available"]["water_level"] is False
    assert detail["water_quality_summary"] == []


def test_bore_claiming_water_level_but_missing_says_so():
    bores = server.BORES
    claimed_missing = bores[bores["water_level_claimed"] & ~bores["has_water_level"]]
    assert len(claimed_missing) == 32          # the 48-vs-16 gap, exactly
    bore_id = claimed_missing.iloc[0]["bore_no"]
    detail = client.get(f"/api/location/bore/{bore_id}").json()
    assert detail["data_available"]["water_level_claimed_but_missing"] is True
    assert any("not in this project's data" in n for n in detail["data_quality_notes"])


def test_unknown_bore_is_404_not_500():
    resp = client.get("/api/location/bore/RN999999")
    assert resp.status_code == 404


# ---------------------------------------------------------
# a gauge and a BOM station
# ---------------------------------------------------------

def test_flow_gauge_has_a_quality_warning():
    resp = client.get("/api/location/gauge/G0280010")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["data_available"]["flow_series"] is True
    assert detail["flow_quality"]["headline_warning"] is not None


def test_gauge_without_a_series_says_so_plainly():
    other_gauge = server.GAUGES[server.GAUGES["station_id"] != "G0280010"].iloc[0]["station_id"]
    detail = client.get(f"/api/location/gauge/{other_gauge}").json()
    assert detail["data_available"]["flow_series"] is False
    assert any("no discharge time series" in n for n in detail["data_quality_notes"])


def test_non_nt_bom_station_is_flagged():
    non_nt = server.BOM_STATIONS[~server.BOM_STATIONS["is_nt"]].iloc[0]["station"]
    detail = client.get(f"/api/location/bom_station/{non_nt}").json()
    assert any("not in the Northern Territory" in n for n in detail["data_quality_notes"])


def test_nt_bom_station_has_no_not_nt_flag():
    nt_station = server.BOM_STATIONS[server.BOM_STATIONS["is_nt"]].iloc[0]["station"]
    detail = client.get(f"/api/location/bom_station/{nt_station}").json()
    assert detail["data_quality_notes"] == []


# ---------------------------------------------------------
# a place with nothing nearby, and the far-station warning
# ---------------------------------------------------------

def test_place_far_from_everything_gets_a_far_warning():
    resp = client.get("/api/place", params={"lat": -10.0, "lon": 110.0})   # middle of the ocean
    assert resp.status_code == 200
    data = resp.json()
    assert data["nearby"]["bores"][0]["distance_km"] > 1000
    assert data["nearby"]["nt_bom_station"]["far_warning"] is True
    assert data["aquifer_context"]["inside_ti_tree_basin"] is False


def test_place_inside_ti_tree_basin_has_aquifer_context():
    # G0280010's own coordinates are inside the Ti Tree basin.
    gauge = server.GAUGES[server.GAUGES["station_id"] == "G0280010"].iloc[0]
    resp = client.get("/api/place", params={"lat": gauge["lat"], "lon": gauge["lon"]})
    data = resp.json()
    assert data["aquifer_context"]["inside_ti_tree_basin"] is True


# ---------------------------------------------------------
# search
# ---------------------------------------------------------

def test_search_hit_returns_the_right_bore():
    data = client.get("/api/search", params={"q": "RN006543"}).json()
    assert data["results"][0]["id"] == "RN006543"
    assert data["results"][0]["type"] == "bore"


def test_search_miss_explains_the_scope_rather_than_returning_empty():
    data = client.get("/api/search", params={"q": "zzz_definitely_not_in_here"}).json()
    assert len(data["results"]) == 1
    assert data["results"][0]["type"] == "none"
    assert "town or state" in data["results"][0]["label"]


# ---------------------------------------------------------
# climate (reused from climate_models.py, no plotly needed server-side)
# ---------------------------------------------------------

def test_climate_meta_lists_both_locations():
    data = client.get("/api/climate/meta").json()
    assert data["available"] is True
    assert set(data["locations"].keys()) == {"Darwin", "Ti Tree"}


def test_climate_anomaly_chart_has_data_for_every_usable_run():
    meta = client.get("/api/climate/meta").json()
    run = meta["locations"]["Darwin"]["usable_runs"][0]
    data = client.get("/api/climate/anomaly", params={"location": "Darwin", "run": run}).json()
    assert len(data["years"]) == len(data["anomaly_mm"]) > 0
    assert data["years"][0] >= 1975    # charts start at FIRST_PLOT_YEAR


def test_climate_wetter_drier_sorts_and_counts_correctly():
    data = client.get("/api/climate/wetter-drier", params={"location": "Ti Tree"}).json()
    assert data["models_total"] == len(data["labels"])
    assert data["models_wetter"] == sum(1 for v in data["mean_pct"] if v > 0)


def test_climate_unknown_location_is_400_not_500():
    resp = client.get("/api/climate/anomaly", params={"location": "Nowhere", "run": "GFDL-ESM4"})
    assert resp.status_code == 400


def test_climate_seasonal_ti_tree_has_observed_and_models():
    resp = client.get("/api/climate/seasonal", params={"location": "Ti Tree"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["observed"] is not None
    assert len(data["observed"]["years"]) > 0
    assert len(data["observed"]["wet"]) == len(data["observed"]["years"])
    assert len(data["models"]) > 0
    assert data["figure"] is not None


def test_climate_seasonal_darwin_handles_missing_observed():
    resp = client.get("/api/climate/seasonal", params={"location": "Darwin"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["observed"] is None
    assert len(data["models"]) > 0


def test_climate_lag_rainfall_returns_correlations():
    resp = client.get("/api/climate/lag", params={"driver": "rainfall"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["driver"] == "Rainfall"
    assert len(data["lags"]) == data["max_lag"] + 1
    assert len(data["r"]) == len(data["lags"])
    assert data["figure"] is not None


def test_climate_lag_flow_returns_correlations():
    resp = client.get("/api/climate/lag", params={"driver": "flow"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["driver"] == "River flow"
    assert len(data["lags"]) == data["max_lag"] + 1


def test_climate_lag_unknown_driver_is_400():
    resp = client.get("/api/climate/lag", params={"driver": "invalid_driver"})
    assert resp.status_code == 400


def test_climate_lag_unknown_bore_is_404():
    resp = client.get("/api/climate/lag", params={"bore_id": "RN9999999"})
    assert resp.status_code == 404


def test_climate_rain_flow_bores_returns_figure_and_rows():
    resp = client.get("/api/climate/rain-flow-bores", params={"start": "2010-01"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["bores"]) > 0
    assert data["figure"] is not None
    assert len(data["rows"]) > 0
    assert "month" in data["rows"][0]
    assert "rainfall_total_mm" in data["rows"][0]
    assert "flow_total_ML" in data["rows"][0]


# ---------------------------------------------------------
# Legacy App Features: KPI banner and statistics calculations
# ---------------------------------------------------------

def test_meta_contains_study_area_and_wq_samples():
    data = client.get("/api/meta").json()
    assert "study_area" in data
    sa = data["study_area"]
    assert sa["bores"] == 415
    assert sa["quality_bores"] == 272
    assert sa["quality_samples"] == 1185
    assert sa["monitoring_bores"] == 126
    assert sa["active_monitoring_bores"] == 36
    assert len(sa["bore_ids"]) == 415
    assert "RN006543" in sa["bore_ids"]
    assert data["counts"]["water_quality_samples"] == 84769


def test_water_quality_series_returns_statistics_card_data():
    resp = client.get("/api/water-quality/RN006543", params={"parameter": "TDS"})
    assert resp.status_code == 200
    data = resp.json()
    assert "statistics" in data
    stats = data["statistics"]
    assert stats is not None
    assert "min" in stats and "max" in stats and "mean" in stats and "median" in stats and "count" in stats
    assert stats["count"] == len(data["values"])
    assert stats["min"] <= stats["median"] <= stats["max"]
    assert stats["min"] <= stats["mean"] <= stats["max"]


def test_water_level_series_returns_statistics_card_data():
    resp = client.get("/api/water-level/RN006543")
    assert resp.status_code == 200
    data = resp.json()
    assert "statistics" in data
    stats = data["statistics"]
    assert stats is not None
    assert "min" in stats and "max" in stats and "mean" in stats and "median" in stats and "count" in stats
    assert stats["min"] <= stats["median"] <= stats["max"]


# ---------------------------------------------------------
# static page
# ---------------------------------------------------------

def test_index_page_serves():
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"HIT401" in resp.content


# ---------------------------------------------------------
# allow running without pytest
# ---------------------------------------------------------

if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"\n{failures} failure(s)")
    sys.exit(1 if failures else 0)
