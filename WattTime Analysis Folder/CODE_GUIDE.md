# WattTime Analysis V2 — Code Guide
_End-of-Term Handoff Reference | April 2026_

---

## Overview

This project analyzes WattTime grid emissions data (MOER, AOER, health_damage signals) to develop
carbon-aware scheduling heuristics for manufacturing operations. The codebase is organized into:

- **Core infrastructure** (config + utils)
- **A numbered analysis pipeline** (scripts 00–13)
- **Chapter 3 thesis analysis** (ch3_* scripts)
- **Several versioned/iterative scripts** that need to be consolidated

Total: ~63 Python files, ~32,400 lines of code.

---

## 1. Core Infrastructure

These files are foundational and used by nearly everything else. They are clean, non-duplicated, and should not be changed without careful review.

### `config.py` (~1,137 lines)
Central configuration hub for the entire project. Contains:
- WattTime credentials and API settings
- Signal definitions (co2_moer, co2_aoer, health_damage)
- Region and region-group definitions
- Analysis parameters (shift hours, job duration, percentile thresholds)
- Color/style schemes for all figures

**Nothing else should hardcode credentials, region lists, or style settings.** All scripts import from here.

---

### `utils/api_helpers.py` (~267 lines)
WattTime API client layer. Handles:
- Token authentication and refresh
- Region lookup from lat/lon coordinates
- Signal availability checks per region

### `utils/library_manager.py` (~352 lines)
Manages the append-only data library (the local cache of downloaded WattTime data). Handles:
- Catalog tracking (what data has been fetched)
- File path conventions for stored parquet files
- Checking coverage gaps and registering new data

### `utils/run_manager.py` (~362 lines)
Creates and manages dated run folders (e.g. `runs/2026-02-26_GridMixStudy_.../`). Handles:
- Validating that required data exists in the library before a run starts
- Expanding region group names to individual region keys
- Writing `run_config.json` used by downstream scripts

### `utils/validation/data_quality.py` (~275 lines)
Quality check functions used by `00_validate_data.py`. Checks for:
- Time series gaps
- Missing data percentages
- Outliers and anomalies
- Overall coverage completeness

---

## 2. The Main Analysis Pipeline (Scripts 00–13)

These numbered scripts form a sequential workflow. Run them in order for a full analysis.

```
00 → validate library data quality
01 → collect/fetch raw data from WattTime API
02 → process raw data into run folder (adds time features, daily stats)
03 → characterize temporal patterns (diurnal, seasonal, YoY)
04 → simulate flexible job scheduling, compute emissions savings
05 → evaluate day-ahead forecast accuracy
06 → synthesize results into actionable heuristics
07 → advanced robustness/volatility/regime analysis
08 → identify and characterize grid stress (extreme emission) events
09 → strategic shutdown/maintenance window planning
10 → analyze how forecast accuracy degrades with planning horizon
11 → traffic light decision system (Green/Yellow/Red by percentile)
12 → multi-day production planning and weekly cycle optimization
13 → generate Grafana dashboard artifacts for operator display
```

### `scripts/00_validate_data.py` (~742 lines)
Validates the local data library before any analysis. Generates distribution plots and a quality report. **Run this first whenever new data has been collected.**

### `scripts/01_data_collection.py` (~512 lines)  ⚠️ See duplicate note below
Fetches historical MOER/AOER/health_damage data from the WattTime API into the local library. Features:
- Intelligent caching (only fetches missing date ranges)
- Parallel fetching across regions
- Monthly incremental saves for crash safety
- Rate-limit handling

### `scripts/02_data_processing.py` (~414 lines)
Loads library data into a run folder. Adds time features (hour, day of week, season, year), computes daily stats, and exports processed parquet files that all downstream scripts read.

### `scripts/03_temporal_patterns.py` (~533 lines)  ⚠️ See duplicate note below
Original temporal pattern analysis — diurnal profiles, seasonal heatmaps (mean), weekday/weekend, YoY trends.

### `scripts/04_scheduling_simulation.py` (~630 lines)
Core simulation engine. Tests optimal vs. baseline job scheduling across a shift window, computing realized emissions savings by duration, season, and region. **Most downstream ch3 scripts re-implement a lighter version of this simulation via `ch3_common.py`.**

### `scripts/05_forecast_accuracy.py` (~450 lines)
Analyzes how well WattTime's day-ahead forecast predicts actual MOER. Measures scheduling decision quality when relying on forecasts rather than actuals.

### `scripts/06_heuristics.py` (~495 lines)  ⚠️ See duplicate note below
Original heuristics synthesis — produces `heuristics_table.csv`, a markdown report, and basic summary figures.

### `scripts/07_advanced_analysis.py` (~1,708 lines)
The largest script in the pipeline. Extends heuristics analysis with:
- Robustness and sensitivity checks
- Operational constraints modeling
- Volatility and grid regime clustering
- Forecast value quantification
**Note:** Much of this analysis was later re-implemented in cleaner, modular form in the `ch3_extended_*` scripts. Review for overlap before using.

