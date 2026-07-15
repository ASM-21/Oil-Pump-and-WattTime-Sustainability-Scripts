# A2 (stdlib check): FDM utilization from measured prints

Independent, pandas-free recomputation of u_FDM from the real
print CSVs in `3D Printer Data/`, run because
`A2_fdm_utilization.py` (same folder) cannot execute in an
environment where pandas is unavailable. Integration rule
mirrors `adapters.load_am_energy()` exactly (dt from consecutive
timestamps, first sample dropped, energy = sum(P * dt)), so the
two should agree once someone runs the canonical script locally
and cross-checks. **Not a replacement for the canonical result --**
cross-check both before quoting u_FDM in the paper.

Files found: 43. Used: 39.
Excluded (annotated/failed captures, by filename): 4
-- ['DriveGear_Part1 cold start_broken sensor.csv', 'DriveGear_Part28 failed.csv', 'DriveShaft_Part1 Broken sensor.csv', 'IdleShaft_Part19 failed.csv']

## Measured

Duration-weighted mean power across 39 valid prints: **186.8 W**

u_FDM = 186.8 / 221 W (rated) = **0.845**

Quoted expectations (GROUND_TRUTH.md): measured draw ~200 W, u ~0.90.
This measurement: -6.6% vs quoted power, -6.1% vs quoted u.

## Per part

| Part | N prints | Mean power (W) | Total energy (Wh) |
|---|---|---|---|
| DriveGear | 9 | 179.2 | 1823.7 |
| DriveShaft | 10 | 180.5 | 929.2 |
| IdleGear | 10 | 194.8 | 2192.1 |
| IdleShaft | 10 | 174.0 | 551.7 |

## Confirms the utilization-landscape headline

u_FDM measured at 0.85 against u_CNC measured at 0.0975
(register-based, `EXPLORATORY/compare_outputs/compare_estimation_ladder.csv`):
a ~9x spread between the two machine classes, both now
from real measurement rather than one spec-sheet number and one
measured number. This is the paper's central utilization-factor
contrast (TRIAGE_code_vs_argument.md's "key direction 1"), now fully
measured on both ends pending the pandas cross-check above.

