# WattTime Carbon-Aware Manufacturing Scheduling — Analysis Framework

Carbon-aware manufacturing scheduling research using WattTime grid emissions data. Developed as part of MS thesis work at Purdue IN-MaC, targeting ASME MSEC 2026.

---

## Project Overview

This framework analyzes historical and forecast Marginal Operating Emissions Rate (MOER) data across US grid regions to develop practical scheduling heuristics for manufacturing facilities. The core question: can simple time-of-day rules capture most of the available carbon savings without requiring real-time API subscriptions?

**Regions analyzed (GridMixStudy group):** CAISO_NORTH (solar-dominant), SPP_KANSAS (wind-dominant), BPA (hydro-dominant), MISO_INDIANAPOLIS (fossil-heavy), ISONE_CT (gas + nuclear), ERCOT_NORTHCENTRAL (wind-smoothed)

**Signals supported:** `co2_moer`, `co2_aoer`, `health_damage`

---

## Quick Reference

| # | Script | Core Question | Primary Output |
|---|--------|---------------|----------------|
| 00 | validate_data | Is my library complete and clean? | `data_validation_report.md` |
| 01 | data_collection | Fetch raw data from WattTime API | `library/{signal}/{region}.parquet` |
| 02 | data_processing | Process raw data into a run | `processed/data_5min.parquet` + run folder |
| 03 | temporal_patterns | When is the grid cleanest? | Hourly/seasonal profile figures, `temporal_pattern_summary.csv` |
| 04 | scheduling_simulation | How much can we save by scheduling optimally? | `scheduling_summary.csv` |
| 05 | forecast_accuracy | How well do WattTime forecasts perform? | `forecast_accuracy_by_horizon.csv` |
| 06 | heuristics | What are the actionable scheduling rules? | `heuristics_table.csv`, `heuristics_report.md` |
| 07 | advanced_analysis | Are the rules robust and validated? | `07_stability.csv`, holdout results |
| 08 | grid_stress | When should we NOT run? | `08_stress_events.csv` |
| 09 | shutdown_planning | When should we schedule maintenance? | `09_weekly_rankings.csv` |
| 10 | forecast_horizon | At what horizon should we trust forecasts vs heuristics? | `10_implementation_thresholds.csv` |
| 11 | threshold_buckets | Can we use a simple traffic light system? | `11_threshold_values.csv` |
| 12 | multiday_optimization | How should we allocate production across a week? | `12_flexibility_value.csv` |
| 13 | grafana_operator_deploy | Deploy a live operator dashboard | Grafana dashboard JSON + operator card |

---

## Project Structure

```
watttime_analysis/
├── config.py                     # Credentials, signals, regions, constants
├── library/                      # Permanent raw data storage (never delete)
│   ├── catalog.json
│   ├── co2_moer/
│   │   ├── historical/           # {REGION}.parquet
│   │   └── forecast/
│   ├── co2_aoer/
│   └── health_damage/
├── runs/                         # Analysis runs (disposable, re-generatable)
│   └── YYYY-MM-DD_run_name/
│       ├── run_config.json
│       ├── processed/
│       ├── outputs/
│       └── figures/
├── scripts/
│   ├── 00_validate_data.py
│   ├── 01_data_collection.py
│   ├── 02_data_processing.py
│   ├── 03_temporal_patterns.py
│   ├── 04_scheduling_simulation.py
│   ├── 05_forecast_accuracy.py
│   ├── 06_heuristics.py
│   ├── 07_advanced_analysis.py
│   ├── 08_grid_stress.py
│   ├── 09_shutdown_planning.py
│   ├── 10_forecast_horizon.py
│   ├── 11_threshold_buckets.py
│   ├── 12_multiday_optimization.py
│   └── 13_grafana_operator_deploy.py
└── utils/
    ├── api_helpers.py
    ├── library_manager.py
    ├── run_manager.py
    └── validation/
        └── data_quality.py
```

