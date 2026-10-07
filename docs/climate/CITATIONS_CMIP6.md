# CMIP6 data citations — HIT401 Group 34

Covers only the model runs actually downloaded and used in `climate_models.py`.
Compiled 7 October 2026 from `HIT401_climate_data_notes.md` and the ESGF search API at
`esgf.nci.org.au`, plus the `license` and `institution` attributes read from the data
files themselves.

Variable `pr` (precipitation), table `Amon` (monthly), experiments `historical` and
`ssp245`. For each location only the single nearest model grid cell was kept.

---

## Required acknowledgement

> We acknowledge the World Climate Research Programme, which, through its Working Group on
> Coupled Modelling, coordinated and promoted CMIP6. We thank the climate modeling groups
> for producing and making available their model output, the Earth System Grid Federation
> (ESGF) for archiving the data and providing access, and the multiple funding agencies who
> support CMIP6 and ESGF.

Terms of use for all CMIP6 output: <https://pcmdi.llnl.gov/CMIP6/TermsOfUse>

---

## Licences — read from the files we actually downloaded

`HIT401_climate_data_notes.md` says "CC BY 4.0 … per the DataCite records", and then says to
quote the `license` attribute of the files used. **Every file we downloaded states
ShareAlike, not plain CC BY**, so the note's CC BY line does not match our files:

| Licence stated in the file | Models |
|---|---|
| Creative Commons Attribution-**ShareAlike** 4.0 International (CC BY-SA 4.0) | GFDL-ESM4, ACCESS-CM2, EC-Earth3, MRI-ESM2-0, MPI-ESM1-2-LR, FGOALS-g3, GISS-E2-1-G, CMCC-ESM2, ACCESS-ESM1-5, NorESM2-MM |
| Creative Commons Attribution-**NonCommercial**-ShareAlike 4.0 International (CC BY-NC-SA 4.0) | **CNRM-CM6-1-HR** |

⚠️ **CNRM-CM6-1-HR carries a NonCommercial clause**, which the other ten do not. If any part
of this project is used commercially, that run has to be dropped or cleared separately.

FGOALS-g3's licence text names "Lawrence Livermore PCMDI" as the producer rather than CAS;
that is what the published file says, quoted here unchanged.

---

## Model runs used

`v…` is the dataset version, `gn`/`gr`/`gr1` the grid label, and the host is where we read
it from. Two runs do **not** use `r1i1p1f1`, because that variant is not published for both
experiments (see the notes column).

| Model (source_id) | Variant | Institution (institution_id) | historical | ssp245 | Notes |
|---|---|---|---|---|---|
| GFDL-ESM4 | r1i1p1f1 | NOAA-GFDL | v20190726 / gr1 / CEDA | v20180701 / gr1 / NCI | historical not on NCI |
| ACCESS-CM2 | r1i1p1f1 | CSIRO-ARCCSS | v20191108 / gn / NCI | v20191108 / gn / NCI | |
| EC-Earth3 | r1i1p1f1 | EC-Earth-Consortium | v20200310 / gr / CEDA | v20200310 / gr / NCI | historical r1i1p1f1 not on NCI |
| MRI-ESM2-0 | r1i1p1f1 | MRI | v20190222 / gn / NCI | v20190222 / gn / NCI | |
| MPI-ESM1-2-LR | r1i1p1f1 | MPI-M | v20190710 / gn / NCI | v20190710 / gn / NCI | |
| FGOALS-g3 | r1i1p1f1 | CAS | v20190818 / gn / CEDA | v20190818 / gn / NCI | NCI replica starts 1970; CEDA holds 1850 on |
| CNRM-CM6-1-HR | **r1i1p1f2** | CNRM-CERFACS | v20191021 / gr / NCI | v20191202 / gr / NCI | f1 is not published; NonCommercial licence |
| GISS-E2-1-G | **r1i1p1f2** | NASA-GISS | v20190903 / gn / NCI | v20200115 / gn / NCI | only p1 pair in both experiments; ssp245 runs to 2500, cropped to 2099 |
| CMCC-ESM2 | r1i1p1f1 | CMCC | v20210114 / gn / NCI | v20210129 / gn / NCI | |
| ACCESS-ESM1-5 | r6i1p1f1 | CSIRO | v20200529 / gn / NCI | v20200810 / gn / NCI | the slide's "r6 (v2105)" run |
| NorESM2-MM | r1i1p1f1 | NCC | v20191108 / gn / NCI | v20191108 / gn / NCI | |

Full institution names, as given in the files:

- **NOAA-GFDL** — National Oceanic and Atmospheric Administration, Geophysical Fluid Dynamics Laboratory, Princeton, NJ 08540, USA
- **CSIRO-ARCCSS** — CSIRO (Aspendale, Victoria 3195, Australia) and ARCCSS (Australian Research Council Centre of Excellence for Climate System Science)
- **EC-Earth-Consortium** — AEMET Spain; BSC Spain; CNR-ISAC Italy; DMI Denmark; ENEA Italy; FMI Finland; Geomar Germany; ICHEC Ireland; ICTP Italy; IDL Portugal; IMAU Netherlands; and other European partners
- **MRI** — Meteorological Research Institute, Tsukuba, Ibaraki 305-0052, Japan
- **MPI-M** — Max Planck Institute for Meteorology, Hamburg 20146, Germany
- **CAS** — Chinese Academy of Sciences, Beijing 100029, China
- **CNRM-CERFACS** — CNRM (Centre National de Recherches Météorologiques, Toulouse 31057, France) and CERFACS
- **NASA-GISS** — Goddard Institute for Space Studies, New York, NY 10025, USA
- **CMCC** — Fondazione Centro Euro-Mediterraneo sui Cambiamenti Climatici, Lecce 73100, Italy
- **CSIRO** — Commonwealth Scientific and Industrial Research Organisation, Aspendale, Victoria 3195, Australia
- **NCC** — NorESM Climate modeling Consortium: CICERO, MET-Norway and partners

