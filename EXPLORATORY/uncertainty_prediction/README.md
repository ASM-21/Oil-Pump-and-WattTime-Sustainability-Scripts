# uncertainty_prediction

The interval reviewers will ask for, plus the design-stage model that makes
this a JMD-relevant contribution.

1. **Footprint uncertainty** - per-operation replicate statistics propagated
   into 95% intervals on manufacturing energy (Monte Carlo, cross-checked
   against the exact delta method via `shared/montecarlo.py`), then combined
   with `bom.csv` masses under the same aluminum-carbon scenarios as
   `explorations/B1_breakeven.py` into footprint and manufacturing-share
   intervals per scenario.
2. **Design-stage prediction** - duration-by-category regression predicting
   program energy from CAM-planned times, leave-one-program-out. Ties the
   measurement campaign to the NX feature-library prototype: if per-category
   power is stable, footprints are estimable at CAM time.

## Run

    python EXPLORATORY/uncertainty_prediction/run.py

Always produces the fixture-verified set (tag `fixture`); adds `measured`
tables when `CNC_DATA_DIR` points at the real Al6061 folder.

## Outputs

- `outputs/footprint_intervals_<tag>.csv`
- `outputs/mfg_share_intervals_<tag>.(png|pdf)` - interval fan per scenario
- `outputs/design_stage_loo_<tag>.csv`
- `outputs/design_stage_scatter_<tag>.(png|pdf)` - predicted vs measured
- `FINDINGS.md` - regenerated each run

## Stated assumptions to keep visible in the paper

- Mass sd = 5 g weighing repeatability (MASS_SD_G; adjust to the scale's spec).
- Grid CI fixed at 0.40 kgCO2e/kWh here; the grid axis is swept in B1.
- Intervals use the SE of operation means ("average part"); single-part
  prediction intervals need use_se=False.

## How to extend

- Report per-category prediction errors to show which categories carry the
  design-stage model.
- Replace normal sampling with bootstrap-from-replicates for the operations
  the Shapiro-Wilk screen flags as non-normal.