**Design principle:** `library/` holds raw data permanently — treat it as append-only. `runs/` holds analysis outputs and can be deleted and regenerated anytime. Never put raw data in `runs/`.

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────┐
│  SETUP / DATA                                        │
│  00_validate_data    → audit library before analysis │
│  01_data_collection  → WattTime API → library        │
│  02_data_processing  → feature engineering → run/   │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  CORE ANALYSIS                                       │
│  03_temporal_patterns  → when is the grid cleanest? │
│  04_scheduling_sim     → how much can we save?      │
│  05_forecast_accuracy  → can we trust forecasts?    │
│  06_heuristics         → what rules should we use?  │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  VALIDATION                                          │
│  07_advanced_analysis  → are the rules robust?      │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  EXTENDED / OPERATIONAL                              │
│  08_grid_stress        → when NOT to run            │
│  09_shutdown_planning  → maintenance window timing  │
│  10_forecast_horizon   → forecast vs heuristic?     │
│  11_threshold_buckets  → traffic light system       │
│  12_multiday_optim     → weekly production planning │
│  13_grafana_deploy     → live operator dashboard    │
└─────────────────────────────────────────────────────┘
```

---

## Run Order

### First-time full pipeline
```bash
python 00_validate_data.py          # Optional but recommended
python 01_data_collection.py        # ~20-30 min
python 02_data_processing.py        # ~2-5 min
python 03_temporal_patterns.py      # ~1 min
python 04_scheduling_simulation.py  # ~5-10 min
python 05_forecast_accuracy.py      # ~2 min (requires forecast data)
python 06_heuristics.py             # ~1 min
python 07_advanced_analysis.py      # ~5 min
python 08_grid_stress.py            # ~2 min
python 09_shutdown_planning.py      # ~2 min
python 10_forecast_horizon.py       # ~3 min (requires forecast data)
python 11_threshold_buckets.py      # ~2 min
python 12_multiday_optimization.py  # ~5 min
python 13_grafana_operator_deploy.py  # ~1 min (run after 11)
```

### Re-running analysis only (data unchanged)
```bash
# Edit RUN_FOLDER in each script to point to your run, then run whichever scripts you need
python 03_temporal_patterns.py
python 06_heuristics.py
# etc.
```

### Adding a new region
```bash
# 1. Add region to config.py REGIONS dict
# 2. Fetch data:
python 01_data_collection.py     # Fetches only the new region (smart cache)
python 02_data_processing.py     # Rebuilds combined dataset
# 3. Re-run all analysis scripts
```

---

## Script Reference

Scripts 03–13 all read from a run folder created by 02. They write only to `figures/` and `outputs/` inside that run folder and are safe to re-run at any time without touching `processed/`. Unless noted otherwise, re-running a script just overwrites its previous outputs.

---

### 00 — validate_data.py

**Purpose:** Audit the `library/` before running analysis. Catches missing data, coverage gaps, and distribution anomalies that would silently corrupt downstream results.

**When to run:** Before any new analysis run, especially after adding regions or fetching new date ranges. Also useful for diagnosing errors like "partial forecast data exists."

**Inputs:**
- `library/{signal}/{data_type}/{REGION}.parquet` files

**Key config:**
```python
SIGNAL = "co2_moer"
REGIONS_TO_VALIDATE = ["CAISO_NORTH", "SPP_KANSAS", ...]
DATA_TYPES_TO_CHECK = ["historical", "forecast"]
EXPECTED_START = datetime(2022, 1, 1)
EXPECTED_END = datetime(2024, 12, 31)
OUTPUT_DIR = Path("validation_outputs")
```

**Outputs:**
- `outputs/data_validation_report.md` — detailed completeness report per region
- `outputs/data_quality_summary.csv` — per-region stats (mean, std, missing %, outlier flags)
- `figures/validation_distributions.png` — box plots per region for visual QC

**What it checks:**
- Date range coverage vs expected (identifies gaps)
- Missing interval counts and percentages
- Distribution statistics (flags regions with anomalous MOER ranges)
- Forecast data completeness (often the source of module 05/10 errors)

**Assumptions:**
- 5-minute interval data (288 points/day); gaps flagged as missing rather than interpolated
- Outlier detection uses IQR method; doesn't remove data, just flags it

---

### 01 — data_collection.py (v2)

**Purpose:** Pull historical or forecast MOER/AOER/health_damage data from the WattTime API into the `library/`. Intelligently checks what already exists and only fetches missing ranges.

**When to run:** Once per signal/region/date range combination. Re-running is safe — it will skip already-collected data.

**Inputs:**
- WattTime API credentials in `config.py`
- WattTime research-tier access (required for historical data)

**Key config:**
```python
SIGNAL = "co2_aoer"                     # "co2_moer", "co2_aoer", or "health_damage"
REGIONS_TO_FETCH = ["MISO_INDIANAPOLIS", "CAISO_NORTH", ...]
START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2024, 12, 31)
DATA_TYPE = "historical"                # or "forecast"
MAX_WORKERS = 1                         # Parallel region fetching (increase with caution)
API_CALL_DELAY = 0.0                    # Seconds between calls; increase if 429 errors
```

**Outputs (to `library/`):**
- `library/{signal}/historical/{REGION}.parquet` — raw timestamped MOER values
- `library/catalog.json` — updated index of available data

**Performance notes:**
- Uses `ThreadPoolExecutor` for parallel region fetching
- Monthly incremental saves protect against crashes mid-fetch
- Smart cache check: compares existing date coverage against requested range and only fetches gaps

**Assumptions:**
- WattTime API returns 5-minute interval data
- Research-tier access provides full historical range; standard tier may be limited
- `forecast` data type returns point-in-time forecast snapshots at 5-min intervals with multiple horizon columns

**Common errors:**
- `403` on a region → not in your subscription tier
- `429` → hit rate limit; increase `API_CALL_DELAY` or reduce `MAX_WORKERS`
- Partial data → run `00_validate_data.py` to diagnose gaps

---

### 02 — data_processing.py

**Purpose:** Reads raw parquet files from `library/`, engineers features (timezone conversion, hour/season/weekday labels, rolling stats), and writes a processed dataset to a new timestamped run folder.

**When to run:** After 01, before any analysis script (03-12). Creates the `run_config.json` and processed parquets that all downstream scripts depend on.

**Inputs:**
- `library/{signal}/{data_type}/{REGION}.parquet`

**Key config:**
```python
RUN_NAME = "moer_6region_analysis"
SIGNAL = "co2_moer"
REGIONS_TO_ANALYZE = ["CAISO_NORTH", "SPP_KANSAS", ...]
DATA_TYPES = ["historical"]             # Add "forecast" if needed for 05/10
```

**Outputs (to `runs/YYYY-MM-DD_{RUN_NAME}/`):**
- `run_config.json` — records what was analyzed (signal, regions, date range, script versions)
- `processed/data_5min.parquet` — all regions combined, 5-min interval data with feature columns
- `processed/data_hourly.parquet` — hourly aggregates, all regions combined
- `processed/daily_statistics.parquet` — daily summary stats, all regions combined
- `processed/data_forecast.parquet` — forecast data (only if `"forecast"` in `DATA_TYPES`)

**Feature columns added:**
- `hour`, `day_of_week`, `month`, `year`, `season`
- `is_weekend`, `is_peak` (4–8pm by default)
- Local timezone conversion (uses region metadata from `config.py`)

**Assumptions:**
- All regions converted to their local timezone for analysis; UTC stored in library
- Hourly aggregation uses mean of 5-min values; no gap-filling (gaps remain NaN)
- Season definitions: Spring (Mar-May), Summer (Jun-Aug), Fall (Sep-Nov), Winter (Dec-Feb)

---

### 03 — temporal_patterns.py (v4)

**Purpose:** Characterizes MOER patterns across time dimensions — hour of day, season, weekday vs weekend, year-over-year. The foundational "when is the grid cleanest?" analysis.


**Inputs:**
- `processed/data_hourly_{REGION}.parquet` from run folder

**Key config:**
```python
RUN_FOLDER = "2026-03-04_AOER_6RegionSummary_V1"
FIXED_YLIM = (0, 1600)           # Y-axis limits for hourly plots
FIXED_HEATMAP_RANGE = (0, 1600)  # Color scale range for heatmaps
```

**Outputs:**

| File | Description |
|------|-------------|
| `figures/03_hourly_profile_{region}.png` | Mean ± percentile bands by hour |
| `figures/03_hourly_density_{region}.png` | Distribution density by hour |
| `figures/03_hourly_by_season_{region}.png` | Hourly profiles split by season |
| `figures/03_heatmap_median_{region}.png` | Median MOER: hour × month heatmap |
| `figures/03_heatmap_mean_{region}.png` | Mean MOER: hour × month heatmap |
| `figures/03_weekday_weekend_{region}.png` | Weekday vs weekend comparison |
| `figures/03_hourly_all_regions.png` | Multi-region overlay |
| `figures/03_seasonal_all_regions.png` | Seasonal comparison across regions |
| `figures/03_yoy_trend_{region}.png` | Year-over-year trend |
| `figures/03_annual_median_comparison.png` | Annual medians cross-region |
| `figures/03_daily_variability.png` | Intraday range distribution |
| `figures/03_daily_range_by_season.png` | Range by season |
| `outputs/temporal_pattern_summary.csv` | Numerical summary: mean/median/spread by hour and season per region |

**Key metric:** Hourly MOER spread (max - min within a day) — primary indicator of scheduling opportunity.

**Assumptions:**
- Uses median rather than mean as primary statistic (MOER distributions are right-skewed in fossil-heavy grids)
- Both mean and median heatmaps generated for comparison; prefer median for skewed regions (MISO, ERCOT)
- YoY analysis requires ≥2 years of data

---

### 04 — scheduling_simulation.py

**Purpose:** Simulates the emissions savings achievable by optimally timing a job within a scheduling window, compared to random/fixed timing. Answers "how much can we actually save?"


**Inputs:**
- `processed/data_5min.parquet` from run folder

**Key config:**
```python
RUN_FOLDER = "..."
# All simulation parameters come from config.py:
#   JOB_DURATIONS          - list of job lengths to simulate (hours)
#   SHIFTS                 - shift definitions (day/evening/night with start/end hours)
#   FLEXIBILITY_WINDOWS_HOURS - scheduling window sizes to test
#   REFERENCE_JOB_KWH      - job energy consumption for absolute emissions calc
#   CONSISTENCY_THRESHOLD  - minimum fraction of years a rule must hold to be "consistent"
```

**Outputs:**

| File | Description |
|------|-------------|
| `figures/04_savings_by_duration_{region}.png` | Savings % vs job duration per region |
| `figures/04_savings_by_season_{region}.png` | Seasonal savings breakdown per region |
| `figures/04_savings_distribution_{region}.png` | Distribution of per-event savings |
| `figures/04_savings_comparison_all_regions.png` | Cross-regional savings comparison |
| `figures/04_consistency_heatmap.png` | Heuristic consistency across years |
| `figures/04_flexibility_vs_savings.png` | Savings vs scheduling window length |
| `outputs/scheduling_simulation_results.parquet` | Per-event results: optimal vs baseline savings |
| `outputs/scheduling_summary.csv` | Summary stats: median savings % by region/season/duration |
| `outputs/consistency_scores.csv` | Per-region heuristic consistency scores |

**Key metric:** Median savings % by region and season; consistency score (fraction of years the rule holds).

**Assumptions:**
- "Optimal" = lowest average MOER start time within the shift window for a given job duration
- "Baseline" = random start within the same shift window
- Simulation runs across all defined shifts (day/evening/night) and all job durations in `JOB_DURATIONS`
- Night shift crosses midnight (22:00–06:00); handled explicitly
- Jobs run continuously; no power variation modeled within the job window

---

### 05 — forecast_accuracy.py

**Purpose:** Evaluates how well WattTime's forecast MOER matches actual historical MOER. Determines if day-ahead scheduling decisions are reliable enough to use.

**When to run:** After 02, but only if the run includes both `historical` and `forecast` data types. Set `DATA_TYPES = ["historical", "forecast"]` in 02_data_processing.py.

**Inputs:**
- `processed/data_5min_{REGION}.parquet` with both historical and forecast columns
- `MAX_HORIZON_HOURS = 72.0` (forecasts beyond this are dropped at load time — memory management)

**Key config:**
```python
RUN_FOLDER = "..."
MAX_HORIZON_HOURS = 72.0
```

**Outputs:**

| File | Description |
|------|-------------|
| `figures/05_forecast_vs_actual_scatter.png` | Forecast vs actual scatter by horizon |
| `figures/05_mae_by_horizon.png` | MAE degradation as horizon increases |
| `figures/05_scheduling_decision_accuracy.png` | Did forecast pick the right hour? |
| `figures/05_error_by_hour.png` | Error patterns by hour of day |
| `figures/05_error_by_season.png` | Error patterns by season |
| `outputs/forecast_accuracy_by_horizon.csv` | MAE, MAPE, RMSE at each horizon (1h, 2h, 4h, …, 72h) |
| `outputs/forecast_decision_accuracy.csv` | % of decisions where forecast picked the optimal window |

**Key metric:** MAE at 24h horizon (relevant for day-ahead scheduling) and decision accuracy (% of time forecast would choose a window within X% of optimal).

**Assumptions:**
- Forecast accuracy is evaluated against actual historical values at matching timestamps
- "Decision accuracy" = forecast selects an hour within the best N hours (configurable tolerance)
- Large forecast dataset (~3 years × 6 regions × 72h horizon) is memory-intensive; `MAX_HORIZON_HOURS` trims this aggressively — keep at 72 unless specifically studying longer horizons

---

### 06 — heuristics.py (v3)

**Purpose:** Synthesizes temporal pattern and scheduling simulation results into concrete, actionable scheduling rules. The output of this script is the primary research deliverable — the heuristics table.

**When to run:** After 03 and 04.

**Inputs:**
- `outputs/temporal_pattern_summary.csv` (from 03)
- `outputs/scheduling_summary.csv` (from 04)

**Key config:**
```python
RUN_FOLDER = "..."
# Inherits SHIFTS and REFERENCE_JOB_KWH from config.py
```

**Outputs:**

| File | Description |
|------|-------------|
| `figures/06_heuristics_summary.png` | Best window per region, color-coded by savings |
| `figures/06_seasonal_recommendations.png` | Season-specific rule variation |
| `figures/06_seasonal_savings_distribution.png` | Savings distribution by season |
| `figures/06_optimal_hour_by_season.png` | Heatmap of optimal start hour |
| `figures/06_consistency_heatmap.png` | How consistent are the rules year-over-year? |
| `figures/06_cumulative_savings.png` | Cumulative savings if rules followed |
| `outputs/heuristics_table.csv` | The rules: region × season → optimal window, savings %, consistency score |
| `outputs/heuristics_report.md` | Human-readable summary of rules with confidence notes |

**Key metric:** Best scheduling window (start hour + duration), expected savings %, and consistency score (how often the rule holds across years).

**Assumptions:**
- Heuristics are derived from historical data (2022–2024); implicitly assumes future patterns resemble past
- Consistency score = fraction of years where the recommended window outperforms random baseline
- Rules are region-specific; no attempt to generalize across regions at this stage (that's 07's job)

---

### 07 — advanced_analysis.py

**Purpose:** Stress-tests and validates the heuristics from 06. Answers: do the rules hold under realistic operational constraints? Would they have worked on held-out data? Are there distinct grid behavior regimes?

**When to run:** After 06. Optional but important before claiming the heuristics are robust.

**Sections (each independently toggleable):**

**1. Robustness Analysis**
- Year-over-year stability scoring
- Threshold-based rules vs time-based rules comparison
- Holdout validation: train on 2022–2023, test on 2024

**2. Operation Constraints**
- Duration sensitivity (how does savings change with job length?)
- Deadline scheduling (jobs with hard deadlines)
- Shift-constrained windows (only certain hours available)

**3. Grid Behavior**
- Intraday volatility characterization
- K-means regime clustering (what "modes" does each grid operate in?)
- MISO-specific investigation (MISO_INDIANAPOLIS has distinct fossil dispatch patterns)

**4. Forecast Value** (auto-skipped if no forecast data)
- Achieved savings using forecast vs theoretical maximum

**Key config:**
```python
RUN_FOLDER = "..."
RUN_ROBUSTNESS = True
RUN_CONSTRAINTS = True
RUN_GRID_BEHAVIOR = True
RUN_FORECAST_VALUE = True
HOLDOUT_TRAIN_YEARS = [2022, 2023]
HOLDOUT_TEST_YEARS = [2024]
THRESHOLD_PERCENTILES = [10, 25, 50]
```

**Outputs:**
- `figures/07_stability_heatmap.png`, `07_holdout_validation.png`, `07_regime_clustering.png`, and more
- `outputs/07_stability.csv`, `07_holdout_results.csv`, `07_constraint_sensitivity.csv`

**Key metric:** Stability score (heuristic consistency across years); holdout savings vs in-sample savings (checks for overfitting).

**Assumptions:**
- Regime clustering uses K-means on hourly MOER shape features; number of clusters = 3 by default
- Holdout split is temporal (earlier years train, later year tests) to respect time ordering
- Constraint analysis assumes jobs cannot be split across shifts

---

### 08 — grid_stress.py

**Purpose:** Identifies periods of extreme emissions (stress events) — when NOT to run energy-intensive operations. Characterizes frequency, duration, temporal patterns, and whether forecasts provide useful warning.


**Key config:**
```python
RUN_FOLDER = "..."
STRESS_PERCENTILE_HIGH = 95        # Top 5% = severe
STRESS_PERCENTILE_MODERATE = 90    # Top 10% = moderate
MIN_CONSECUTIVE_HOURS = 2          # Minimum duration to count as an event
GAP_HOURS_TO_MERGE = 1             # Merge events separated by ≤ this many hours
RUN_FORECAST_WARNING = True        # Requires forecast data
```

**Analysis sections:**
1. Event identification — top 5%/10% MOER periods, grouped into consecutive events
2. Temporal characterization — monthly and hourly distribution, weekday vs weekend, YoY trends
3. Regional correlation — do regions spike simultaneously? (safe harbor analysis)
4. Forecast warning — did day-ahead forecasts predict stress events? What was the lead time?

**Outputs:**

| File | Description |
|------|-------------|
| `figures/08_stress_monthly_heatmap.png` | Event frequency by month × region |
| `figures/08_stress_hourly_distribution.png` | Hour-of-day distribution of stress events |
| `figures/08_regional_correlation.png` | Correlation matrix of stress timing across regions |
| `figures/08_forecast_warning_leadtime.png` | Distribution of forecast lead time before stress events |
| `outputs/08_stress_events.csv` | Each event: start, end, duration, peak MOER, region |
| `outputs/08_stress_summary.csv` | Per-region summary: event count, mean duration, worst months |

**Key metric:** Event frequency (events/year), mean duration (hours), and % of events with >4h forecast warning.

**Assumptions:**
- Stress events defined regionally (a 95th percentile event in BPA is a different absolute MOER than in MISO)
- Events < `MIN_CONSECUTIVE_HOURS` are classified as transient spikes, not events
- Regional correlation uses Pearson correlation on binary stress indicator (1/0 per hour)

---

### 09 — shutdown_planning.py

**Purpose:** Identifies optimal weeks and months for planned facility downtime (maintenance shutdowns) to maximize avoided emissions. A high-MOER period is actually a good time to be offline.


**Key config:**
```python
RUN_FOLDER = "..."
SHUTDOWN_DURATIONS_WEEKS = [1, 2, 3, 4]    # Scenarios to analyze
COMMON_SHUTDOWNS = {                         # US industrial calendar benchmarks
    "christmas_ny": [52, 1],
    "july_4th": [27],
    "thanksgiving": [47],
    "memorial_day": [22],
    "labor_day": [36],
}
```

**Analysis sections:**
1. Weekly rankings — all 52 weeks ranked by average MOER, YoY consistency
2. Monthly rankings — month-level patterns and best months for downtime
3. Optimal maintenance windows — if you have N weeks of annual downtime, which N weeks?
4. Holiday analysis — how do common industrial shutdown periods align with grid patterns?

**Outputs:**

| File | Description |
|------|-------------|
| `figures/09_weekly_ranking_{region}.png` | All 52 weeks ranked by MOER |
| `figures/09_shutdown_value_curve.png` | Diminishing returns: value of 1st, 2nd, 3rd shutdown week |
| `figures/09_holiday_alignment.png` | Common shutdown periods vs actual optimal weeks |
| `figures/09_monthly_heatmap.png` | Monthly MOER patterns across regions |
| `outputs/09_weekly_rankings.csv` | All weeks ranked with mean MOER, YoY consistency |
| `outputs/09_optimal_windows.csv` | Best N-week combinations per region |
| `outputs/09_holiday_opportunity_cost.csv` | Gap between current practice and optimal timing |

**Key metric:** Best maintenance weeks and the MOER differential vs current common shutdown periods (opportunity cost of status quo timing).

**Assumptions:**
- "Best" shutdown week = highest average MOER (you'd be avoiding the most emissions by being offline)
- Assumes facility would otherwise operate at full capacity during the shutdown week
- Calendar week numbering uses ISO 8601 (week 1 = first week with a Thursday)
- Cross-year averaging for weekly rankings requires ≥2 years of data

---

### 10 — forecast_horizon.py

**Purpose:** Determines the practical planning horizon — how far ahead forecasts remain reliable enough to use for scheduling, and at what point you should fall back to heuristics.

**When to run:** After 02, requires both historical and forecast data in the run.

**Key config:**
```python
RUN_FOLDER = "..."
HORIZONS = [1, 2, 4, 6, 8, 12, 18, 24, 36, 48, 72]   # Hours ahead to evaluate
SAVINGS_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]         # Fraction of theoretical max
HOUR_TOLERANCE = [0, 1, 2, 3]                            # Hours within optimal = "good"
PEAK_HOURS = list(range(16, 21))                          # For peak-specific analysis
SCHEDULING_WINDOW_HOURS = 8                               # Decision window size
```

**Analysis sections:**
1. Accuracy by horizon — MAE/MAPE at each horizon, finding the accuracy "cliff"
2. Accuracy by context — seasonal effects, time-of-day effects, peak vs off-peak
3. Decision reliability — probability of picking an optimal or near-optimal window at each horizon
4. Implementation thresholds — recommended cutoff horizon for forecast-based vs heuristic scheduling

**Outputs:**

| File | Description |
|------|-------------|
| `figures/10_accuracy_degradation.png` | MAE vs horizon curve with cliff identification |
| `figures/10_decision_reliability_by_horizon.png` | P(good decision) vs horizon |
| `figures/10_accuracy_by_season.png` | Seasonal forecast accuracy variation |
| `figures/10_peak_vs_offpeak.png` | Peak hour forecast reliability |
| `outputs/10_accuracy_by_horizon.csv` | MAE, MAPE, RMSE at each horizon per region |
| `outputs/10_decision_reliability.csv` | P(within X% of optimal) at each horizon |
| `outputs/10_implementation_thresholds.csv` | Recommended horizon cutoffs per region |

**Key metric:** Horizon at which decision reliability drops below 70% (the "trust boundary" for scheduling).

**Assumptions:**
- Forecast data must be structured as point-in-time snapshots with horizon metadata
- "Decision reliability" uses same window size as 04_scheduling_simulation for comparability
- Memory-intensive: large forecast datasets may need `gc.collect()` calls (already implemented)

---

### 11 — threshold_buckets.py

**Purpose:** Simplifies carbon-aware scheduling to a traffic light system (Green/Yellow/Red) that operators can use without API access. Produces lookup tables calibrated to each region's MOER distribution.


**Key config:**
```python
RUN_FOLDER = "..."
GREEN_PERCENTILE = 25      # Bottom 25% → run freely
RED_PERCENTILE = 75        # Top 25% → defer if possible
MIN_PRODUCTION_HOURS_PER_DAY = 8
TRANSITION_LOOKAHEAD_HOURS = [1, 2, 3, 4]
```

**Analysis sections:**
1. Threshold definition — calculate Green/Yellow/Red cutoff MOER values per region
2. Bucket distribution — % of hours in each bucket by region, season, hour of day
3. Transition patterns — Markov-style probabilities (given Green now, P(still Green in 1h/2h/3h)?)
4. Savings quantification — if you defer all Red hours to next Green window, how much do you save?

**Outputs:**

| File | Description |
|------|-------------|
| `figures/11_traffic_light_summary.png` | Distribution of bucket occupancy per region |
| `figures/11_bucket_by_hour_{region}.png` | Hour-of-day bucket distribution |
| `figures/11_transition_matrix.png` | Bucket-to-bucket transition probabilities |
| `figures/11_availability_heatmap.png` | Green hour availability: hour × month |
| `outputs/11_threshold_values.csv` | Green/Yellow/Red cutoff MOER values per region |
| `outputs/11_bucket_distribution.csv` | % in each bucket by region/season/hour |
| `outputs/11_transition_probabilities.csv` | Markov transition matrix per region |
| `outputs/11_deferral_savings.csv` | Expected savings from Red-to-Green deferral strategy |

**Key metric:** Green hour availability (% of production hours that fall in Green), and expected savings from simple Red deferral vs optimal scheduling.

**Assumptions:**
- Thresholds are historical percentiles — they will not perfectly match future distributions
- Transition probabilities are stationary across seasons (season-stratified version possible but not default)
- `MIN_PRODUCTION_HOURS_PER_DAY` is used to check whether enough Green hours exist to meet production needs

---

### 12 — multiday_optimization.py

**Purpose:** Extends single-day scheduling to weekly production planning. If a facility has flexibility to shift production between days of the week, how should they allocate hours to minimize emissions?


**Key config:**
```python
RUN_FOLDER = "..."
DAILY_PRODUCTION_HOURS = 8       # Target hours per day
WEEKLY_PRODUCTION_HOURS = 40     # Total weekly target
FLEXIBILITY_WINDOWS = [1, 2, 3, 5, 7]   # Days of flexibility to compare
MIN_HOURS_PER_DAY = 4
MAX_HOURS_PER_DAY = 12
CONSERVATIVE_PERCENTILE = 25     # Conservative strategy target
AGGRESSIVE_PERCENTILE = 10       # Aggressive strategy target
```

**Analysis sections:**
1. Multi-day patterns — weekly MOER cycles, weekday vs weekend, best days to concentrate production
2. Production shifting scenarios — front-load vs back-load vs distribute evenly
3. Flexibility value curve — savings from 1-day vs 2-day vs 5-day flexibility
4. Risk-adjusted scheduling — expected savings vs variability (conservative vs aggressive strategies)

**Outputs:**

| File | Description |
|------|-------------|
| `figures/12_weekly_moer_cycle.png` | Average MOER by day of week per region |
| `figures/12_flexibility_curve.png` | Savings vs flexibility window length |
| `figures/12_shifting_scenarios.png` | Front-load vs back-load comparison |
| `figures/12_risk_adjusted.png` | Expected savings vs variance trade-off |
| `outputs/12_weekly_scenarios.csv` | Savings by scenario and flexibility window |
| `outputs/12_flexibility_value.csv` | Marginal value of each additional day of flexibility |

**Key metric:** Marginal value of flexibility — how much additional savings each extra day of production flexibility provides (diminishing returns curve).

**Assumptions:**
- Flexibility is symmetric (can shift to any day in the window, not just forward)
- Minimum/maximum daily hours constraints prevent the optimizer from concentrating all production in one day
- Weekly quota must be met exactly; no carryover between weeks
- Uses historical weekly averages, not forecast; for forward-looking planning use with 10's horizon guidance

---

### 13 — grafana_operator_deploy.py

**Purpose:** Generates all static artifacts needed to run a live Green/Yellow/Red traffic light dashboard in Grafana for shop-floor operators. This is the deployment step that takes 11's thresholds and makes them usable in real-time.

**When to run:** After 11_threshold_buckets.py (requires threshold outputs to exist).

**Key config:**
```python
RUN_FOLDER = "..."
DEPLOY_REGION = "MISO_INDY"                    # One region per deployment
GRAFANA_DATASOURCE_NAME = "InfluxDB-WattTime"  # Must match your Grafana instance
```

**What it generates:**

| Output | Description |
|--------|-------------|
| `outputs/13_grafana/thresholds_{REGION}.json` | Grafana value mappings: MOER value → color + label |
| `outputs/13_grafana/hourly_lookup_{REGION}.csv` | Season × hour → expected bucket (reference table) |
| `outputs/13_grafana/13_grafana_dashboard.json` | Ready-to-import Grafana dashboard JSON |
| `outputs/13_grafana/15_operator_card.png` | Printable reference card with thresholds + recommended actions |
| `figures/13_hourly_heatmap.png` | Expected bucket by hour × season |
| `figures/13_operator_reference.png` | Visual version of the operator card |

**Dashboard panels included:**
- Live traffic light (Stat/Gauge panel with color-coded MOER)
- Hourly heatmap (expected conditions by hour of day)
- Shift summary (bucket distribution for current shift)
- MOER trend with threshold bands

**Grafana setup:**
1. Ensure WattTime MOER data is flowing into InfluxDB (or your configured data source)
2. In Grafana: Dashboards → Import → upload `13_grafana_dashboard.json`
3. Set the data source variable to match your InfluxDB instance name
4. Threshold values are pre-loaded from the region's historical MOER distribution

**Assumptions:**
- Operator side requires only a current MOER value (no API subscription needed at runtime)
- Thresholds are static (calibrated from `11_threshold_buckets.py`); recalibrate annually or after major grid changes
- One dashboard per region/facility; deploy separately for each location
- InfluxDB is the assumed time-series backend; adjust field/measurement names in config if using another source

---

## Configuration Reference (`config.py`)

`config.py` is the single source of truth for shared constants. Script-level CONFIG blocks (the `▼▼▼ USER CONFIG ▼▼▼` sections) override or extend these for each run.

**What lives in `config.py`** — shared across all scripts:

```python
# Credentials
WATTTIME_USERNAME = "your_username"
WATTTIME_PASSWORD = "your_password"