### `scripts/08_grid_stress.py` (~1,003 lines)
Identifies extreme grid emissions events. Analyzes event frequency, duration, predictability, regional correlation, and whether forecasts can provide early warning.

### `scripts/09_shutdown_planning.py` (~935 lines)
Strategic analysis for planning facility downtime/maintenance during the lowest-emission periods. Ranks weeks and months by MOER, assesses holiday alignment, and models diminishing returns.

### `scripts/10_forecast_horizon.py` (~1,229 lines)
Analyzes how forecast reliability degrades as planning horizon extends from hours to days. Identifies crossover points where heuristics outperform forecasts.

### `scripts/11_threshold_buckets.py` (~931 lines)
Implements the traffic light system (Green / Yellow / Red) based on MOER percentile thresholds. Generates lookup tables for operators who don't want live API integration.

### `scripts/12_multiday_optimization.py` (~1,000 lines)
Extends scheduling from a single day to multi-day production planning. Analyzes weekly emission cycles and the value of flexible production scheduling.

### `scripts/13_grafana_operator_deploy.py` (~722 lines)
Generates deployment artifacts for a Grafana operator dashboard:
- Threshold JSON config
- Hourly lookup CSV
- Printable reference cards

---

## 3. Chapter 3 Thesis Analysis (ch3_* scripts)

These scripts produce the figures and tables for Chapter 3 of the thesis. They are a parallel, self-contained analysis system that is more publication-ready than the pipeline scripts above.

### `scripts/ch3_common.py` (~459 lines) — **THE KEY FILE**
Shared utility module imported by ALL ch3 scripts. Contains:
- Global CONFIG (run folder, regions, signal, shift hours, percentile thresholds, years)
- Data loading functions (`load_5min`, `load_hourly`)
- Core simulation engine (`run_scheduling_sim`, `simulate_day`, `compute_thresholds`)
- Thesis-quality figure styling (`thesis_style`)
- Save helpers (`save_fig`, `save_table`, `record_number`)
- Caching layer (`save_cache`, `load_cache`) for expensive computations

**If you need to change which data is used, which regions are analyzed, or any global parameter for Chapter 3 figures — edit only this file.**

### Master Runners
- **`ch3_run_all.py`** (~106 lines): Runs core Chapter 3 sections (s1–s4 + appendix). Supports `--section`, `--recompute`, `--clean` flags.
- **`ch3_run_all_extended.py`** (~165 lines): Runs the 10 extended analysis scripts. Writes to a separate output file to avoid overwriting core section numbers.

### Chapter 3 Sections (Core)
Each section script imports from `ch3_common.py` and produces specific figures/tables:

| Script | Section | What It Produces |
|--------|---------|-----------------|
| `ch3_s1_grid_characterization.py` (~483 lines) | 3.3 | Figs 3.1–3.3, Tables 3.2–3.3: diurnal profiles, representative week, optimal hour heatmap |
| `ch3_s2_traffic_light.py` (~906 lines) | 3.4 | Figs 3.4–3.7, Tables 3.4–3.5: traffic light system, savings comparison, holdout validation |
| `ch3_s3_constraints.py` (~365 lines) | 3.5 | Figs 3.8–3.9, Table 3.6: duration sensitivity, flexibility value |
| `ch3_s4_discussion.py` (~335 lines) | 3.6 | Table 3.7: maintenance timing, weekend/weekday, oil pump retrospective |
| `ch3_appendix_c.py` (~414 lines) | Appendix C | Green window distributions, state transition probabilities, shift-constrained savings |

### Chapter 3 Supplementary Analysis
These produce supplementary figures and robustness checks for the thesis:

| Script | What It Does |
|--------|-------------|
| `ch3_supp_temporal_holdout.py` (~492 lines) | How quickly heuristic parameters go stale when not recalibrated |
| `ch3_supp_job_duration.py` (~517 lines) | Detailed duration sensitivity sweep (extends Fig 3.8) |
| `ch3_supp_forcast_horizon.py` (~730 lines) | Scheduling savings vs. decision lead time (1h → 72h) |
| `ch3_supp_yoy_trend.py` (~343 lines) | Year-over-year consistency of MOER patterns and savings |
| `ch3_supp_green_windows.py` (~417 lines) | Green window duration distributions and persistence |
| `ch3_supp_weekend_weekday.py` (~251 lines) | Weekend vs. weekday scheduling opportunity differences |
| `ch3_supp_monthly_savings.py` (~264 lines) | How scheduling effectiveness varies month to month |
| `ch3_supp_shift_windows.py` (~406 lines) | Savings when production hours are fixed vs. flexible |
| `ch3_supp_outlierFigs copy.py` (~343 lines) | ⚠️ Dev copy — see duplicate note below |

