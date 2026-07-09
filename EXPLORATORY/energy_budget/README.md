# energy_budget

Generalizes the paper's single non-productive number (homing at ~11.7%) into
a complete, auditable energy budget:

1. **Category budget** - every operation category's share of part energy,
   split productive vs non-productive (idle, homing), per part and pooled.
2. **Closure** - bottom-up attributed energy reconciled against an
   independent integration of the full raw power stream, per
   (part, run, program). The residual is what attribution silently loses;
   the smoke test fails if it exceeds 5%.

## Run

    python EXPLORATORY/energy_budget/run.py

Always produces the fixture-verified result set (tag `fixture`); adds
`measured` tables when `CNC_DATA_DIR` points at the real Al6061 folder, and
then checks the measured homing share against the quoted 11.7%.

## Outputs

- `outputs/category_budget_<tag>.csv`, `closure_<tag>.csv`
- `outputs/category_budget_<tag>.(png|pdf)` - stacked share bars, hatched
  non-productive; the Results exhibit
- `FINDINGS.md` - regenerated each run

## How to extend

- Add a per-program budget figure if reviewers ask where roughing vs
  finishing dominates.
- Fold in the FDM stream once AM loading is wired, for a machine-class
  comparison of non-productive shares.
