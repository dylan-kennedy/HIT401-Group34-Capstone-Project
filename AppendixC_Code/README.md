# HIT401 Capstone Project — Group 34
## Towards an Interactive Groundwater Report Card for the Northern Territory
### Appendix C — Data and Source Code (Interim Report, Semester 2 2026)

Supervisor: Dr Cat Kutay. Hydrogeology adviser: Assoc. Prof. Dylan Irvine.
Group members: Dylan Kennedy, Gaurab Gaihre, Krishna Dhakal, Sachin Kharel.

---

## 1. What is in this package

| File | Produces | Report section |
|---|---|---|
| `gwrc_ingest.py` | `gwrc_tidy.csv` — every supplied export normalised into one table, plus the data-quality audit | Section IV |
| `gwrc_trends.py` | `gwrc_trend_results.csv`, `gwrc_trends.png` — per-bore trends, completeness, OLS vs Mann–Kendall check | Sections IV–V, Fig. 4-1 |
| `toolkit_demo.py` | `toolkit_demo.png` — the four core analysis functions validated on synthetic data with known answers | Section V, toolkit validation |
| `README.md` | this file | Appendix C |

## 2. Input data — not redistributed here

The analysis reads the folder **`GroundwaterHeads_20250718`**, shared by Dr Cat Kutay
on 6 August 2026 and prepared by Assoc. Prof. Dylan Irvine. It contains water-level
records for 16 unique bores (17 subfolders — RN006543 is exported twice) in the
**Ti Tree Basin, Northern Territory**, comprising 60 CSV exports and 711,627
measurements (706,752 Publish, 4,875 Field Visits) spanning 21 February 1967 to
12 December 2024. `gwrc_ingest.py` de-duplicates RN006543's repeated
LocationExport folder — the two folders hold identical data — by skipping a
folder once its bore ID has already been ingested; without this, the printed
measurement total is inflated by 92,272 records (one folder's worth) even
though the unique-bore and series counts are unaffected.

That folder is **not included in this submission**: it was supplied privately by the
client and is not ours to redistribute. Markers with access can point the scripts at
their own copy. Each per-bore subfolder contains up to four exports —
`Depth Below Ground` and `Water Elevation (AHD)`, each as a `Field Visits` series
(manual dip measurements) and a `Publish` series (approved, largely logger-derived).

Secondary public source (not required to run the scripts):
NT Government bore locations, water quality and groundwater levels,
`https://data.nt.gov.au/dataset/nt-bore-locations-water-quality-and-groundwater-levels`

## 3. Environment

Developed and tested on Python 3.11+ with:

```
pandas >= 2.0
numpy >= 1.24
scipy >= 1.10
matplotlib >= 3.7
```

Install with:

```bash
pip install pandas numpy scipy matplotlib
```

## 4. Steps to execute

```bash
# 1. Normalise the supplied exports and run the data-quality audit
python3 gwrc_ingest.py /path/to/GroundwaterHeads_20250718
#    -> writes gwrc_tidy.csv and prints defects (a)-(d) from Section IV

# 2. Trend and completeness analysis, and the report figures
python3 gwrc_trends.py gwrc_tidy.csv
#    -> writes gwrc_trend_results.csv and gwrc_trends.png

# 3. Validate the four core analysis functions against synthetic test cases
python3 toolkit_demo.py
#    -> writes toolkit_demo.png
```

## 5. Method notes

**Timestamp handling.** The dataset mixes two date formats: `RN005723`'s
`Water Elevation (AHD).Field Visits` export uses `DD/MM/YYYY` while every other file
uses `YYYY-MM-DD`. `gwrc_ingest.py` detects the format per row rather than forcing
one, so neither is silently discarded. The client's own `Load_and_plot.py` handles
this with `pd.to_datetime(..., dayfirst=True)`.

**Averaging.** Raw observations are averaged to monthly means and then to annual
means, so that years with dense logger data are not weighted more heavily than years
with a handful of manual dips.

**Trend estimation.** An ordinary least-squares fit to the annual means is the
headline figure, chosen for transparency and comparability. Annual averaging removes
the seasonal cycle and most of the serial correlation that Helsel et al. (2020) warn
would otherwise inflate significance. A Mann–Kendall test with a Sen slope is
computed alongside as a non-parametric robustness check, and `gwrc_trends.py` flags
any bore where the two methods disagree in sign or significance. Currently this
happens for 5 of the 16 bores (RN005628, RN005641, RN012581, RN016682, RN017403);
none of the 5 are among the 9 bores with a significant OLS decline, so the headline
result is unaffected, but these 5 should be treated as uncertain rather than as
having a settled trend direction.

**Series selection.** The Field Visits series is used by default because it spans the
full period of record for most bores; the Publish series is substituted for
`RN005723` because of the timestamp defect above.

**Figure.** `gwrc_trends.py` writes a single file, `gwrc_trends.png`, with two
panels: (left) the six most steeply declining bores plotted in raw m AHD, and
(right) the fitted linear trend for all 16 bores as a horizontal bar chart, red
for decline / blue for rise.

## 6. Known limitations

- The supplied folder contains **water levels only**. No abstraction/pumping series,
  no streamflow gauging record and no hydrochemistry were included, so the drawdown,
  baseflow and connectivity functions in `toolkit_demo.py` are validated against
  synthetic data only and have not yet been run on real records.
- Trends are fitted as linear. A bore with a genuine change of regime (for example a
  new extraction licence part-way through the record) will be poorly summarised by a
  single slope.
- Declining water levels are established by this analysis; **attribution** of that
  decline to licensed extraction rather than to climate is not, and requires the
  pumping data listed in Section VII of the report.

## 7. Third-party code and data acknowledgement

- Input data supplied by Assoc. Prof. Dylan Irvine (CDU) via Dr Cat Kutay; original
  records sourced from the Northern Territory Government water monitoring network.
- `Load_and_plot.py` and `Bores_with_head_data.py` in the supplied folder were written
  by D. Irvine. Our ingestion follows the same loading convention so results remain
  comparable, but the code in this package is our own.
- Libraries used are cited in the report's reference list: NumPy (Harris et al., 2020)
  and SciPy (Virtanen et al., 2020); pandas and matplotlib are used under their
  respective open-source licences.

## 8. Academic integrity

All submitted data and code comply with Charles Darwin University's Academic
Integrity Policy. Third-party code, datasets and libraries are acknowledged above and
referenced in the report. Use of generative AI is declared in Appendix B.
