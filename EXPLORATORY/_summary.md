# EXPLORATORY summary

**Status:** not yet computed -- run `python EXPLORATORY/run_all.py` to generate results.

This file is a placeholder. After running the projects, fill it in with:
- Which directions had substance (ranked)
- Computed numbers resolving the GROUND_TRUTH.md [verify] placeholders
- Every discrepancy vs quoted numbers, stated bluntly
- One-line status per project: explored / promising / null / parked

---

## [verify] placeholders from GROUND_TRUTH.md

These are the numbers that must come from the data, not from the paper:

| Quantity | Quoted | Computed | Source |
|---|---|---|---|
| Fleet average operating power (CNC) | ~1,376 W | TODO (estimation_ladder) | regression slope |
| Homing share of CNC energy | ~11.7% | TODO (allocation) | TRANSITION_OVERHEAD / total |
| Lid / body energy ratio | 67.7% | TODO (allocation) | measured per-part means |
| Operations passing Shapiro-Wilk | 40 of 45 | TODO (wear_runorder or separate) | normality test |
| Distinct tracked operations | 45 vs 49 | TODO (test_adapters gate) | operation_id.nunique() |
| Replicate runs per program | 16 to 27 | TODO (test_adapters gate) | run_id.nunique() per program |
| MTConnect downtime exclusion | ~20% | TODO (manual check) | clean_data() log |

---

## Project status (fill in after running)

| Project | Status | Key finding |
|---|---|---|
| estimation_ladder | TODO | |
| allocation | TODO | |
| wear_runorder | TODO | |