# API settings
API_MAX_DAYS_PER_REQUEST = 32
API_RATE_LIMIT = 3000           # requests per 5 minutes

# Signals with metadata (name, unit_label, typical_range)
SIGNALS = {"co2_moer": {...}, "co2_aoer": {...}, "health_damage": {...}}

# Full region definitions (timezone, coordinates, description)
# Includes all MISO, PJM, CAISO, ERCOT, ISONE, NYISO, SPP subregions
# plus standalone utilities (TVA, BPA, SOCO, etc.) and Canada
REGIONS = {...}

# Region group shortcuts for REGIONS_TO_FETCH / REGIONS_TO_ANALYZE
REGION_GROUPS = {
    "GridMixStudy": ["CAISO_NORTH", "SPP_KANSAS", "BPA", "MISO_INDIANAPOLIS", "ISONE_CT", "ERCOT_NORTHCENTRAL"],
    "US_5REG":      ["MISO_INDIANAPOLIS", "PJM_NJ", "CAISO_NORTH", "ERCOT_EASTTX", "ISONE_NEMA"],
    "AOER_6RegionSummary": ["MISO", "BPA", "CAISO", "SPP", "ERCOT", "ISONE"],
    "AOER_REGIONS": [...],   # All regions with co2_aoer data
    "HEALTH_REGIONS": ["CAISO_NORTH"],  # Only region with health_damage
    # + ISO-level groups: MISO_ALL, PJM_ALL, CAISO_ALL, ERCOT_ALL, etc.
}