### Chapter 3 Extended Analysis (10 scripts)
Each addresses a distinct research question. No overlap between them:

| Script | Research Question |
|--------|-----------------|
| `ch3_extended_signal_predictability.py` (~656 lines) | Why do heuristics work? What fraction of MOER variance is explained by calendar features? |
| `ch3_extended_three_tier_signals.py` (~462 lines) | eGRID vs AOER vs MOER — how much scheduling opportunity is lost with simpler data? |
| `ch3_extended_threshold_optimization.py` (~543 lines) | Are P25/P75 the optimal green/red boundaries, or would other percentiles perform better? |
| `ch3_extended_heuristic_shelf_life.py` (~348 lines) | How quickly do scheduling parameters become stale over time? |
| `ch3_extended_health_cobenefits.py` (~249 lines) | CAISO case study: does carbon-aware scheduling also reduce health-damaging emissions? |
| `ch3_extended_decarbonization_trajectory.py` (~271 lines) | Is the value of carbon-aware scheduling increasing as grids decarbonize? |
| `ch3_extended_economic_value.py` (~266 lines) | Converts savings to annual tonnes CO₂ and $/year under carbon pricing scenarios |
| `ch3_extended_production_queue.py` (~380 lines) | How do results change when jobs must run in fixed queue order vs. flexible selection? |
| `ch3_extended_intra_iso_portability.py` (~416 lines) | Can one region's thresholds work for a different region in the same ISO? |
| `ch3_extended_shift_flexibility.py` (~386 lines) | Value of extending shift windows: 8-hr vs. 12-hr vs. 16-hr availability |

### Benchmark Comparison Scripts
These four scripts sit outside the main section structure but are part of Chapter 3 analysis:

| Script | What It Does |
|--------|-------------|
| `Ch3TodAnnual.py` (~369 lines) | Benchmarks a fixed annual "best hour" rule vs. baseline and optimal |
| `Ch3TodSeasonal.py` (~523 lines) | Benchmarks seasonal best-hour rules (region × season specific) |
| `Ch3ForecastEval.py` (~570 lines) | Evaluates scheduling when using last night's day-ahead forecast to pick tomorrow's window |
| `Ch3MethodComparison.py` (~733 lines) | Side-by-side comparison of all methods: TOD, traffic light, forecast, optimal oracle |

### Standalone Figure Generators
| Script | What It Produces |
|--------|-----------------|
| `CH3_FIG_optimalHourHeatmap.py` (~196 lines) | Region × season optimal hour heatmap figure |
| `CH3_FIG_greenwindowLength.py` (~212 lines) | Green window length and persistence visualization |

---

## 4. Versioned / Duplicate Scripts — Consolidation Guide

These are the scripts with multiple versions. Each group is analyzed below.

---

### Group A: `01_data_collection` (2 versions)

| File | Lines | Key Difference |
|------|-------|----------------|
| `01_data_collection.py` | 512 | Base version |
| `01_data_collection v2.py` | 596 | Same docstring/structure; CONFIG has `SIGNAL = "health_damage"`, `REGIONS_TO_FETCH = "GridMixStudy"` |

**Finding:** These are functionally the same script. The "v2" file is just a saved copy with different CONFIG values set for a specific data pull (health_damage signal, GridMixStudy region group). The logic is identical.

**Recommendation:** Keep only `01_data_collection.py`. The v2 file adds no new logic — it's just a snapshot config state. If you want to document that health_damage and GridMixStudy were the configs used for a specific pull, note that in a comment at the top of the canonical file or in the run log.

---

### Group B: `03_temporal_patterns` (4 versions + 3 sub-scripts)

| File | Lines | Key Innovation Added |
|------|-------|---------------------|
| `03_temporal_patterns.py` (v1) | 533 | Original: hourly profiles, mean heatmaps, weekday/weekend, YoY |
| `03_temporal_patterns_v2.py` | 660 | Added all-regions multi-panel figures (`03_seasonal_all_regions.png`, `03_weekday_weekend_all_regions.png`) |
| `03_temporal_patterns_v3.py` | 694 | Added `FIXED_YLIM` and `FIXED_HEATMAP_RANGE` params for consistent axis control; added `03_daily_variability.png` and `03_daily_range_by_season.png` |
| `03_temporal_patterns_v4.py` | 786 | Added percentile-based analysis (P25–P75, P10–P90 bands), **median heatmaps** alongside mean heatmaps, density plots — major methodological upgrade |

**Finding:** This is a clear linear evolution. Each version builds on the previous. **v4 contains all innovations from v1–v3.** The fixed axis limits from v3 are already in v4 (`FIXED_YLIM`, `FIXED_HEATMAP_RANGE`). The multi-region panel figures from v2 are also in v4.

