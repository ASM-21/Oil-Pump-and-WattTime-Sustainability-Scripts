# WattTime Heuristic Tool — Quick Reference

## Module Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  01_data_collection     │  WattTime API → raw parquet       │  Run once     │
│  02_data_processing     │  Feature engineering, timezones   │  Run once     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CORE ANALYSIS                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  03_temporal_patterns   │  Hourly/seasonal/YoY profiles     │  Patterns     │
│  04_scheduling_sim      │  Job optimization, savings calc   │  Savings      │
│  05_forecast_accuracy   │  Forecast vs actual comparison    │  Forecasts    │
│  06_heuristics          │  Synthesize into actionable rules │  Rules        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ADVANCED ANALYSIS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  07_advanced_analysis   │  Robustness, constraints, regimes │  Validation   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EXTENDED ANALYSIS (NEW)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  08_grid_stress         │  Extreme events, warnings         │  Avoidance    │
│  09_shutdown_planning   │  Maintenance windows, calendar    │  Strategic    │
│  10_forecast_horizon    │  Reliability by horizon/season    │  Guidance     │
│  11_threshold_buckets   │  Traffic light rules              │  Operators    │
│  12_multiday_planning   │  Weekly production optimization   │  Scheduling   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Details

| # | Module | Core Question | Time Scale | Primary User |
|---|--------|---------------|------------|--------------|
| 01 | data_collection | — | — | Setup |
| 02 | data_processing | — | — | Setup |
| 03 | temporal_patterns | When is the grid cleanest? | Hours | Analyst |
| 04 | scheduling_sim | How much can we save? | Hours | Analyst |
| 05 | forecast_accuracy | Can we trust forecasts? | Hours-Days | Analyst |
| 06 | heuristics | What rules should we follow? | Hours | Operator |
| 07 | advanced_analysis | Are the rules robust? | Hours-Years | Analyst |
| 08 | grid_stress | When should we NOT run? | Hours-Days | Operator |
| 09 | shutdown_planning | When should we schedule downtime? | Weeks-Months | Plant Manager |
| 10 | forecast_horizon | When to use forecast vs heuristic? | Hours-Days | System Designer |
| 11 | threshold_buckets | Can we use a traffic light system? | Real-time | Operator |
| 12 | multiday_planning | How to allocate weekly production? | Days-Week | Scheduler |

---

## Key Outputs by Module

### Core Pipeline

| Module | Key CSV | Key Figure | Key Metric |
|--------|---------|------------|------------|
| 03 | `temporal_pattern_summary.csv` | `03_hourly_all_regions.png` | Hourly spread (lbs/MWh) |
| 04 | `scheduling_results.csv` | `04_savings_distribution.png` | Savings % |
| 05 | `forecast_accuracy.csv` | `05_forecast_error_by_horizon.png` | MAE, MAPE |
| 06 | `heuristics_table.csv` | `06_heuristics_summary.png` | Best window, consistency |

### Advanced + Extended

| Module | Key CSV | Key Figure | Key Metric |
|--------|---------|------------|------------|
| 07 | `07_stability.csv` | `07_stability_heatmap.png` | Stability score |
| 08 | `08_stress_events.csv` | `08_stress_monthly_heatmap.png` | Event frequency, duration |
| 09 | `09_weekly_rankings.csv` | `09_shutdown_value_curve.png` | Best maintenance weeks |
| 10 | `10_accuracy_by_horizon.csv` | `10_accuracy_degradation.png` | Horizon threshold |
| 11 | `11_threshold_values.csv` | `11_traffic_light_summary.png` | Green/yellow/red cutoffs |
| 12 | `12_weekly_scenarios.csv` | `12_flexibility_curve.png` | Flexibility value |

---

## Data Dependencies

