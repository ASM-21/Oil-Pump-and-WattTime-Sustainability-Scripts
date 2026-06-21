# estimation_ladder

**Question:** How wrong are simplified energy estimates vs operation-level measured ground truth, and by how much does the error depend on machine class?

**Status:** ready to run (set CNC_DATA_DIR first)

## Plan

Compares five estimation approaches (L0 rated power, L1 avg power, L2 SEC*mass,
L3 program total, L4 UUID ground truth) against measured operation energy for
body and lid CNC programs. Computes utilization factors (u = mean/rated) for
CNC and FDM. Generates the replication table n=(1.96*CV/r)^2 per operation category.

All data comes from the existing CNC CSV files via `shared/adapters.load_operation_energy()`.
The only external inputs are the CNC nameplate rating (13.4 kW spindle, parameterized)
and the Kara & Li (2011) SEC value for aluminum milling.

## How to run

```
# Set environment variable first
export CNC_DATA_DIR=/path/to/your/Al6061_csv_folder

# Run from repo root
python EXPLORATORY/estimation_ladder/run.py
```

Outputs land in `outputs/`. Findings in `FINDINGS.md`.

## Effort box

**First real result:** signed % error per estimation level, per part (body/lid),
in a table -- plus the CNC utilization factor u verified against the quoted ~0.10.

Stop when the error table is computed, verified, and written to FINDINGS.md.
Do not add a second analysis. Record next steps in FINDINGS under "How to extend."

## Dependencies beyond the repo's existing stack

- matplotlib (already in requirements.txt)
- numpy (already in requirements.txt)

No additional packages needed.

## Key parameters to verify before citing numbers

1. `CNC_RATED_POWER_W` (currently 13,400 W spindle rating): update to total connected
   load if you photograph the Hurco electrical plate.
2. `MASS_REMOVED_G` (body 1437 g, lid 448 g): verify against stock/finished mass records
   and set `MASS_DATA_VERIFIED = True` once confirmed.
3. `SEC_KARA_LI_KWH_PER_KG` (2.5 kWh/kg): report which value you use and cite the paper.