| Sub-script | Lines | Relationship to v4 |
|-----------|-------|--------------------|
| `03.1_temporal_patterns_kansas debug.py` | 165 | Pure diagnostic for SPP_KANSAS spike anomaly — not production code |
| `03.2_temporal_patters_gridfigure.py` | 192 | Standalone 6-panel diurnal grid figure with archetype labels (matches Table 3-1); uses P25/P75/P10/P90 bands |
| `03.3_representative_week_grid.py` | 301 | Standalone 6-panel raw weekly 5-min traces with day/night shading and threshold lines |

**Recommendation:**
- **v4 is the canonical script** — rename it to `03_temporal_patterns.py` and retire v1–v3.
- **`03.2` and `03.3` should be kept as separate scripts** — they generate specific thesis publication figures (6-panel grids with archetype labels that map to Table 3-1) and are not redundant with v4. Their figure logic could eventually be pulled into `ch3_s1_grid_characterization.py` which already generates similar figures for Section 3.3.
- **`03.1` (Kansas debug)** can be deleted or moved to an `archive/` folder. Any useful outlier-detection logic from it belongs in `00_validate_data.py` or `utils/validation/data_quality.py`.

**Things from v1–v3 worth saving before you delete them:**
- v3's `FIXED_YLIM`/`FIXED_HEATMAP_RANGE` values (already in v4 — safe to delete v3)
- v2's multi-panel output logic (already in v4 — safe to delete v2)
- v1 has nothing v4 doesn't have

---

### Group C: `06_heuristics` (3 versions)

| File | Lines | Key Difference |
|------|-------|----------------|
| `06_heuristics.py` (v1) | 495 | Original: `heuristics_table.csv`, `heuristics_report.md`, 2 summary figures |
| `06_heuristics_v2.py` | 500 | Near-identical to v1 in structure and outputs; same run folder referenced |
| `06_heuristics_v3.py` | 755 | Adds 4 new figures: `seasonal_savings_distribution`, `optimal_hour_by_season`, `consistency_heatmap`, `cumulative_savings`; references a newer run folder |

**Finding:** v1 and v2 appear functionally identical — v2 is likely a minor iteration with small tweaks. v3 is a significant expansion with 4 additional figure outputs and a newer run folder. v3 is the most complete version.

**Recommendation:**
- **v3 is the canonical script** — rename it to `06_heuristics.py` and retire v1 and v2.
- Before retiring v2, do a diff against v1 to confirm nothing unique was added (they appear structurally identical from the headers, but worth checking the body).
- Note: The `ch3_s2_traffic_light.py` and `ch3_s3_constraints.py` scripts cover much of the same heuristics ground for the thesis, with better methodology. If continuing this project, the pipeline `06_heuristics.py` may eventually be superseded by the ch3 scripts entirely.

---

### Group D: `ch3_supp_outlierFigs copy.py`

This is a copy artifact (note the "copy" in the filename). Compare it against any final `ch3_supp_outlierFigs.py` — if no canonical version exists, rename this to `ch3_supp_outlier_figures.py` and delete the copy suffix. If both exist, diff them and keep whichever is more complete.

---

### Group E: `07_advanced_analysis.py` vs Ch3 Extended Scripts

This is not a filename duplicate, but a **functional overlap** worth flagging:

`07_advanced_analysis.py` (1,708 lines) was written as part of the pipeline and includes:
- Robustness analysis
- Operational constraints modeling
- Grid volatility/regime clustering
- Forecast value quantification

The 10 `ch3_extended_*.py` scripts later re-implemented these analyses in cleaner, more modular form with better thesis-quality figures and caching. Specifically:
- `07_advanced_analysis.py` robustness → `ch3_extended_threshold_optimization.py`
- `07_advanced_analysis.py` forecast value → `ch3_supp_forcast_horizon.py` and `Ch3ForecastEval.py`
- `07_advanced_analysis.py` volatility → `ch3_extended_signal_predictability.py`

**Recommendation:** Don't delete `07_advanced_analysis.py` — it may contain intermediate outputs referenced by `08` through `13`. But for new analysis or publication, prefer the ch3 extended scripts.

---

## 5. Exploratory / One-Off Scripts

These are development artifacts and not part of any analysis pipeline:

| Script | Status | Notes |
|--------|--------|-------|
| `400_all_aoer_regions_exploretest.py` (67 lines) | Dev test | One-off API access verification for co2_aoer signal; safe to archive or delete |
| `Ch3_defesneercotandspp_code that suckis and output directorywrong.py` (433 lines) | Abandoned | Poorly named debug script; review for any salvageable logic before deleting |
| `03.1_temporal_patterns_kansas debug.py` (165 lines) | Diagnostic | See Group B above |

---

## 6. Consolidation Summary

