"""
streamlit_climate_demo.py - a standalone preview of the climate section.

This exists so the climate work can be checked on its own, without touching the main
dashboard. The whole page is one call to climate_models.render_climate_tab(), so the same
function can later be dropped into a tab of the main app with no changes:

    import climate_models
    tab_map, tab_climate = st.tabs(["Map", "Climate"])
    with tab_climate:
        climate_models.render_climate_tab()

Launch it with:

    ~/venvs/hit401_climate/bin/python -m streamlit run climate/streamlit_climate_demo.py

It needs the files in data/climate/, which come from:

    ~/venvs/hit401_climate/bin/python climate/download_cmip6_pr.py --download
"""

import sys
from pathlib import Path

import streamlit as st

# Make sure this folder is importable even if streamlit is launched from elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import climate_models

st.set_page_config(page_title="HIT401 Group 34 - Climate preview", page_icon="🌧️",
                   layout="wide")

st.title("Climate model preview")
st.caption(
    "Standalone preview of the climate section for HIT401 Group 34. "
    "The main dashboard (krishna-code/app(v1.2).py) is not affected by this page."
)

climate_models.render_climate_tab()

with st.expander("Where this data comes from"):
    st.markdown(
        """
**Climate models** - CMIP6 monthly precipitation (`Amon`, `pr`), experiments `historical`
and `ssp245`, downloaded from the Earth System Grid Federation through the NCI and CEDA
nodes. For each location we keep only the single model grid cell nearest the point, so
each file is a few tens of kB. See `docs/climate/CITATIONS_CMIP6.md` for the model list and licence.

**Observed rainfall** - Bureau of Meteorology daily rainfall (product IDCJAC0009),
station 015643 Territory Grape Farm, the closest station to Ti Tree in our dataset.

**River flow** - NT water-course discharge for G0280010, Woodforde River at Arden Soak.

**Residual mass** - each month's total minus the long-term average for that same calendar
month, accumulated over time, after the BOM AWRA technical supplement
(https://www.bom.gov.au/water/awra/2010/documents/technical_supplement.pdf).
        """
    )
