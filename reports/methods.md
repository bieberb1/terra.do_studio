# Methods

<!-- Source files: data/raw/, data/processed/combined.csv, reports/eda_stats_new.csv, reports/qa_checks.csv -->
<!-- Pipeline scripts: src/ingest.py, src/clean.py, src/eda.py, src/qa.py, src/dashboard.py -->

## 1. Research Question

This analysis evaluates peak energy usage by county and building type using simulated commercial
building stock data, comparing existing baseline conditions against a technology upgrade scenario.

---

## 2. Data Source

**Dataset**: End-Use Load Profiles for the U.S. Building Stock — ComStock AMY2018 Release 1
(published 2021, accessed 2026).

**Published by**: National Renewable Energy Laboratory (NREL) via the Open Energy Data Initiative
(OEDI) Data Lake (AWS S3 bucket: `oedi-data-lake`).

**Reference path**:
```
nrel-pds-building-stock/end-use-load-profiles-for-us-building-stock/2021/comstock_amy2018_release_1/
```

**Documentation**: NREL End-Use Load Profiles project website
(https://www.nrel.gov/buildings/end-use-load-profiles.html); dataset README at
`data/raw/README.md`.

### 2.1 Dataset Overview

ComStock models the U.S. commercial building stock using OpenStudio/EnergyPlus building energy
simulation. Each record in the timeseries aggregates represents the sum of energy consumption
across all simulated buildings of a given type within a geographic unit, at 15-minute resolution.
The `comstock_amy2018_release_1` dataset uses Actual Meteorological Year (AMY) 2018 weather data
derived from NOAA ISD, NSRDB, and MesoWest sources, making it appropriate for analyses where
realistic weather-event synchronisation across locations is important.

**Simulation engine**: OpenStudio / EnergyPlus
**Weather year**: AMY 2018 (calendar year 2018)
**Building stock represented**: U.S. commercial building stock (circa 2018 construction vintage)

---

## 3. Geographic Scope

Three U.S. counties were selected to represent distinct climate regions:

| County | State | GISJOIN | Climate Context |
|---|---|---|---|
| Orange County | CA | G0600590 | Warm, coastal (Southern California) |
| Denver County | CO | G0800310 | Semi-arid, continental (high-elevation) |
| Washtenaw County | MI | G2601610 | Cold, humid (Great Lakes) |

Geographic identifiers follow the GISJOIN convention (U.S. Census county codes with leading
state FIPS prefix).

> **Note**: County-level aggregates in sparsely-populated counties may have low model counts,
> potentially producing unrealistic load profiles. The `models_used` column in the raw files
> records how many building energy models contributed to each aggregate; this was reviewed
> during QA (see Section 7).

---

## 4. Upgrade Scenarios

Two upgrade scenarios were obtained for each county × building type combination:

| Upgrade ID | Name | Description |
|---|---|---|
| 0 | Baseline | Existing commercial building stock, no modifications |
| 36 | Package 3 | LED Lighting + Standard Performance Heat Pump RTU or HP Boilers |

Upgrade IDs and names are defined in `data/raw/upgrades_lookup.json`. The full set of 40 upgrade
scenarios available in this dataset is documented there. Package 3 (upgrade 36) combines lighting
efficiency improvements with heating system electrification.

Upgrade 36 CSVs include an additional 25 `*.savings` columns (energy savings relative to
baseline) not present in upgrade 0 files. These savings columns were excluded during data
cleaning (see Section 5.2) to maintain a consistent energy column schema across both scenarios.

---

## 5. Data Acquisition and Processing Pipeline

### 5.1 Ingestion (`src/ingest.py`)

Raw aggregate timeseries CSVs were downloaded from the OEDI S3 bucket for the county-level
timeseries aggregates path:

```
timeseries_aggregates/by_county/upgrade=<upgrade_id>/
```

Files follow the naming convention `up<upgrade_id>-<gisjoin>-<building_type>.csv` (lowercase).
One file is downloaded per county × building type × upgrade combination. Downloaded files are
stored under `data/raw/<STATE>_<GISJOIN>/upgrade_<id>/`.

### 5.2 Cleaning and Normalisation (`src/clean.py`)

All raw CSVs under `data/raw/` were discovered recursively and concatenated into a single
combined dataset. The following transformations were applied:

1. **State column**: A two-letter state abbreviation was derived from the parent folder name
   (e.g., `CO_G0800310` → `CO`) and prepended as a new `state` column.

2. **Column selection**: The following columns were retained:
   - Identifier columns: `state`, `upgrade`, `in.county`, `in.comstock_building_type`, `timestamp`
   - Floor area column: `floor_area_represented`
   - Energy output columns: all `out.*` columns **except** those ending in `.savings`
     (25 energy columns retained; savings columns excluded)

3. **Timestamp parsing**: The `timestamp` column was parsed to `datetime64` (UTC-naive; source
   timestamps are in U.S. Eastern Standard Time per dataset documentation).

4. **Energy normalisation**: Raw energy values represent aggregate kWh consumed per 15-minute
   interval across all buildings of a given type in the county. To enable cross-county and
   cross-building-type comparison, each energy column was divided by `floor_area_represented`
   and multiplied by 1,000, yielding **kWh per 1,000 sq ft per 15-minute interval**.
   Column names were updated from `*.kwh` to `*.kwh_per_1000sqft` to reflect the new unit.

   > `floor_area_represented` is constant within each county × building-type file and was
   > validated to contain no nulls and no zeros before normalisation (verified in `src/clean.py`).
   > It represents the total commercial floor area (in square feet) of that building type in
   > the county, as represented by the simulated models.

5. **Output**: The processed dataset was written to `data/processed/combined.csv` (all timesteps,
   both upgrades) and `data/processed/combined_dec1_3.csv` (December 1–3 subset).

### 5.3 Processed Dataset Structure

The combined dataset (`data/processed/combined.csv`) contains the following columns:

| Column | Type | Description |
|---|---|---|
| `state` | string | Two-letter state abbreviation (derived) |
| `upgrade` | integer | Upgrade scenario ID (0 = Baseline, 36 = Package 3) |
| `in.county` | string | GISJOIN county identifier |
| `in.comstock_building_type` | string | ComStock commercial building type |
| `timestamp` | datetime | 15-minute interval end timestamp (EST) |
| `floor_area_represented` | float | Total floor area (sq ft) represented by aggregate |
| `out.*.kwh_per_1000sqft` | float | Normalised energy intensity (kWh / 1,000 sq ft / 15 min) |

Energy columns cover the following fuel types and end uses:

- **Electricity** (14 end-use columns): cooling, exterior lighting, fans, heat recovery,
  heat rejection, heating, interior equipment, interior lighting, pumps, refrigeration,
  water systems, and total
- **Natural gas** (3 end-use columns): heating, interior equipment, water systems, and total
- **District cooling** (2 columns): cooling end-use and total
- **District heating** (2 columns): heating end-use, water systems end-use, and total
- **Other fuel** (3 columns): heating, water systems, and total
- **Site energy** (1 column): `out.site_energy.total.energy_consumption.kwh_per_1000sqft`

---

## 6. Building Types

Up to 14 ComStock commercial building prototype types were available per county. Hospital was
not present in Washtenaw County, MI (flagged as a coverage warning in the QA report;
see `reports/qa_report.html`).

| Building Type | Description |
|---|---|
| FullServiceRestaurant | Full-service restaurant |
| Hospital | Hospital (CA and CO only) |
| LargeHotel | Large hotel |
| LargeOffice | Large office building |
| MediumOffice | Medium office building |
| Outpatient | Outpatient healthcare facility |
| PrimarySchool | Primary school |
| QuickServiceRestaurant | Quick-service (fast food) restaurant |
| RetailStandalone | Standalone retail store |
| RetailStripmall | Retail strip mall |
| SecondarySchool | Secondary school |
| SmallHotel | Small hotel / motel |
| SmallOffice | Small office building |
| Warehouse | Warehouse / storage |

---

## 7. Temporal Coverage

Timestamps span the full calendar year 2018, with 35,040 records per county × building type ×
upgrade combination (96 intervals/day × 365 days). The first timestamp is
`2018-01-01 00:15:00` and the last is `2019-01-01 00:00:00`, both in Eastern Standard Time.
Timestamp completeness was verified in the QA checks (see `reports/qa_checks.csv`; all
timestamp-completeness checks: PASS).

---

## 8. Quality Assurance

Automated QA checks were implemented in `src/qa.py` and results are reported in
`reports/qa_report.html` and `reports/qa_checks.csv`. Checks performed:

| Check | Result |
|---|---|
| Null values in energy columns | PASS |
| Negative energy values | PASS |
| Zero site energy (all-zero rows) | PASS |
| Electricity sub-columns sum to total | PASS |
| Natural gas sub-columns sum to total | PASS |
| Fuel totals sum to site energy total | PASS |
| Timestamp count per group (35,040 expected) | PASS |
| Timestamp gaps (no missing intervals) | PASS |
| Building type coverage — Baseline | WARN (Hospital absent in Washtenaw Co, MI) |
| Building type coverage — Package 3 | WARN (Hospital absent in Washtenaw Co, MI) |
| Statistical outliers (3×IQR) | WARN (present in select building types; see below) |
| Flat-line detection (≥8 identical consecutive values) | PASS |
| Cross-county magnitude comparison — Baseline | PASS |
| Cross-county magnitude comparison — Package 3 | PASS |

**Outlier note**: Statistical outliers (values exceeding Q3 + 3×IQR on site energy intensity)
were observed in several building types, most prominently Warehouse across all counties and
upgrade scenarios (see `reports/qa_checks.csv` for per-group counts and percentages). Warehouse
buildings are known to have highly irregular overnight and weekend load patterns that produce
right-skewed distributions. No data were excluded on the basis of outlier status; observations
are retained in all analyses.

**Hospital coverage**: Hospital data are available for Orange County (CA) and Denver County (CO)
only. Washtenaw County (MI) does not have a Hospital aggregate file in this dataset release.
County-level comparisons involving Hospital should be interpreted accordingly.

---

## 9. Analytical Outputs

The following output files are generated by the processing pipeline:

| File | Script | Description |
|---|---|---|
| `data/processed/combined.csv` | `src/clean.py` | All timesteps, all counties, both upgrades |
| `data/processed/combined_dec1_3.csv` | `src/clean.py` | December 1–3 subset |
| `reports/eda_stats_new.csv` | `src/eda.py` | Summary statistics (mean, peak, P95, total) per county × building type × upgrade |
| `reports/eda_report.html` | `src/eda.py` | Interactive EDA report with six figure panels |
| `reports/qa_checks.csv` | `src/qa.py` | Per-group outlier statistics |
| `reports/qa_report.html` | `src/qa.py` | QA check results and diagnostic figures |
| `dashboard/index.html` | `src/dashboard.py` | Interactive Plotly dashboard with upgrade filter |

Summary statistics in `reports/eda_stats_new.csv` include mean, peak (maximum), 95th percentile,
and annual total energy intensity (kWh / 1,000 sq ft) per county × building type × upgrade
combination, computed over the full 2018 year at 15-minute resolution.

---

## 10. Software and Reproducibility

**Python version**: 3.x (see `.venv/`)
**Key libraries**: pandas, numpy, plotly, matplotlib, seaborn, scipy
**Linting**: ruff (all checks pass as of pipeline execution)

To reproduce the full pipeline from raw data:

```bash
python src/clean.py      # produces data/processed/combined.csv
python src/eda.py        # produces reports/eda_report.html
python src/qa.py         # produces reports/qa_report.html
python src/dashboard.py  # produces dashboard/index.html
```

Raw data ingestion (re-download from OEDI):

```bash
python src/ingest.py
```

---

*Document generated: 2026-03-13*
*Data accessed: 2026*
*Source dataset citation: see `data/raw/README.md`*