| Action | Scripts Affected |
|--------|-----------------|
| **Keep as-is (canonical, no changes needed)** | `config.py`, all `utils/`, `00`, `02`, `04`–`06_v3`, `07`–`13`, all `ch3_common.py`, all `ch3_s*`, all `ch3_supp_*` (except copy), all `ch3_extended_*`, all `Ch3Tod*`, `Ch3ForecastEval`, `Ch3MethodComparison`, both `CH3_FIG_*` |
| **Rename v4 → canonical** | `03_temporal_patterns_v4.py` should become the main `03_temporal_patterns.py` |
| **Rename v3 → canonical** | `06_heuristics_v3.py` should become the main `06_heuristics.py` |
| **Safe to archive/delete** (logic absorbed by canonical versions) | `03_temporal_patterns.py` (v1), `03_temporal_patterns_v2.py`, `03_temporal_patterns_v3.py`, `06_heuristics.py` (v1), `06_heuristics_v2.py`, `01_data_collection v2.py` |
| **Keep separate but consider renaming** | `03.2_temporal_patters_gridfigure.py` → `03b_diurnal_grid_6panel.py`, `03.3_representative_week_grid.py` → `03c_representative_week_6panel.py` |
| **Archive (diagnostic only)** | `03.1_temporal_patterns_kansas debug.py`, `400_all_aoer_regions_exploretest.py` |
| **Review then delete** | `Ch3_defesneercotandspp_code that suckis...`, `ch3_supp_outlierFigs copy.py` |

---

## 7. Recommended "Clean" Script Set (Post-Consolidation)

After consolidation, the project should have approximately **47 scripts** (down from 63):

```
config.py
utils/
  api_helpers.py
  library_manager.py
  run_manager.py
  validation/data_quality.py

scripts/
  00_validate_data.py
  01_data_collection.py          ← (drop v2)
  02_data_processing.py
  03_temporal_patterns.py        ← (was v4)
  03b_diurnal_grid_6panel.py     ← (was 03.2, renamed)
  03c_representative_week_6panel.py ← (was 03.3, renamed)
  04_scheduling_simulation.py
  05_forecast_accuracy.py
  06_heuristics.py               ← (was v3)
  07_advanced_analysis.py
  08_grid_stress.py
  09_shutdown_planning.py
  10_forecast_horizon.py
  11_threshold_buckets.py
  12_multiday_optimization.py
  13_grafana_operator_deploy.py

  ch3_common.py
  ch3_run_all.py
  ch3_run_all_extended.py

  ch3_s1_grid_characterization.py
  ch3_s2_traffic_light.py
  ch3_s3_constraints.py
  ch3_s4_discussion.py
  ch3_appendix_c.py

  ch3_supp_temporal_holdout.py
  ch3_supp_job_duration.py
  ch3_supp_forcast_horizon.py
  ch3_supp_yoy_trend.py
  ch3_supp_green_windows.py
  ch3_supp_weekend_weekday.py
  ch3_supp_monthly_savings.py
  ch3_supp_shift_windows.py
  ch3_supp_outlier_figures.py    ← (was "copy", renamed)

  ch3_extended_signal_predictability.py
  ch3_extended_three_tier_signals.py
  ch3_extended_threshold_optimization.py
  ch3_extended_heuristic_shelf_life.py
  ch3_extended_health_cobenefits.py
  ch3_extended_decarbonization_trajectory.py
  ch3_extended_economic_value.py
  ch3_extended_production_queue.py
  ch3_extended_intra_iso_portability.py
  ch3_extended_shift_flexibility.py

  Ch3TodAnnual.py
  Ch3TodSeasonal.py
  Ch3ForecastEval.py
  Ch3MethodComparison.py

  CH3_FIG_optimalHourHeatmap.py
  CH3_FIG_greenwindowLength.py
```

---

## 8. Core Infrastructure — What Could Be Cleaner

These are not duplicates — the core files work — but they have structural issues worth fixing before a handoff.

---

### `config.py` Issues

**1. Hardcoded credentials (security)**
Credentials now come from environment variables in `config.py`; older commits contained plain-text credentials, so rotate any exposed WattTime password before sharing:
```python
WATTTIME_USERNAME = os.getenv("WATTTIME_USERNAME", "")
WATTTIME_PASSWORD = os.getenv("WATTTIME_PASSWORD", "")
```
For a handoff, copy `.env.example` to `.env`, keep `.env` ignored by git, and set `WATTTIME_USERNAME` / `WATTTIME_PASSWORD` locally. Do not commit generated token files.

**2. The REGIONS dict is enormous and mostly unused**
`config.py` catalogs 60+ WattTime subregions (MISO, PJM, CAISO, ERCOT, ISONE, NYISO, SPP, BPA, etc.) across ~400 lines, but the actual GridMixStudy analysis only ever uses 6:
```
BPA, CAISO_NORTH, ERCOT_NORTHCENTRAL, ISONE_CT, MISO_INDIANAPOLIS, SPP_KANSAS
```
This is not wrong — it's a reference catalog — but it makes the file confusing because a reader has to scroll past hundreds of unused region definitions to find analysis parameters. A simple fix: move the full catalog to a separate `region_catalog.py` and keep only the 6 study regions plus the REGION_GROUPS in `config.py`. The catalog is still there for future use but doesn't bury the important settings.