```
                        01_data_collection
                              │
                              ▼
                        02_data_processing
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
         data_5min       data_hourly    daily_stats
              │               │               │
              │      ┌────────┴────────┐      │
              │      │                 │      │
              ▼      ▼                 ▼      ▼
           ┌────┐ ┌────┐            ┌────┐ ┌────┐
           │ 04 │ │ 03 │            │ 05 │ │ 07 │
           └──┬─┘ └──┬─┘            └──┬─┘ └──┬─┘
              │      │                 │      │
              └──────┼─────────────────┘      │
                     │                        │
                     ▼                        │
                  ┌────┐                      │
                  │ 06 │◄─────────────────────┘
                  └──┬─┘
                     │
     ┌───────┬───────┼───────┬───────┐
     │       │       │       │       │
     ▼       ▼       ▼       ▼       ▼
  ┌────┐ ┌────┐  ┌────┐  ┌────┐  ┌────┐
  │ 08 │ │ 09 │  │ 10 │  │ 11 │  │ 12 │
  └────┘ └────┘  └────┘  └────┘  └────┘
```

---

## Run Order

### Full Pipeline (First Time)
```bash
python 01_data_collection.py    # ~20-30 min
python 02_data_processing.py    # ~2-5 min
python 03_temporal_patterns.py  # ~1 min
python 04_scheduling_simulation.py  # ~5-10 min
python 05_forecast_accuracy.py  # ~2 min
python 06_heuristics.py         # ~1 min
python 07_advanced_analysis.py  # ~5 min
python 08_grid_stress.py        # ~2 min
python 09_shutdown_planning.py  # ~2 min
python 10_forecast_horizon.py   # ~3 min
python 11_threshold_buckets.py  # ~2 min
python 12_multiday_planning.py  # ~5 min
```

### Re-run Analysis Only
```bash
# If only changing analysis parameters (not data):
python 03_temporal_patterns.py
# ... other analysis scripts as needed
```

### Add New Region
```bash
# 1. Add region to config.py
# 2. Re-run:
python 01_data_collection.py    # Fetches only new region
python 02_data_processing.py    # Rebuilds combined dataset
# 3. Re-run all analysis scripts
```

---

## Config Quick Reference

```python
# Key parameters to customize:

# Regions (add/remove as needed)
REGIONS = {
    "MISO_INDIANAPOLIS": {...},
    "CAISO_NORTH": {...},
    # Add more here
}

# Date range
HISTORICAL_START = datetime(2022, 1, 1)
HISTORICAL_END = datetime(2024, 12, 31)

# Job scheduling
DEFAULT_JOB_DURATION_HOURS = 2.0

# Stress events (Module 08)
STRESS_PERCENTILE = 95  # Top 5%

# Thresholds (Module 11)
THRESHOLD_PERCENTILES = {"green": 25, "yellow": 75, "red": 100}

# Weekly planning (Module 12)
WEEKLY_WORKLOADS = [20, 30, 40, 50, 60]
```

---

## Thesis Chapter Mapping

| Chapter | Primary Modules | Key Deliverables |
|---------|-----------------|------------------|
| Methodology | 01, 02 | Data collection approach |
| Results: Temporal | 03, 07 (stability) | Hourly profiles, YoY consistency |
| Results: Savings | 04, 06 | Simulation results, heuristics table |
| Results: Forecasting | 05, 10 | Accuracy metrics, horizon guidance |
| Discussion: Robustness | 07 | Holdout validation, constraints |
| Discussion: Strategic | 08, 09 | Stress events, shutdown planning |
| Implementation | 11, 12 | Traffic light rules, weekly planning |

---

## Troubleshooting Checklist

- [ ] WattTime credentials in config.py?
- [ ] `pip install -r requirements.txt` completed?
- [ ] Run 01 before 02, run 02 before 03-12?
- [ ] Check `runs/` for output location?
- [ ] Windows? Add `encoding="utf-8"` to file writes
- [ ] API 429 error? Add sleep, check rate limits
- [ ] Region 403 error? Not in your subscription tier