# Default date range
DEFAULT_HISTORICAL_START = datetime(2022, 1, 1)
DEFAULT_HISTORICAL_END = datetime(2024, 12, 31)

# Shift definitions (used by 04_scheduling_simulation)
SHIFTS = {
    "day":   {"start": 6,  "end": 14},
    "swing": {"start": 14, "end": 22},
    "night": {"start": 22, "end": 6},
}

# Job durations tested in simulation (hours)
JOB_DURATIONS = [0.5, 1.0, 2.0, 4.0]

# Season definitions (meteorological)
SEASONS = {"winter": [12,1,2], "spring": [3,4,5], "summer": [6,7,8], "fall": [9,10,11]}

# Reference job energy for absolute emissions calculations (kWh)
REFERENCE_JOB_KWH = 2.0

# Scheduling analysis thresholds
CONSISTENCY_THRESHOLD = 0.80        # Min fraction of max savings for a window to count as "consistent"
FLEXIBILITY_WINDOWS_HOURS = [2, 4, 6, 8]

# Data quality
MAX_MISSING_PCT_PER_DAY = 10        # Flag days with more than this % missing intervals

# Figure settings
FIGURE_DPI = 150
FIGURE_SIZE = (10, 6)
```

**What lives in individual script CONFIG blocks** — script-specific, not in `config.py`:

| Script | Script-level parameters |
|--------|------------------------|
| 00 | `REGIONS_TO_VALIDATE`, `DATA_TYPES_TO_CHECK`, `EXPECTED_START/END` |
| 01 | `SIGNAL`, `REGIONS_TO_FETCH`, `START_DATE`, `END_DATE`, `DATA_TYPE`, `MAX_WORKERS`, `API_CALL_DELAY` |
| 02 | `RUN_NAME`, `SIGNAL`, `REGIONS_TO_ANALYZE`, `DATA_TYPES`, `START_DATE`, `END_DATE` |
| 03–06 | `RUN_FOLDER`, axis limit overrides |
| 07 | `RUN_FOLDER`, `RUN_*` toggles, `HOLDOUT_TRAIN/TEST_YEARS`, `THRESHOLD_PERCENTILES` |
| 08 | `RUN_FOLDER`, `STRESS_PERCENTILE_HIGH/MODERATE`, `MIN_CONSECUTIVE_HOURS`, `GAP_HOURS_TO_MERGE` |
| 09 | `RUN_FOLDER`, `SHUTDOWN_DURATIONS_WEEKS`, `COMMON_SHUTDOWNS` |
| 10 | `RUN_FOLDER`, `HORIZONS`, `SAVINGS_THRESHOLDS`, `HOUR_TOLERANCE`, `PEAK_HOURS` |
| 11 | `RUN_FOLDER`, `GREEN_PERCENTILE`, `RED_PERCENTILE`, `MIN_PRODUCTION_HOURS_PER_DAY` |
| 12 | `RUN_FOLDER`, `DAILY/WEEKLY_PRODUCTION_HOURS`, `FLEXIBILITY_WINDOWS`, `MIN/MAX_HOURS_PER_DAY` |
| 13 | `RUN_FOLDER`, `DEPLOY_REGION`, `GRAFANA_DATASOURCE_NAME` |



---

## Data Dependencies

Scripts must be run in dependency order. Most 03–13 scripts can be re-run independently once 02 has created the run folder.

```
01_data_collection
       │