**3. Archetype labels exist in two places**
`ch3_common.py` defines `CH3_REGIONS` with archetype labels (e.g., "Hydro-baseload", "Solar-dominated") that `config.py`'s REGIONS dict does not have. These labels appear in thesis figures. If you ever add a 7th region to the study, you have to add it to both files. Consider adding an `archetype` field to the REGIONS dict in `config.py` so it becomes the single source.

**4. `get_run_dir()` is copy-pasted 12+ times**
Every pipeline script (03 through 13) has this identical ~8-line function:
```python
def get_run_dir() -> Path:
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
            sys.exit(1)
        return run_dir
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    ...
```
This belongs in `utils/run_manager.py` as an exported function. It's a trivial fix but would clean up every pipeline script significantly. The ch3 scripts already handle this via `ch3_common.py`, which is the right pattern.

**5. `ch3_common.py` has its own standalone CONFIG block**
`ch3_common.py` re-defines shift hours, percentile thresholds, job duration, characterization years, and the region list — all things that also exist in `config.py`. The two systems have drifted:

| Parameter | `config.py` | `ch3_common.py` |
|-----------|------------|-----------------|
| Shift start | `SHIFTS = {"day": {"start": 6}}` | `DAY_SHIFT_START = 6` |
| Green percentile | `GREEN_PERCENTILE` (not present) | `GREEN_PERCENTILE = 25` |
| Job duration | `JOB_DURATIONS = [0.5, 1, 2, 4]` | `REFERENCE_JOB_HOURS = 2.0` |
| Region colors | `REGION_COLORS = {...}` | `REGION_COLORS = {...}` (duplicated) |

Both color dicts define the same 6 colors — they happen to be in sync, but there's no enforcement. If you change a color in one, you must remember to change the other. The ch3 scripts should import `REGION_COLORS` from `config.py` rather than redefining it.

---

### `utils/` Issues

**`utils/run_manager.py` is underused**
The module exists and creates run folders correctly, but most pipeline scripts bypass it and use their own `get_run_dir()` boilerplate (see point 4 above). The ch3 scripts use `ch3_common.py`'s version instead. `run_manager.py` should be the single place this logic lives, and both the pipeline scripts and `ch3_common.py` should import from it.

**`utils/validation/data_quality.py` is only called by `00_validate_data.py`**
The quality-check functions (gap detection, outlier flagging) in `data_quality.py` would also be useful inside `02_data_processing.py` as a lightweight sanity check on the data being processed into a run. Currently 02 does no validation — it assumes the library data is clean. If a bad data pull made it into the library (e.g., the Kansas spike issue that spawned `03.1_temporal_patterns_kansas debug.py`), processing will silently proceed with corrupted data until figures look wrong.

---

## 9. Pipeline Scripts vs Chapter 3 Scripts — Overlap Analysis

The pipeline (scripts 00–13) and the Chapter 3 system (`ch3_*`) are **two parallel implementations** of related analyses. They are NOT the same — the ch3 scripts are more rigorous and publication-ready — but they share significant conceptual and sometimes technical overlap. This section maps exactly where they diverge so you know which to use.

---

### The Core Design Difference

| | Pipeline (00–13) | Chapter 3 (ch3_*) |
|---|---|---|
| **Purpose** | Exploratory / iterative analysis tool | Publication-quality thesis figures and tables |
| **Data inputs** | From run folder via `RUN_FOLDER` config | From run folder via `ch3_common.py` CONFIG |
| **Simulation** | Full pipeline in `04_scheduling_simulation.py` | Reimplemented in `ch3_common.run_scheduling_sim()` |
| **Figures** | Quick diagnostic outputs | Thesis-formatted, labeled, PDF+PNG |
| **Caching** | None — re-computes every run | Yes — `save_cache`/`load_cache` in `ch3_common.py` |
| **Config** | Edit `RUN_FOLDER` in each script | Edit `RUN_DIR_NAME` once in `ch3_common.py` |
| **Run** | One script at a time | `ch3_run_all.py` runs everything |

---

### Specific Overlapping Pairs

**1. Diurnal MOER profiles**
- Pipeline: `03_temporal_patterns_v4.py` → generates `03_hourly_profile_{region}.png`
- Ch3: `ch3_s1_grid_characterization.py` → generates `fig_3_1_diurnal_profiles.png`
- **Difference:** ch3 version uses thesis styling, ±1σ bands, archetype labels, and saves as PDF. Pipeline version generates per-region plots with more diagnostic variants. **Use ch3 for the paper; use pipeline for exploration.**

