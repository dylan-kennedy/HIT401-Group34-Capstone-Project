# AI usage log — HIT401 Group 34

For the AI declaration form. Records where generative AI was used in the climate-modelling
part of this project, what was asked, and what came out.

**Tools used:** Claude Code (Anthropic's command-line coding tool), running the Claude
model, inside VS Code.
**Operator:** Sachin Kharel.
**Charts:** the chart designs replicate the style of slides 28–31 of "The wet season that
was" by A/Prof Dylan Irvine, Charles Darwin University. The layout, colours and wording of
the titles follow his slides; all numbers plotted are computed from data our group
downloaded. No chart carries his name as author; each carries the credit line
"Data: CMIP6 (ESGF). Chart design after D. Irvine, CDU."

---

## Session 1 — 7 October 2026

One working session, run as a conversation with Claude Code. The operator set standing
safety rules at the start: read-only until told otherwise, ask before touching any existing
file, new files only unless approved, no git commands that change anything, and stop rather
than guess.

### How the prompts below are recorded

The prompts are reproduced from the conversation in order. They are **summaries written
after the fact**, not verbatim transcripts, except where marked *verbatim*. The two long
batch instructions were pasted by the operator as single messages; their task lists are
reproduced closely but condensed. Nothing in this log was generated without the operator
asking for it.

| # | Prompt (summarised unless marked) | What the AI produced |
|---|---|---|
| 1 | Safety rules plus the brief: reproduce the climate graphs from slides 28–31 for Darwin, add Ti Tree versions and a rainfall residual mass graph. Stay read-only first; summarise how the app loads data and draws the map. | A read-only review of `krishna-code/app(v1.2).py` and `Datasets/`, a summary of the data loading and the folium map, and a list of questions. No files touched. |
| 2 | Answers on the credit line, the trailing moving mean, the last water year and the reference shading; sampled slide colours confirmed; asked for a plan and the first file. | A plan, the sampled colours (#3B87CA, #BB274E, #E6E6E6) read from the slide images, and a proposal for `download_cmip6_pr.py`. |
| 3 | Approved `download_cmip6_pr.py`; chose gap option A (more than 5 blank days = missing month); asked which NT station suits Ti Tree. | `download_cmip6_pr.py` created. A dry run showed which model runs are on ESGF. Station 015643 (Territory Grape Farm) reported with its gaps. |
| 4 | Decisions on model variants: use CNRM r1i1p1f2, search CEDA for a matching EC-Earth3 and GISS pair, check the EC-Earth3 file coverage. | The downloader was fixed (the API spells the service `OPENDAP`; the search limit of 200 was hiding files) and the host fallback added. All 11 non-coupled runs then resolved. |
| 5 | Asked for the full file contents, a check for any host or write location outside the allowed ones, and extra download guards. | Guards added: estimated bytes printed before each read, a 100 MB per-read and 500 MB total cap, three retries with timeouts, and a host allow-list. A check found nothing written outside `data/climate/`. |
| 6 | Approved running `--coords`. | Nearest grid cells reported for Darwin and Ti Tree for all 11 runs. Darwin and Ti Tree share no cell in any model. |
| 7 | **Batch 1** (*close to verbatim, condensed*): fix the FGOALS grid spacing; download stage 1 then stage 2; run sanity checks with a stop condition; write `climate_models.py` with the data functions; write tests; add the first two plot functions and save Darwin previews. | 44 model files downloaded (2.1 MB transferred). `climate_models.py` and `tests/test_climate_models.py` written; 11 tests pass. Four Darwin preview charts generated. Found that NCI's FGOALS-g3 replica starts in 1970 rather than 1850. |
| 8 | **Batch 2** (*close to verbatim, condensed*): re-download FGOALS from CEDA; test how sensitive CMCC-ESM2 is to the grid cell; build the Ti Tree charts; build rainfall and river-flow residual mass with tests; build a Streamlit demo; write this log and the citations file. | FGOALS re-downloaded (now 1850–2099). A 3×3 cell test for CMCC-ESM2. Ti Tree charts. Residual mass code for BOM rainfall and G0280010 flow, plus 12 more tests. `streamlit_climate_demo.py`. This file and `CITATIONS_CMIP6.md`. |

| 9 | **Batch 3** (*close to verbatim, condensed*): tidy up the Batch 2 loose ends; add an observed water-year chart; choose bores near the gauge; build a three-panel figure, lag charts and a seasonal chart; wire them into the Streamlit tab; add tests; write a README. | The data check turned into a repeatable script that reports model extremes as INFO rather than failures. Observed water-year, three-panel, lag and seasonal charts added. Three bores chosen and justified. 11 more tests. `README_climate.md` and `HANDOVER_climate.md` written. |

### A file produced by a different AI tool

`docs/climate/climate_data_notes.md` was **not** written in the session above. It was
produced earlier by an AI browser assistant, which researched where CMIP6 data could be
obtained and compiled the source comparison, the example URLs, the expected file sizes and
the draft citation list. It was supplied to this session as background material and used
as the starting point for `CITATIONS_CMIP6.md`.

Two of its statements were checked against the downloaded files and corrected: the licence
is CC BY-SA 4.0 rather than CC BY 4.0, and CNRM-CM6-1-HR is CC BY-NC-SA 4.0. The DOIs it
lists were carried across unchanged and have not been independently verified here; models
with no DOI in those notes are marked UNVERIFIED in the citations file.

### Files the AI wrote

New files, all created in this session:

- `download_cmip6_pr.py` — downloads one CMIP6 grid cell per location over OPeNDAP
- `climate_models.py` — water-year totals, anomalies, percent changes, residual mass, the plots and the Streamlit tab
- `streamlit_climate_demo.py` — standalone preview page
- `tests/test_climate_models.py` — 11 tests
- `tests/test_residual_mass.py` — 12 tests
- `tests/test_observed_analysis.py` — 11 tests (water-year rule, lag alignment, seasons)
- `tests/check_downloaded_data.py` — data-quality report on the downloaded files
- `README_climate.md` — how to run everything, and the limitations
- `HANDOVER_climate.md` — proposed changes to shared files, written out but NOT applied
- `AI_LOG.md` (this file) and `CITATIONS_CMIP6.md`
- `data/climate/*.nc` — 44 downloaded cell files, plus 18 in `data/climate/sensitivity/`
- `outputs/climate_preview/*.html` — preview charts

No file that existed before this session was edited, renamed or deleted. In particular
`krishna-code/app(v1.2).py`, everything under `Datasets/`, and `requirements.txt` are
untouched. No git command that changes the repository was run.

### Judgement calls the AI made, which a human should check

1. **Historical records are cut at December 2014** and the scenario run is used from
   January 2015. FGOALS-g3 publishes historical months through 2016, which would otherwise
   be double-counted.
2. **The 10-year moving mean is trailing**, computed on the full series from 1850 and then
   cropped to 1975, so the line has a complete window at the left edge. The slides do not
   state which convention they used.
3. **The moving mean is drawn as an anomaly** (the reference mean subtracted) so it shares
   the bar axis, matching how the slides look.
4. **Two model variants differ from the slides**: CNRM-CM6-1-HR and GISS-E2-1-G use
   `r1i1p1f2`, because `r1i1p1f1` is not published for both experiments.
5. **A month counts as missing when more than 5 days are blank**, and a missing month adds
   zero to the residual mass curve.
6. **River flow is integrated with the trapezoidal rule** over the actual, irregular
   intervals; a flow month is missing when more than 5 of its days are uncovered.
7. **Four "coupled" runs on slide 31 were not identified** and are absent from our charts.
8. **An observed water year is dropped if more than 2 of its months are missing.** A year
   short 1 or 2 months is kept, with those months filled using that calendar month's
   long-term average rather than zero, and is marked on the chart.
9. **Bores were chosen by distance to the river gauge**, keeping only those with at least
   10 years of record since 2010 across at least 40 separate months. No bore within 10 km
   qualified, so the nearest usable ones are 25.9-33.5 km away.
10. **The lag charts use anomalies and month-to-month differences**, not raw series, to
    avoid a correlation that only reflects the shared seasonal cycle or a shared trend.
    A lag backed by fewer than 24 paired months is never reported as the strongest.

### Verification done

- 34 automated tests, all passing, plus a data-quality report over the downloaded files.
- The Streamlit preview was started headless and checked for errors, then stopped.
- Downloaded files checked for missing months, duplicate months, NaN, negative values and
  calendar handling.
- Our Darwin and Ti Tree figures deliberately differ from the supervisor's slides; nothing
  was adjusted to make them agree. The differences are reported rather than hidden.
