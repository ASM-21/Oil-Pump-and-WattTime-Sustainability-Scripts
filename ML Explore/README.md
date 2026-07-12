# Operation-level sensor ML toolkit

Splits long-format CNC monitoring CSVs into per-(program, operation) tables and runs a
full suite of analyses on them, keeping every sensor channel (not just energy). Fifteen
scripts: one prep step, a shared feature library, eleven standalone analyses, a report
builder, and a one-command runner.

## Quick start

```
pip install -r requirements.txt

# FIRST on new data: inspect the schema without writing anything
python split_operations.py --input ./data --dry-run

# Everything at once: split raw files, run all analyses, build the HTML report
python run_all.py --data ./data --names operation_names.json --material-carbon 12.5

# open ml/report.html
```

The dry run reports, per file, the detected sample count, channel count, pivot
method, operation count, and whether the filename parsed. If filenames do not parse,
set `--part-types` to your part keywords (e.g. `--part-types body,lid,bracket`).

`run_all.py` produces `ml/report.html`, a single self-contained page with every
script's key tables and plots. A failing step is reported and skipped; the rest run.

## Manual workflow

One prep script makes the CSV folder; every analysis is standalone and just points at
that folder. Keep all `.py` files together (the analyses import `features.py`).

```
# 1. PREP (only data step)
python split_operations.py --input ./data --output ./operation_csvs --names operation_names.json

# 2. QUALITY (run first; sets thresholds for the rest)
python quality_check.py --input ./operation_csvs

# 3. ANALYSES (standalone, run any subset)
python classify_operations.py    --input ./operation_csvs   # operation ID + sensor ablation
python estimate_energy.py        --input ./operation_csvs   # per-operation energy regression
python variability_analysis.py   --input ./operation_csvs   # reproducibility + variance + drift
python energy_breakdown.py       --input ./operation_csvs   # energy attribution + Pareto
python sensor_study.py           --input ./operation_csvs   # sensor importance + minimal set
python carbon_scheduling.py      --input ./operation_csvs   # carbon-aware scheduling sim
python time_series_analysis.py   --input ./operation_csvs   # signatures + early prediction
python wear_analysis.py          --input ./operation_csvs   # trends + changepoints + RUL
python cluster_operations.py     --input ./operation_csvs   # unsupervised structure + sub-modes
python carbon_footprint.py       --input ./operation_csvs   # carbon + material-vs-mfg split

# 4. REPORT (assemble everything)
python generate_report.py --input ./ml --output ./ml/report.html
```

## Scripts

- **split_operations.py** (prep) - long->wide pivot, one CSV per (program, operation) with
  runs combined; identity columns preserve run/pass separation. Wipes stale output on re-run.
- **features.py** (library) - per-pass channel summaries (mean/std/min/max/range/median/
  slope/auc), sensor groups, energy targets; also serves sample (1 Hz) granularity.
- **quality_check.py** - sparse/short operations, imbalance, dead channels, IsolationForest
  outliers. Run first.
- **classify_operations.py** - per-operation F1 by algorithm + sensor-group ablation.
- **estimate_energy.py** - per-operation energy regression; best model and drivers per op.
- **variability_analysis.py** - reproducibility (CV), variance explained (eta^2 + tests),
  within-program drift.
- **energy_breakdown.py** - energy attribution per program/operation, Pareto, specific energy.
- **sensor_study.py** - mutual information, redundancy, greedy minimal sensor set.
- **carbon_scheduling.py** - place a job on a grid carbon curve; run-now/overnight/threshold/
  optimal; synthetic or real MOER via --carbon-csv.
- **time_series_analysis.py** - power signatures, phase segmentation, early prediction curves.
- **wear_analysis.py** - Mann-Kendall trends, CUSUM changepoints, control limits, RUL proxy.
- **cluster_operations.py** - PCA + KMeans, ARI/NMI vs operations, sub-mode discovery.
- **carbon_footprint.py** - operational carbon, per-part carbon passport, material-vs-mfg split.
- **generate_report.py** - assembles all outputs into one self-contained HTML report.
- **run_all.py** - runs the whole pipeline and the report with one command.

## Methodology notes

- Model cross-validation is **grouped by run** (`source_file`); whole runs are held out, so
  scores reflect generalization, not run memorization.
- **Short/sparse operations**: run quality_check first, then `--min-samples N` and read
  per-operation (not pooled) metrics.
- **Energy regression** excludes the energy sensor group (anti-circularity); early-prediction
  energy keeps power (forecasting).
- **Drift/wear/variability** are computed within a program (run numbers reset per program).
- **Scheduling** treats a program as one shiftable job; savings are grid-dependent and naive
  overnight rules can backfire on solar grids.
- **Carbon footprint** material-vs-mfg split depends on the real energy magnitude and the
  emission/material factors you supply.

## Useful flags

- `run_all.py --skip a,b` skip steps; `--report-only` rebuild report; `--material-carbon K`;
  `--min-samples N`; `--keep-idle`.
- `--target {auto,kwh_meter,wh_integral}` energy target (energy/breakdown/scheduling).
- `--carbon-csv/--time-col/--value-col/--value-unit` real MOER data (scheduling).
- `--emission-factor`, `--material-carbon`, `--material-csv` (carbon_footprint).
- `split_operations.py --dry-run` inspect schema/operations without writing;
  `--part-types body,lid,...` set filename part keywords; `--pivot {auto,time,blocks}`
  choose sample detection (auto validates the fast time-based method and falls back).
- `--granularity sample` (features) row-level instead of per-pass.
