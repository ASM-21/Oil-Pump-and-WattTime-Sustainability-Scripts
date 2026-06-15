# allocation

**Question:** How badly do standard LCA allocation rules (mass, time, economic) misassign energy compared to measured per-part ground truth?

**Status:** ready to run (set CNC_DATA_DIR first; mass-based rule needs bom.csv)

## Plan

Uses the body/lid measured energy pair as ground truth to falsify each allocation
rule directly. For each rule, computes the fraction of total CNC energy it would
assign to each part, then measures the signed % error vs what was actually measured.
Sweeps a synthetic production mix (body:lid ratio from 1:5 to 5:1) to show how
error varies across production scenarios. Quantifies the homing (non-productive
repositioning) share and shows how each rule handles it.

All data comes from `shared/adapters.load_operation_energy()`. Mass data for the
mass-based rule comes from `shared/adapters.load_bom()` or the hardcoded context
doc estimates; see README for how to supply verified masses.

## How to run

```
export CNC_DATA_DIR=/path/to/your/Al6061_csv_folder
python EXPLORATORY/allocation/run.py
```

For the mass-based rule, also create `EXPLORATORY/bom.csv`:
```
part,stock_mass_g,finished_mass_g,mass_removed_g
body,2500.0,1063.0,1437.0
lid,610.0,162.0,448.0
```

## Effort box

**First real result:** error table per rule per part (body, lid) and the mix-sweep
figure showing worst-case error as body:lid production ratio varies.

## Key parameters to verify

1. `MASS_BASIS`: choose "removed", "finished", or "stock" and use it consistently.
   Old drafts mixed bases (72% vs 84% lighter); pick one.
2. Verify mass values against lab records; create EXPLORATORY/bom.csv with confirmed numbers.
