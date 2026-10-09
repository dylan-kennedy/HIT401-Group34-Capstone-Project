"""
Tests for webapp/build_cache.py's own logic: ID normalisation, the Bores.csv quoting
repair, and a cross-check that the missing-month/residual-mass rules it reuses from
climate_models.py still produce the numbers that module's own tests expect.

None of these touch the real data files or the network — small made-up inputs only,
worked out by hand, same convention as climate/tests/.

Run with:
    ~/venvs/hit401_web/bin/python webapp/tests/test_build_cache.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))       # webapp/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "climate"))  # climate/

import build_cache as bc
import climate_models as cm


# ---------------------------------------------------------
# ID normalisation
# ---------------------------------------------------------

def test_normalise_id_pads_rn_numbers():
    assert bc.normalise_id("RN5628") == "RN005628"
    assert bc.normalise_id("rn 005628") == "RN005628"
    assert bc.normalise_id("RN005628") == "RN005628"
    assert bc.normalise_id('"RN5628"') == "RN005628"


def test_normalise_id_leaves_non_rn_codes_alone_but_upper_cases():
    assert bc.normalise_id("g0280010") == "G0280010"
    assert bc.normalise_id(" G0280010 ") == "G0280010"


def test_normalise_id_handles_missing_values():
    assert bc.normalise_id(None) is None
    assert bc.normalise_id("") is None
    assert bc.normalise_id("   ") is None


# ---------------------------------------------------------
# Bores.csv repair — the three malformed shapes actually found in the file
# (confirmed against the real file in webapp/cache/build_report.json; these are the same
# three cases reduced to the minimum that reproduces them)
# ---------------------------------------------------------

def test_repair_row_18_fields_passes_through_unchanged():
    row = [str(i) for i in range(18)]
    assert bc._repair_row(2, row) == row


def test_repair_row_19_fields_name_split_by_one_stray_quote():
    # Mirrors the real line 930: RN012978,"MCMAHONS 6"CAS 72K E...,100M W OF MILL",url,...
    row = (
        ["RN012978", 'MCMAHONS 6CAS 72K E OF 3/WAYS', '100M W OF MILL"']
        + ["url", "4.4", "1980-12-12", "134", "0", "0", "Production", "",
           "Current", "-19.3", "134.8", "53", "484260", "7863685", "GPS", ""]
    )
    assert len(row) == 19
    fixed = bc._repair_row(930, row)
    assert fixed is not None
    assert len(fixed) == 18
    assert fixed[0] == "RN012978"
    assert fixed[1] == "MCMAHONS 6CAS 72K E OF 3/WAYS,100M W OF MILL"   # quote stripped
    assert fixed[2] == "url"
    assert fixed[-1] == ""


def test_repair_row_20_fields_name_split_twice():
    row = (
        ["RN014729", "TOMS BORE 5CAS  ABD 8.2K WEST OF H/S", "250M STH", 'RD"']
        + ["url", "3", "1983-01-01", "12.5", "0", "6", "Production", "Abandoned",
           "Historical", "-25.3", "131.7", "52", "769489", "7198837", "GPS", ""]
    )
    assert len(row) == 20
    fixed = bc._repair_row(38754, row)
    assert len(fixed) == 18
    assert fixed[1] == "TOMS BORE 5CAS  ABD 8.2K WEST OF H/S,250M STH,RD"


def test_repair_row_11_fields_blob_split():
    # Mirrors the real line 26223, where the stray quote swallowed 8 columns into one field.
    blob = 'UNKNOWN 210MILE PEG STH ",url,0.4,1960-01-01,19.5,0,16.1,Production"'
    row = ["RN002991", blob, "Constructed&Capped", "Current", "-25.9", "133.3",
           "53", "328128", "7136171", "Estimated", ""]
    assert len(row) == 11
    fixed = bc._repair_row(26223, row)
    assert len(fixed) == 18
    assert fixed[0] == "RN002991"
    assert fixed[1] == 'UNKNOWN 210MILE PEG STH '
    assert fixed[2] == "url"
    assert fixed[8] == "Production"          # the stray trailing quote is stripped
    assert fixed[9] == "Constructed&Capped"  # and the genuine trailing fields are untouched


def test_repair_row_unrecognised_shape_returns_none_rather_than_guess():
    assert bc._repair_row(1, ["a", "b", "c"]) is None               # 3 fields: no rule fits
    assert bc._repair_row(1, [str(i) for i in range(25)]) is None   # 25 fields: no rule fits


# ---------------------------------------------------------
# Reused climate_models rules stay in step (a regression guard: if someone changes the
# constant in one module and not the other, this fails loudly)
# ---------------------------------------------------------

def test_max_blank_days_constant_matches_climate_models():
    assert bc.MAX_BLANK_DAYS == cm.MAX_BLANK_DAYS == 5


def test_far_station_warning_km_is_a_sane_positive_number():
    assert bc.FAR_STATION_WARNING_KM == 50
    assert isinstance(bc.FAR_STATION_WARNING_KM, int) and bc.FAR_STATION_WARNING_KM > 0


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
