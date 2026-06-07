# WattTime Heuristic Development Tool

## Complete Guide to Carbon-Aware Manufacturing Scheduling Analysis

**Author:** Andrew  
**Version:** 2.0  
**Last Updated:** February 2026  
**Purpose:** Research tool for developing and validating carbon-aware manufacturing scheduling heuristics

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Data Flow](#3-data-flow)
4. [Module Reference](#4-module-reference)
   - [Core Pipeline (01-06)](#41-core-pipeline)
   - [Advanced Analysis (07)](#42-advanced-analysis)
   - [Extended Analysis (08-12)](#43-extended-analysis)
5. [Configuration](#5-configuration)
6. [Usage Guide](#6-usage-guide)
7. [Output Interpretation](#7-output-interpretation)
8. [Research Applications](#8-research-applications)

---

## 1. Overview

### What This Tool Does

This tool analyzes historical grid emissions data from WattTime to develop actionable scheduling heuristics for manufacturing operations. It answers questions like:

- When are the best/worst times to run energy-intensive operations?
- How much emissions reduction is achievable through scheduling?
- How reliable are forecasts for planning purposes?
- What simple rules can operators follow without complex systems?

### Key Concepts

| Term | Definition |
|------|------------|
| **MOER** | Marginal Operating Emissions Rate — the emissions intensity of the *next* unit of electricity on the grid (lbs CO₂/MWh) |
| **Heuristic** | A simple, actionable rule derived from data analysis (e.g., "Run CNC operations between 10am-2pm in summer") |
| **Scheduling Window** | A contiguous time period during which an operation can be scheduled |
| **Stress Event** | A period of unusually high grid emissions (top 5-10% of MOER values) |

### Research Context

Traditional LCA uses *average* grid emissions factors. This tool uses *marginal* emissions (MOER), which better reflects the impact of load-shifting decisions. The key insight: when you shift load, you're affecting which power plants run at the margin, not the average grid mix.

---

## 2. Architecture

### Project Structure

```
watttime_analysis/
├── config.py                    # Credentials, regions, all parameters
├── 01_data_collection.py        # WattTime API → raw parquet files
├── 02_data_processing.py        # Feature engineering → processed data
├── 03_temporal_patterns.py      # Hourly/seasonal/YoY patterns
├── 04_scheduling_simulation.py  # Job scheduling optimization
├── 05_forecast_accuracy.py      # Forecast vs actual comparison
├── 06_heuristics.py             # Synthesize findings into rules
├── 07_advanced_analysis.py      # Robustness, constraints, grid behavior
├── 08_grid_stress.py            # Extreme event analysis [NEW]
├── 09_shutdown_planning.py      # Strategic maintenance windows [NEW]
├── 10_forecast_horizon.py       # Forecast reliability by horizon [NEW]
├── 11_threshold_buckets.py      # Traffic light decision rules [NEW]
├── 12_multiday_planning.py      # Weekly production optimization [NEW]
│
├── runs/                        # Output organized by analysis run
│   └── YYYY-MM-DD_signal_name/
│       ├── run_config.json      # Parameters for this run
│       ├── processed/           # Processed parquet files
│       ├── figures/             # Generated plots
│       └── outputs/             # CSV tables and reports
│
├── data/                        # Legacy structure (if not using runs/)
│   ├── raw/                     # Raw API data
│   └── processed/               # Processed datasets
│
└── utils/                       # Shared utilities
```

### Module Dependencies

```
                    ┌─────────────────────────────────────┐
                    │         01_data_collection          │
                    │  (WattTime API → raw parquet)       │
                    └─────────────────┬───────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │         02_data_processing          │
                    │  (Feature engineering, time zones)  │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ 03_temporal  │  │ 04_schedule  │  │ 05_forecast  │
         │   patterns   │  │  simulation  │  │   accuracy   │
         └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                │                 │                 │
                └─────────────────┼─────────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────────────┐
                    │           06_heuristics             │
                    │  (Synthesize into actionable rules) │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ 07_advanced  │  │  08-12 NEW   │  │    Future    │
         │   analysis   │  │   modules    │  │  extensions  │
         └──────────────┘  └──────────────┘  └──────────────┘
```

---

## 3. Data Flow

### Input Data

| Source | Endpoint | Resolution | History |
|--------|----------|------------|---------|
| WattTime Historical | `/v3/historical` | 5-minute | 2+ years |
| WattTime Forecast | `/v3/forecast` | 5-minute | 24-72 hours ahead |

### Processed Data Files

| File | Contents | Used By |
|------|----------|---------|
| `data_5min.parquet` | Raw MOER at 5-min resolution with time features | Scheduling simulation, volatility |
| `data_hourly.parquet` | Hourly aggregates (mean, min, max, std) | Temporal patterns, heuristics |
| `daily_statistics.parquet` | Daily summaries | Regime clustering, stress events |
| `data_forecast.parquet` | Historical forecasts for accuracy analysis | Forecast modules |

### Key Data Columns

```python
# After processing, data includes:
{
    "point_time": "2024-01-15 14:30:00-05:00",  # Local time
    "point_time_utc": "2024-01-15 19:30:00+00:00",
    "region": "MISO_INDIANAPOLIS",
    "value": 1245.3,  # MOER in lbs CO₂/MWh
    "hour": 14,
    "day_of_week": 0,  # Monday
    "month": 1,
    "season": "winter",
    "year": 2024,
    "is_weekend": False,
    "date": "2024-01-15"
}
```

---

## 4. Module Reference

### 4.1 Core Pipeline

#### 01_data_collection.py

**Purpose:** Pull historical MOER and forecast data from WattTime API.

**Inputs:**
- WattTime credentials (in config.py)
- Region codes
- Date range

**Outputs:**
- `data/raw/{region}_moer_historical.parquet`
- `data/raw/{region}_forecast_{month}.parquet`

**Key Parameters:**
```python
HISTORICAL_START = "2022-01-01"
HISTORICAL_END = "2024-12-31"
REGION_CODES = ["MISO_INDIANAPOLIS", "CAISO_NORTH", ...]
```

**Runtime:** ~20-30 minutes for 3 years × 5 regions

---

#### 02_data_processing.py

**Purpose:** Clean data, convert time zones, add temporal features.

**Inputs:**
- Raw parquet files from 01

**Outputs:**
- `processed/data_5min.parquet`
- `processed/data_hourly.parquet`
- `processed/daily_statistics.parquet`
- `run_config.json`

**Key Operations:**
1. Convert UTC to local time per region
2. Add hour, day_of_week, month, season, year columns
3. Aggregate to hourly (mean, min, max, std)
4. Calculate daily statistics

**Runtime:** ~2-5 minutes

---

#### 03_temporal_patterns.py

**Purpose:** Characterize MOER patterns by hour, season, year.

**Inputs:**
- Processed hourly data

**Outputs:**
- `figures/03_hourly_profile_{region}.png` — 24-hour MOER curve
- `figures/03_seasonal_heatmap_{region}.png` — Hour × Season matrix
- `figures/03_yoy_comparison.png` — Year-over-year stability
- `outputs/temporal_pattern_summary.csv`

**Key Findings Format:**
```
MISO Indianapolis:
  Mean MOER: 1377.1 lbs/MWh
  Best hour: 14:00 (1320.5)
  Worst hour: 19:00 (1422.0)
  Hourly spread: 101.5 lbs/MWh (7.4% variation)
```

---

#### 04_scheduling_simulation.py

**Purpose:** Simulate scheduling operations to optimal windows, calculate savings.

**Inputs:**
- Processed 5-minute data
- Job durations (default: 2 hours)
- Shift definitions

**Outputs:**
- `figures/04_savings_distribution_{region}.png`
- `figures/04_optimal_windows_{region}.png`
- `outputs/scheduling_results.csv`
- `outputs/consistency_scores.csv`

**Simulation Logic:**
```
For each day:
    1. Define shift window (e.g., 6am-2pm)
    2. Find all possible 2-hour windows within shift
    3. Calculate average MOER for each window
    4. Compare: optimal window vs baseline (random scheduling)
    5. Record savings percentage
```

---

#### 05_forecast_accuracy.py

**Purpose:** Evaluate WattTime forecast accuracy for scheduling decisions.

**Inputs:**
- Historical forecasts
- Actual MOER data

**Outputs:**
- `figures/05_forecast_error_by_horizon.png`
- `figures/05_forecast_vs_actual_scatter.png`
- `outputs/forecast_accuracy.csv`

**Key Metrics:**
- MAE (Mean Absolute Error) by horizon
- MAPE (Mean Absolute Percentage Error)
- "Would schedule be same?" — directional accuracy

---

#### 06_heuristics.py

**Purpose:** Synthesize all findings into actionable scheduling rules.

**Inputs:**
- Results from 03, 04, 05

**Outputs:**
- `outputs/heuristics_table.csv` — Full table of recommendations
- `outputs/heuristics_report.md` — Prose summary
- `figures/06_heuristics_summary.png`
- `figures/06_seasonal_recommendations.png`

**Output Format:**
| Region | Season | Shift | Best Window | Avg Savings | Consistency |
|--------|--------|-------|-------------|-------------|-------------|
| MISO | Summer | Day (6a-2p) | 10:00-12:00 | 8.2% | 76% |
| CAISO | Summer | Day | 11:00-13:00 | 18.5% | 89% |

---

### 4.2 Advanced Analysis

#### 07_advanced_analysis.py

**Purpose:** Validate heuristics, test robustness, analyze grid behavior.

**Sections:**

**Section 1: Robustness Analysis**
- Year-over-year stability of best hours
- Threshold vs time-based rule comparison
- Holdout validation (train on 2022-23, test on 2024)

**Section 2: Operational Constraints**
- Duration sensitivity (0.5h to 8h jobs)
- Deadline scheduling (must finish by X pm)
- Shift-constrained windows

**Section 3: Grid Behavior**
- Volatility by hour and region
- Regime clustering (K-means on daily profiles)
- MISO evening dip investigation

**Section 4: Forecast Value**
- Achieved vs theoretical savings using forecasts
- Capture rate distribution

**Outputs:**
- `outputs/07_stability.csv`
- `outputs/07_threshold_vs_time.csv`
- `outputs/07_duration_sensitivity.csv`
- `outputs/07_regime_clusters.csv`
- `outputs/07_summary_report.txt`
- Multiple figures (07_*.png)

---

### 4.3 Extended Analysis (New Modules)

#### 08_grid_stress.py — Extreme Event Analysis

**Core Question:** When are the worst times to run, and can you predict them?

**What It Does:**

1. **Stress Event Identification**
   - Filter top 5% and 10% MOER periods
   - Group consecutive high-MOER hours into "events"
   - Track duration (1-hour spike vs 8-hour sustained)

2. **Temporal Characterization**
   - Monthly distribution of stress events
   - Hour-of-day patterns (when do they start/peak?)
   - Weekday vs weekend frequency
   - Clustering patterns (do events bunch together?)

3. **Trigger Analysis**
   - Seasonal correlation (summer AC, winter heating)
   - Year-over-year trends (getting better/worse?)
   - Weather proxy analysis (if temp data available)

4. **Regional Correlation**
   - When MISO spikes, does PJM spike too?
   - Are there "safe harbor" regions during stress?

5. **Forecast Warning Analysis**
   - For each historical stress event, did forecast predict it?
   - Lead time: how much warning did we get?
   - False positive rate: predicted stress that didn't happen

**Outputs:**
| File | Contents |
|------|----------|
| `08_stress_events.csv` | Catalog of all stress events with start, end, duration, peak MOER |
| `08_stress_calendar.csv` | Monthly/weekly stress frequency by region |
| `08_stress_forecast_warning.csv` | Forecast lead time for each event |
| `08_stress_monthly_heatmap.png` | When stress events happen (month × hour) |
| `08_stress_duration_dist.png` | How long events last |
| `08_stress_regional_corr.png` | Cross-region spike correlation |

**Thesis Application:**
"Avoiding the worst 5% of grid hours provides X% of theoretical maximum savings with minimal scheduling complexity."

---

#### 09_shutdown_planning.py — Strategic Maintenance Windows

**Core Question:** When should facilities schedule planned downtime to maximize avoided emissions?

**What It Does:**

1. **Weekly Rankings**
   - Rank all 52 weeks by average MOER per region
   - Identify consistently "bad" weeks (best for maintenance)
   - Calculate year-over-year consistency

2. **Monthly Rankings**
   - Same analysis at monthly granularity
   - Seasonal patterns: Is August always bad?

3. **Optimal Maintenance Windows**
   - If you have 1 week of downtime, which week?
   - If you have 2 weeks, which 2? (consecutive or spread?)
   - Diminishing returns curve: value of 3rd, 4th week

4. **Holiday/Calendar Overlay**
   - Map typical industrial shutdowns (Christmas, July 4th, Thanksgiving)
   - Are manufacturers accidentally optimizing already?
   - Opportunity cost: "Moving shutdown from Christmas to week X saves Y%"

5. **Production Concentration**
   - Flip side: which weeks are best for heavy production?
   - Optimal 4-week "production sprint" timing

**Outputs:**
| File | Contents |
|------|----------|
| `09_weekly_rankings.csv` | All weeks ranked by MOER, by region |
| `09_monthly_rankings.csv` | All months ranked |
| `09_shutdown_recommendations.csv` | "Best N weeks for maintenance" |
| `09_holiday_analysis.csv` | How holidays align with grid patterns |
| `09_weekly_heatmap.png` | 52-week view across years |
| `09_shutdown_value_curve.png` | Diminishing returns of downtime |

**Thesis Application:**
Strategic facility planning beyond tactical job scheduling. Relevant for maintenance scheduling, capacity planning, capital budgeting.

---

#### 10_forecast_horizon.py — Forecast Reliability Deep Dive

**Core Question:** At what planning horizon can you trust forecasts vs falling back to heuristics?

**What It Does:**

1. **Accuracy by Horizon**
   - Calculate MAE/MAPE at 4h, 8h, 12h, 24h, 48h, 72h
   - Identify accuracy "cliff" (where forecasts become unreliable)
   - Compare absolute error vs decision error

2. **Accuracy by Season**
   - Summer vs winter forecast reliability
   - Hypothesis: stable weather = better forecasts

3. **Accuracy by Time of Day**
   - Morning forecasts for afternoon operations
   - Evening forecasts for overnight/next-morning
   - Peak hour (4-7pm) forecast reliability

4. **Decision Reliability Metrics**
   - P(within 1 hour of actual best)
   - P(achieving ≥80% of theoretical savings)
   - Breakdown by horizon and season

5. **Decision Rules**
   - "Use real-time data if horizon < X hours"
   - "Use day-ahead forecast if horizon 12-24h AND consistency > Y"
   - "Fall back to heuristics if horizon > 48h"

**Outputs:**
| File | Contents |
|------|----------|
| `10_accuracy_by_horizon.csv` | MAE/MAPE at each horizon |
| `10_accuracy_by_season.csv` | Season × horizon cross-tab |
| `10_decision_reliability.csv` | Probability of good decisions |
| `10_recommended_thresholds.csv` | When to use forecast vs heuristic |
| `10_accuracy_degradation.png` | Error vs horizon curve |
| `10_decision_heatmap.png` | Horizon × season reliability matrix |

**Thesis Application:**
Practical implementation guidance for system designers. Defines boundaries of forecast utility.

---

#### 11_threshold_buckets.py — Traffic Light Decision Rules

**Core Question:** Can carbon-aware scheduling be reduced to a simple traffic light system?

**What It Does:**

1. **Define Thresholds by Region**
   - Green: bottom 25% of regional MOER (run freely)
   - Yellow: middle 50% (run if needed)
   - Red: top 25% (defer if possible)
   - Thresholds calibrated per-region (CAISO green ≠ MISO green)

2. **Bucket Distribution Analysis**
   - % of hours in each bucket by region/season/hour
   - "In summer, 40% of morning hours are green vs 10% evening"

3. **Transition Patterns**
   - How long do green windows typically last?
   - Markov-style transition probabilities
   - "If yellow now, P(green in 2 hours) = X%"

4. **Operational Feasibility**
   - If you only run during green, how many hours/day?
   - Is this enough for typical production?
   - Minimum viable flexibility requirements

5. **Savings Quantification**
   - Defer all red → next green: what's the savings?
   - Comparison to full optimization
   - "Traffic light achieves X% of optimal with Y% complexity"

**Outputs:**
| File | Contents |
|------|----------|
| `11_threshold_values.csv` | Green/yellow/red cutoffs by region |
| `11_bucket_distribution.csv` | % hours in each bucket |
| `11_transition_probs.csv` | Bucket-to-bucket transitions |
| `11_green_window_duration.csv` | How long green windows last |
| `11_bucket_heatmap.png` | 24-hour × season bucket view |
| `11_traffic_light_summary.png` | Simple operator visual |

**Thesis Application:**
"Minimum viable implementation" — no API integration needed, just a lookup table. Bridges research to practice.

---

#### 12_multiday_planning.py — Production Week Optimization

**Core Question:** How should weekly production hours be allocated across days and shifts?

**What It Does:**

1. **Weekly Production Scenarios**
   - "I have 40 hours of machining this week"
   - Test workloads: 20h, 30h, 40h, 50h, 60h
   - Compare uniform vs optimized allocation

2. **Day Selection Analysis**
   - If you can choose which days to run, which are best?
   - Monday-Friday vs including weekends
   - 4×10 schedule vs 5×8 schedule comparison

3. **Shift Allocation**
   - Given a day, optimal hour distribution
   - "Run 10 hours Tuesday" — which 10?

4. **Flexibility Value Curve**
   - Marginal value of additional flexibility
   - "Going from 40h to 50h of weekly flexibility saves X% more"
   - Diminishing returns analysis

5. **Constraint Interactions**
   - Minimum daily runtime (equipment warm-up)
   - Jobs that can't be split across days
   - Required maintenance windows

**Outputs:**
| File | Contents |
|------|----------|
| `12_weekly_scenarios.csv` | Optimal allocation per workload |
| `12_day_rankings.csv` | Best days by region/season |
| `12_flexibility_value.csv` | Marginal value of flexibility |
| `12_weekly_allocation.png` | Visual of optimal week |
| `12_flexibility_curve.png` | Savings vs flexibility hours |

**Thesis Application:**
Production planning perspective rather than single-job scheduling. More relevant for facility managers.

---

## 5. Configuration

### config.py Structure

```python
# =============================================================================
# CREDENTIALS
# =============================================================================
WATTTIME_USERNAME = "your_username"
WATTTIME_PASSWORD = "your_password"
WATTTIME_BASE_URL = "https://api.watttime.org/v3"

# =============================================================================
# REGIONS
# =============================================================================
REGIONS = {
    "MISO_INDIANAPOLIS": {
        "name": "MISO Indianapolis",
        "timezone": "America/Indiana/Indianapolis",
        "color": "#1f77b4"
    },
    "CAISO_NORTH": {
        "name": "California ISO North", 
        "timezone": "America/Los_Angeles",
        "color": "#2ca02c"
    },
    # ... more regions
}

# =============================================================================
# TIME RANGE
# =============================================================================
HISTORICAL_START = datetime(2022, 1, 1)
HISTORICAL_END = datetime(2024, 12, 31)

# =============================================================================
# ANALYSIS PARAMETERS
# =============================================================================
# Scheduling
DEFAULT_JOB_DURATION_HOURS = 2.0
SHIFTS = {
    "day": (6, 14),
    "evening": (14, 22),
    "night": (22, 6),
}

# Seasons
SEASONS = {
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "fall": [9, 10, 11],
}

# Grid stress (Module 08)
STRESS_PERCENTILE = 95  # Top 5% = stress event
STRESS_MIN_DURATION_HOURS = 2

# Threshold buckets (Module 11)
THRESHOLD_PERCENTILES = {
    "green": 25,   # Bottom 25%
    "yellow": 75,  # 25-75%
    "red": 100,    # Top 25%
}

# Multi-day planning (Module 12)
WEEKLY_WORKLOADS = [20, 30, 40, 50, 60]

# =============================================================================
# OUTPUT
# =============================================================================
FIGURE_DPI = 150
FIGURE_SIZE = (10, 6)
RUNS_DIR = Path("./runs")
```

---

## 6. Usage Guide

### First-Time Setup

```bash
# 1. Clone/download the project
cd watttime_analysis

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
# Edit config.py with your WattTime username/password

# 5. Test API access
python check_access.py
```

### Running the Full Pipeline

```bash
# Step 1: Collect data (run once, ~20-30 min)
python 01_data_collection.py

# Step 2: Process data (run once, ~2-5 min)
python 02_data_processing.py

# Step 3: Run analyses (any order, re-run as needed)
python 03_temporal_patterns.py
python 04_scheduling_simulation.py
python 05_forecast_accuracy.py
python 06_heuristics.py

# Step 4: Advanced analysis
python 07_advanced_analysis.py

# Step 5: Extended modules (when implemented)
python 08_grid_stress.py
python 09_shutdown_planning.py
python 10_forecast_horizon.py
python 11_threshold_buckets.py
python 12_multiday_planning.py
```

### Re-running Analyses

- **Data changed?** Re-run 01 → 02 → all analysis scripts
- **Parameters changed?** Re-run affected analysis script only
- **New region added?** Re-run 01 (fetches only new) → 02 → all analysis scripts

### Working with Runs

Each execution of `02_data_processing.py` creates a new run folder:

```bash
runs/
├── 2025-01-28_moer_temporal/
├── 2025-02-01_moer_forecast/
└── 2025-02-03_moer_full/
```

Analysis scripts auto-detect the most recent run, or you can specify:

```python
# In script config section:
RUN_FOLDER = "2025-01-28_moer_temporal"  # Specific run
RUN_FOLDER = None  # Auto-detect most recent
```

---

## 7. Output Interpretation

### Key Metrics

| Metric | Good Value | Meaning |
|--------|------------|---------|
| Hourly Spread | >100 lbs/MWh | Significant scheduling opportunity |
| Savings % | >10% | Meaningful emissions reduction |
| Consistency | >70% | Reliable pattern across days |
| Stability Score | >0.7 | Pattern stable across years |
| Capture Rate | >0.8 | Forecast achieves 80%+ of optimal |
| Generalization | >0.8 | Heuristics work on new data |

### Reading the Heuristics Table

```
| Region | Season | Shift | Best Window | Avg Savings | Consistency |
|--------|--------|-------|-------------|-------------|-------------|
| MISO   | Summer | Day   | 10:00-12:00 | 8.2%        | 76%         |
```

- **Best Window:** Start your 2-hour operation at 10am
- **Avg Savings:** Expected 8.2% emissions reduction vs random scheduling
- **Consistency:** 76% of days, this window is within 80% of optimal

### Interpreting Stress Events

```
Stress Event #42:
  Region: MISO_INDIANAPOLIS
  Start: 2024-07-15 16:00
  End: 2024-07-15 22:00
  Duration: 6 hours
  Peak MOER: 1856 lbs/MWh
  Forecast Warning: 18 hours
```

- 6-hour event = sustained, not a spike
- Peak 1856 vs mean ~1377 = 35% above normal
- 18-hour warning = day-ahead forecast caught it

### Regional Comparisons

| Region | Mean MOER | Spread | Best For |
|--------|-----------|--------|----------|
| CAISO | 849 | 311 (37%) | Scheduling optimization |
| MISO | 1377 | 71 (5%) | Baseline operations |
| ERCOT | 1134 | 48 (4%) | Minimal scheduling value |

CAISO's high spread means scheduling matters most there. MISO/ERCOT are flatter — focus on other efficiency measures.

---

## 8. Research Applications

### Thesis Integration

| Chapter | Relevant Modules | Key Outputs |
|---------|------------------|-------------|
| Literature Review | — | Establish MOER vs average distinction |
| Methodology | 01, 02, config | Data collection approach |
| Results: Patterns | 03 | Temporal profiles, seasonal variation |
| Results: Savings | 04, 06 | Scheduling simulation, heuristics |
| Results: Forecasting | 05, 10 | Forecast accuracy, horizon analysis |
| Discussion | 07, 08, 09 | Robustness, stress events, planning |
| Implementation | 11, 12 | Traffic light rules, weekly planning |

### Paper Figures

**Priority 1 (Core Findings):**
1. `03_hourly_all_regions.png` — Regional MOER profiles
2. `04_savings_distribution.png` — Achievable savings
3. `06_heuristics_summary.png` — Actionable recommendations

**Priority 2 (Supporting Evidence):**
4. `07_stability_heatmap.png` — Year-over-year consistency
5. `08_stress_monthly_heatmap.png` — When to avoid operations
6. `10_accuracy_degradation.png` — Forecast reliability

**Priority 3 (Extended Analysis):**
7. `09_shutdown_value_curve.png` — Strategic planning
8. `11_traffic_light_summary.png` — Operator decision aid
9. `12_flexibility_curve.png` — Value of flexibility

### Key Research Contributions

1. **Marginal vs Average:** Demonstrate that marginal emissions (MOER) differ significantly from average grid factors
2. **Scheduling Value:** Quantify achievable emissions reduction through time-shifting
3. **Regional Variation:** Show that location determines scheduling opportunity
4. **Practical Heuristics:** Provide simple rules that achieve most of optimal
5. **Forecast Utility:** Define when forecasts add value vs heuristics sufficient
6. **Strategic Planning:** Extend beyond job scheduling to facility planning

---

## Appendix A: Troubleshooting

### Common Issues

**API rate limits:**
```
ERROR: 429 Too Many Requests
```
Solution: Add sleep between requests, check rate limit (3000/5min)

**Missing regions:**
```
Region DE: 403 Forbidden
```
Solution: Region not in your subscription tier, remove from config

**Timezone errors:**
```
AttributeError: Can only use .dt accessor with datetimelike values
```
Solution: Ensure timezone conversion completed, check data processing script

**Unicode errors (Windows):**
```
UnicodeEncodeError: 'charmap' codec can't encode character
```
Solution: Add `encoding="utf-8"` to file write operations

### Data Quality Checks

```python
# Check for gaps
df.groupby("date").size().describe()

# Check for outliers
df[df["value"] > df["value"].quantile(0.999)]

# Verify timezone conversion
df[["point_time_utc", "point_time", "hour"]].head(20)
```

---

## Appendix B: API Reference

### WattTime Endpoints Used

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `/v3/login` | Get auth token | — |
| `/v3/historical` | Past MOER data | 32 days/request |
| `/v3/forecast` | Future predictions | 72 hours |
| `/v3/signal-index` | Real-time MOER | 1 request/5min |

### Research Tier Features

- Full MOER values (lbs CO₂/MWh), not just 0-100 index
- 2+ years historical data
- 5-minute resolution
- Multiple regions
- Forecast history access

---

*Document maintained alongside codebase. Update as modules are added or modified.*
