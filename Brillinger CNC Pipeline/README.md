# Brillinger CNC Pipeline

An operation-level energy analysis pipeline for the Brillinger et al. (2025)
CNC Machining Data Repository (Mendeley Data V2, DOI
10.17632/gtvvwmz7r7.2; data descriptor in *Data in Brief* 61, 111814). It
parses the dataset's Sinumerik NC programs and per-axis power logs, aligns
them into operation-level energy, and layers on material-removal simulation,
structural/geometry features, anomaly detection, and reporting.

## Current status: **unverified against real data**

This suite was built from the dataset's published descriptor and an
integration plan, not from an actual downloaded file. Nothing here should be
cited until you:

1. Download at least one real `.json` power log + `.mpf` NC program from the
   Mendeley repository.
2. Run `python brillinger_pipeline.py inspect <file.json>` (or
   `explore_dataset.py ... --inspect-only`) and reconcile the printed schema
   against `config.BRILLINGER.channel_power_keys` and `counter_key`.
3. Confirm which NC key the power log's counter actually indexes
   (`n_number` vs `line_number` vs `block_index`) — this is the single
   most error-prone link in the whole pipeline (see `ARCHITECTURE.md`).

Everything downstream (energy-by-operation, SEC, the Brillinger-vs-IN-MaC
comparison) inherits that boundary/channel-map uncertainty until step 2-3 are
done on a real file.

## Why this is here

This repo already has real machine energy data (`Machine Specific Scripts/`,
`Al6061Body/`, `Al6061Lid/`, `3D Printer Data/`) collected from your own
Hurco VMX30Ui (IN-MaC) runs. The Brillinger dataset is an **external, open**
CNC energy dataset (different machine, different measurement boundary — see
below) that can serve as an independent cross-check or a second data source
for the sustainability-scheduling work, once the schema is verified.

## Quick start

```bash
cd "Brillinger CNC Pipeline"
pip install -r ../requirements.txt   # pandas, numpy, matplotlib already covered
pip install ijson trimesh            # optional: streaming JSON inspect, STL volume

# 1. inspect one real file before trusting anything
python explore_dataset.py /path/to/brillinger_dataset --inspect-only

# 2. after fixing config.py's channel map/counter key if needed, full run
python explore_dataset.py /path/to/brillinger_dataset --out ./exploration
```

See `ARCHITECTURE.md` for the module-by-module layout, the
source-agnostic `OperationStore` spine, and how to plug your own IN-MaC UUID
results in for a cross-dataset comparison.

## The measurement-boundary caveat (read before comparing to your data)

Brillinger's power log is a **sum of per-axis drive channels** (spindle +
linear/rotary drives). It excludes control electronics, cooling, and
lighting. Your IN-MaC IAMMETER reads **true total machine input**. These are
not the same boundary, and `comparison.py` / `operations.compare()` refuse to
compare them on a raw "total" basis for exactly this reason — see the module
docstrings for the marginal-energy approach and its residual limits.

## Tests

```bash
python test_anomalies_report.py   # anomaly detection + HTML report, synthetic fixtures
python test_features.py           # NC/geometry feature extraction, known-answer checks
```

Both build small synthetic MPF/JSON/STL fixtures on the fly (no real dataset
required) and print a pass/fail summary. `test_features.py` needs `trimesh`.

## Safety and cleanup notes

- No credentials or absolute local paths are hardcoded here.
- The dataset itself is not committed; point `explore_dataset.py` at a local
  download path.
- Cache directories (`--cache`) and generated `exploration/` output are
  local artifacts; do not commit large corpus runs.