02_data_processing
       │
  ┌────┴────┬──────┬──────┐
  03        04     05     │
  │         │      │      │
  └────┬────┘      10     │
       06                 07
       │
  ┌────┼────┬────┬────┐
  08   09   11   12   13*

* 13 requires 11 outputs
```

---

## Developing a New Script

All analysis scripts follow the same pattern. If you're adding a new module (e.g., `14_something.py`), use this as a template:

**1. Script header and imports**
```python
"""
14_something.py - Short description

Longer description of what it analyzes and why.

Usage:
    1. Run 02_data_processing.py first
    2. Edit CONFIG section below
    3. Run: python 14_something.py

Output (in run folder):
    - figures/14_*.png
    - outputs/14_*.csv
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (REGIONS, SEASONS, RUNS_DIR, FIGURE_DPI, FIGURE_SIZE,
                    REGION_COLORS, SEASON_COLORS, get_signal_metadata, get_unit_label)
```

**2. CONFIG block** — keep it at the top, edit-only (no CLI args)
```python
# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================
RUN_FOLDER = "2026-03-04_MyRun"   # Set to None to auto-detect most recent
MY_PARAM = 42
# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================
```

**3. Standard run folder resolution** — copy this boilerplate exactly
```python
def get_run_dir() -> Path:
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
            sys.exit(1)
        return run_dir
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    if not runs:
        print("ERROR: No runs found. Run 02_data_processing.py first.")
        sys.exit(1)
    return runs[0]
```

**4. Load data from the run folder** — not from `library/` directly
```python
def load_data(run_dir: Path) -> pd.DataFrame:
    # Use data_5min for high-resolution analysis
    df = pd.read_parquet(run_dir / "processed" / "data_5min.parquet")
    # Or data_hourly for pattern analysis
    # df = pd.read_parquet(run_dir / "processed" / "data_hourly.parquet")
    return df
```

**5. Save outputs with your script's number prefix**
```python
# Figures
fig.savefig(run_dir / "figures" / "14_my_figure.png", dpi=FIGURE_DPI, bbox_inches="tight")

# CSVs
results_df.to_csv(run_dir / "outputs" / "14_my_results.csv", index=False)
```

**6. Mark the script run in `run_config.json`**
```python
def mark_script_run(run_dir: Path):
    config_path = run_dir / "run_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    config["scripts_run"].append({"script": "14_something", "timestamp": datetime.now().isoformat()})
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)
```

**Conventions to follow:**
- Prefix all output files with your script number (`14_`)
- Use `REGION_COLORS` and `SEASON_COLORS` from config for consistent plot styling
- Loop over regions rather than hardcoding; read the region list from `run_config.json`
- Use `get_unit_label(signal)` for axis labels rather than hardcoding units
- Keep analysis functions separate from plotting functions
- Print progress to console — these scripts can run for several minutes

---

## Troubleshooting


**"Run folder not found"** → Check the `RUN_FOLDER` variable in the script matches an actual folder name in `runs/`. Folder names are date-prefixed: `YYYY-MM-DD_name`.

**"No forecast data"** → Scripts 05 and 10 require a run created with `DATA_TYPES = ["historical", "forecast"]`. Re-run 02 with forecast data included.

**API 429 error** → Increase `API_CALL_DELAY` in 01 or reduce `MAX_WORKERS` to 1.

**API 403 on a region** → That region is not in your WattTime subscription tier. Check access at the WattTime account portal.

**Memory errors in 05/10** → Reduce `MAX_HORIZON_HOURS` (72 is already conservative). The forecast dataset is the largest in the pipeline.

**Windows encoding error** → Add `encoding="utf-8"` to any `open()` file write calls.

**SPP_KANSAS threshold anomaly** → Known distribution quirk — SPP has occasional MOER spikes that push the 95th percentile significantly higher than other regions. Run 00_validate_data.py to check and decide whether to clip outliers before analysis.

**Runs directory getting large** → `runs/` is fully disposable. Delete old runs freely; re-run 02 onward to regenerate. `library/` is the only data that can't be easily regenerated (requires API calls).