**2. Traffic light / threshold system**
- Pipeline: `11_threshold_buckets.py` → calibrates thresholds, generates lookup tables
- Ch3: `ch3_s2_traffic_light.py` → full traffic light analysis with holdout validation (train 2022–23, test on 2024), multiple scheduling strategies, savings comparison
- **Difference:** ch3 version is more rigorous — it validates the thresholds on held-out data and compares against alternative strategies. Pipeline version is faster to run and generates the operator-facing artifacts (used by script 13). **These are complementary, not duplicates.** Script 11 → Script 13 → operator deployment. `ch3_s2` → thesis table.

**3. Scheduling simulation**
- Pipeline: `04_scheduling_simulation.py` (full script, ~630 lines)
- Ch3: `ch3_common.run_scheduling_sim()` + `ch3_common.simulate_day()` (~100 lines combined)
- **Difference:** `ch3_common` has a cleaner, vectorized re-implementation for the six core regions. The pipeline version is more comprehensive — it tests more shift types, more durations, and outputs more diagnostic figures. The ch3 version is leaner and faster because it only computes what the thesis needs. **Not truly duplicate — the ch3 version is a focused extract.** If the pipeline sim results and ch3 sim results disagree on a number, investigate — they should produce the same answer for the same inputs.

**4. Forecast horizon analysis**
- Pipeline: `10_forecast_horizon.py` (~1,229 lines) — very comprehensive, many horizons, many contexts
- Ch3 supplementary: `ch3_supp_forcast_horizon.py` (~730 lines) — focused on the scheduling-relevant insight (savings vs lead time)
- **Difference:** Pipeline version characterizes forecast accuracy broadly. Ch3 version specifically answers "at what lead time does forecast-based scheduling stop beating heuristics?" — a narrower but more directly thesis-relevant question. **Both are worth keeping; the ch3 version is the one cited in the paper.**

**5. Heuristics synthesis**
- Pipeline: `06_heuristics_v3.py` — produces `heuristics_table.csv` and `heuristics_report.md`
- Ch3: `ch3_s2_traffic_light.py` + `ch3_s3_constraints.py` + `ch3_s4_discussion.py` together cover the same ground as `06_heuristics`, but split into thesis sections
- **Difference:** The pipeline `06` produces a single unified heuristics table that is operationally useful (operators could print it). The ch3 scripts produce section-by-section thesis content. **The pipeline version is the deliverable; the ch3 scripts are the peer-reviewed evidence.**

**6. Robustness / holdout validation**
- Pipeline: `07_advanced_analysis.py` — Section 1 runs holdout validation (train 2022–23, test 2024)
- Ch3: `ch3_supp_temporal_holdout.py` — measures parameter staleness over time
- **Difference:** `07` tests whether the *rules* hold on new data. The ch3 supp script tests how quickly the *parameters* (optimal hours, thresholds) drift as data ages. Related but distinct questions.

**7. Duration sensitivity**
- Pipeline: `07_advanced_analysis.py` Section 2 includes duration sensitivity
- Ch3 core: `ch3_s3_constraints.py` — Fig 3.8, the thesis figure for duration sensitivity
- Ch3 supplementary: `ch3_supp_job_duration.py` — deeper sweep with more durations
- **Difference:** Three levels of the same analysis. `07` is the rough exploratory version. `ch3_s3` is the clean thesis figure. `ch3_supp_job_duration` is the detailed evidence behind it.

**8. Regional color palettes (pure duplication)**
Both `config.py` and `ch3_common.py` define `REGION_COLORS` with the same 6 hex codes. This is the clearest true duplicate — no difference in purpose, no difference in values. The ch3 scripts should import from `config.py`.

---

### What to Use When

| Task | Use This |
|------|---------|
| Exploring a new signal or region | Pipeline scripts 03–06 |
| Generating thesis figures | `ch3_run_all.py` |
| Generating supplementary / extended figures | `ch3_run_all_extended.py` |
| Calibrating operator thresholds | `11_threshold_buckets.py` → `13_grafana_operator_deploy.py` |
| Checking data quality | `00_validate_data.py` |
| Adding new data to the library | `01_data_collection.py` |
| Re-running all Ch3 numbers after changing years/regions | Edit `ch3_common.py` CONFIG, run `ch3_run_all.py --recompute` |

---

## 10. Existing Guide Documents — Summary

There are three existing guide files in the project root plus the new `CODE_GUIDE.md` (this file). Here is what each covers and how they relate.

---

### `README.md` (~976 lines) — **The Primary Reference**