---

## Dataset DOIs

### Taken from `HIT401_climate_data_notes.md`

These were recorded in the notes as verified on DataCite. They were **not re-checked in this
session**, because DataCite is outside the hosts we were allowed to contact.

- Krasting, J. P. et al. (2018). *NOAA-GFDL GFDL-ESM4 model output prepared for CMIP6 CMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.1407>
- John, J. G. et al. (2018). *NOAA-GFDL GFDL-ESM4 model output prepared for CMIP6 ScenarioMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.1414>
- Yukimoto, S. et al. (2019). *MRI MRI-ESM2.0 model output prepared for CMIP6 CMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.621>
- Yukimoto, S. et al. (2019). *MRI MRI-ESM2.0 model output prepared for CMIP6 ScenarioMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.638>
- Wieners, K.-H. et al. (2019). *MPI-M MPI-ESM1.2-LR model output prepared for CMIP6 CMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.742>
- Wieners, K.-H. et al. (2019). *MPI-M MPI-ESM1.2-LR model output prepared for CMIP6 ScenarioMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.793>
- Ziehn, T. et al. (2019). *CSIRO ACCESS-ESM1.5 model output prepared for CMIP6 CMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.2288>
- Ziehn, T. et al. (2019). *CSIRO ACCESS-ESM1.5 model output prepared for CMIP6 ScenarioMIP.* ESGF. <https://doi.org/10.22033/ESGF/CMIP6.2291>

### UNVERIFIED — no DOI available to us

The notes carry no DOI for these seven models, and the ESGF search records returned an
empty `license` field and no DOI field. **No DOI has been invented for them.** Each
`citation_url` below came from the ESGF search API and is where the citation record,
including the DOI, can be read; none of these pages was opened in this session, so treat
every entry as UNVERIFIED until someone checks it.

| Model | Status | citation_url (from the ESGF search API, not opened) |
|---|---|---|
| ACCESS-CM2 | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.CSIRO-ARCCSS.ACCESS-CM2.historical.r1i1p1f1.Amon.pr.gn.v20191108.json` and the matching `ScenarioMIP…ssp245…` record |
| EC-Earth3 | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.EC-Earth-Consortium.EC-Earth3.historical.r1i1p1f1.Amon.pr.gr.v20200310.json` and the ssp245 record |
| FGOALS-g3 | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.CAS.FGOALS-g3.historical.r1i1p1f1.Amon.pr.gn.v20190818.json` and the ssp245 record |
| CNRM-CM6-1-HR | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.CNRM-CERFACS.CNRM-CM6-1-HR.historical.r1i1p1f2.Amon.pr.gr.v20191021.json` and the ssp245 record |
| GISS-E2-1-G | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.NASA-GISS.GISS-E2-1-G.historical.r1i1p1f2.Amon.pr.gn.v20190903.json` and the ssp245 record |
| CMCC-ESM2 | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.CMCC.CMCC-ESM2.historical.r1i1p1f1.Amon.pr.gn.v20210114.json` and the ssp245 record |
| NorESM2-MM | **UNVERIFIED** | `cera-www.dkrz.de/WDCC/meta/CMIP6/CMIP6.CMIP.NCC.NorESM2-MM.historical.r1i1p1f1.Amon.pr.gn.v20191108.json` and the ssp245 record |

Per-dataset ES-DOC pages (also unopened) follow the pattern
`https://furtherinfo.es-doc.org/CMIP6.<institution_id>.<source_id>.historical.none.<variant>`.

---

## Supporting references

- O'Neill, B. C. et al. (2016). The Scenario Model Intercomparison Project (ScenarioMIP) for CMIP6. *Geoscientific Model Development* 9, 3461–3482. <https://gmd.copernicus.org/articles/9/3461/2016/>
- Eyring, V. et al. (2016). Overview of the Coupled Model Intercomparison Project Phase 6 (CMIP6) experimental design and organization. *Geoscientific Model Development* 9, 1937–1958.

## Observed data used alongside the models

- **Rainfall** — Bureau of Meteorology, daily rainfall product IDCJAC0009, station 015643 (Territory Grape Farm, NT), 1 Jan 1987 to 17 Sep 2026. <https://www.bom.gov.au/climate/data/>
- **River flow** — NT Department of Lands, Planning and Environment, water-course discharge, station G0280010 (Woodforde River at Arden Soak), 1974 to 2026.
- **Residual mass method** — Bureau of Meteorology, *AWRA technical supplement* (2010). <https://www.bom.gov.au/water/awra/2010/documents/technical_supplement.pdf>

## Runs on the supervisor's slide 31 that we could not match

Four rows are marked "coupled" and we could not tell which published run they are, so they
were not downloaded and are not cited: CNRM-CM6-1-HR (coupled), ACCESS-ESM1-5 r20
(coupled v2112), NorESM2-MM (coupled), ACCESS-ESM1-5 r40 (coupled v2112).