The most current and comprehensive guide in the project. Covers:
- Project overview and research context
- Quick-reference table (script # → core question → primary output)
- Full directory structure diagram
- Pipeline architecture flow diagram (with stages: Setup → Core → Validation → Extended)
- Per-script documentation for ALL 14 pipeline scripts (00–13), each with: purpose, inputs, key config params, outputs table, key metric, and assumptions
- `config.py` full reference — what lives there vs what lives in script CONFIG blocks
- Data dependency diagram
- Template for writing a new pipeline script (new module convention)
- Troubleshooting section (common errors and fixes)

**Status:** Up to date with v4 temporal patterns, v3 heuristics, and the library/runs architecture. References the correct run folder naming convention. The most useful document for someone continuing the pipeline work.

**Gap:** Does not cover the ch3 scripts at all — treats them as outside scope.

---

### `watttime_heuristic_tool_guide.md` (~888 lines) — **Older Overview**

An earlier, more narrative guide written before the runs/ architecture was finalized. Covers:
- Detailed module descriptions for 01–12 (matching `README.md` sections)
- Thesis chapter mapping table
- Architecture diagram and data flow
- API reference (WattTime endpoints, research tier features)
- Output interpretation guide (how to read the heuristics table, stress events, regional comparisons)
- Priority-ranked figure list for the paper

**Status:** Partially outdated. It still references `data/raw/` paths (the pre-library structure) and `data/processed/` rather than the `runs/` folder system. The module descriptions duplicate README but are less detailed. The output interpretation section and "Research Applications" section (thesis chapter mapping, priority figure list) are the unique value — those are not in README.

**Most useful parts not in README:**
- Section 7: Output interpretation — guidance on what "good" values look like for each metric (hourly spread >100, savings >10%, consistency >70%, etc.)
- Section 8 / Research Applications — thesis chapter mapping, priority figure rankings for paper, key research contributions narrative

**Recommendation for handoff:** The output interpretation table and research contributions list are worth preserving. Everything else is covered more accurately by README.

---

### `watttime_quick_reference.md` (~212 lines) — **Concise Cheat Sheet**

A condensed version intended for quick lookup. Contains:
- Module overview ASCII table (pipeline stages)
- Module details table (# → core question → time scale → primary user)
- Key outputs by module (CSV + figure + metric, in one table per stage)
- Dependency diagram
- Run order commands (first-time + re-run + new region)
- Config quick reference
- Thesis chapter mapping

**Status:** Slightly dated — references `12_multiday_planning.py` (the script is named `12_multiday_optimization.py`). Also does not include script 13 (grafana deploy) or script 00 (validate). Otherwise still accurate.

**Most useful part:** The "module details" table showing time scale (Hours / Days / Weeks-Months) and primary user (Analyst / Operator / Plant Manager / System Designer) — a quick frame for understanding the purpose of each module that neither README nor the longer guide has in one place.

**Recommendation for handoff:** Keep as-is, fix the script 12 name, add scripts 00 and 13.

---

### `CODE_GUIDE.md` (this file) — **Consolidation and Handoff Map**

What this document adds that the others don't:
- Inventory of all 63 scripts including ch3 and versioned files
- Explicit consolidation guide: which scripts are duplicates, what each version added, which is canonical
- Core infrastructure critique (config issues, copy-pasted boilerplate, parallel implementations)
- Ch3 vs pipeline overlap analysis — which to use for what
- Guide document summary (this section)

---

### How the Four Guides Relate

```
watttime_quick_reference.md    — One-page cheat sheet, run order, output lookup
         ↓ expands to
README.md                      — Full pipeline reference, per-script docs, template for new scripts
         ↓ this file adds
CODE_GUIDE.md                  — Duplication map, infrastructure critique, ch3 overlap analysis
         ↓ deeper narrative in
watttime_heuristic_tool_guide.md — Older guide; still useful for output interpretation and thesis framing
```

**For a new person taking over the project, the recommended reading order:**
1. `README.md` — understand the pipeline architecture and how to run it
2. `watttime_quick_reference.md` — keep open as a cheat sheet while working
3. `CODE_GUIDE.md` (this file) — understand what's a duplicate vs canonical and why things are organized the way they are
4. `watttime_heuristic_tool_guide.md` Section 7 — understand what "good" results look like

---

## 11. Quick-Reference: Where to Look for What

| Need | Look Here |
|------|-----------|
| Change API credentials / regions / signals | `config.py` |
| Add a new region | `config.py` → `REGIONS` dict |
| Fetch new data | `01_data_collection.py` |
| Understand what data is cached | `utils/library_manager.py` |
| Reproduce core thesis figures | `ch3_run_all.py` (runs s1–s4 + appendix) |
| Reproduce extended/supplementary figures | `ch3_run_all_extended.py` |
| Change analysis parameters for Ch3 | `ch3_common.py` CONFIG section |
| Understand the scheduling simulation logic | `ch3_common.py` → `run_scheduling_sim()` and `simulate_day()` |
| Re-run full pipeline analysis | Scripts 00 → 13 in order |
| Traffic light thresholds for operators | `scripts/11_threshold_buckets.py` and `scripts/13_grafana_operator_deploy.py` |
