# EXPLORATORY summary

**Status as of 2026-07-09:** infrastructure and theory build complete
(authored in a cloud session where the scientific stack could not be
installed, so everything pandas-based is verified by construction and
fixture design but MUST be executed locally once; the stdlib-only checks
below were executed and pass). Measurement CSVs are still not in the repo;
`bom.csv` now is.

Run order on a machine with the data:

    pip install -r requirements.txt statsmodels
    python EXPLORATORY/theory/selftest_stdlib.py     # passes anywhere (verified)
    python EXPLORATORY/shared/fixtures.py            # passes anywhere (verified)
    python EXPLORATORY/shared/test_shared.py         # first pandas-based gate
    python EXPLORATORY/smoke_fixture_all.py          # ALL nine projects on fixtures
    export CNC_DATA_DIR=/path/to/Al6061_csvs
    export AM_DATA_DIR=/path/to/FDM_csvs             # optional: u_FDM from data
    python EXPLORATORY/run_all.py
    python EXPLORATORY/explorations/A2_fdm_utilization.py

Hardening pass (2026-07-09, second commit): fixed three latent `duration_s > 0`
asserts that would have failed on the analyzer's zero-duration
TRANSITION_OVERHEAD rows (adapter gate, example project, estimation_ladder);
removed the undeclared `tabulate` dependency from FINDINGS writers; made
fixture idle gaps detector-compatible; added `smoke_fixture_all.py` (executes
the Tier-A flagships end to end on fixtures for the first time, with
FIXTURE_SMOKE=1 downgrading quoted-number checks that synthetic data cannot
meet); wired the AM/FDM loader + fixtures + A2 utilization exploration; added
open-set rejection to signature_mining; estimation_ladder and allocation now
read masses from bom.csv.

---

## [verify] placeholders from GROUND_TRUTH.md

These are the numbers that must come from the data, not from the paper:

| Quantity | Quoted | Computed | Source |
|---|---|---|---|
| Fleet average operating power (CNC) | ~1,376 W | TODO (estimation_ladder) | regression slope |
| Homing share of CNC energy | ~11.7% | TODO (allocation or energy_budget) | TRANSITION_OVERHEAD / total |
| Lid / body energy ratio | 67.7% | TODO (allocation or allocation_theory) | measured per-part means |
| Operations passing Shapiro-Wilk | 40 of 45 | TODO (wear_runorder or separate) | normality test |
| Distinct tracked operations | 45 vs 49 | TODO (test_adapters gate) | operation_id.nunique() |
| Replicate runs per program | 16 to 27 | TODO (test_adapters gate) | run_id.nunique() per program |
| MTConnect downtime exclusion | ~20% | TODO (manual check) | clean_data() log |

Resolved this session (no measurement data needed):

| Quantity | Old value | Verified value | Source |
|---|---|---|---|
| Body stock / finished / removed mass | 2500 / 1063 / 1437 g (estimates) | 1880 / 443 / 1437 g | owner, bom.csv |
| Lid stock / finished / removed mass | 610 / 162 / 448 g (estimates) | 518 / 70 / 448 g | owner, bom.csv |
| Mfg share at recycled Al (Indiana grid) | ~29% (old masses) | 35.1% | B1 recompute (stdlib check) |
| CF_al where mfg crosses 5% | 3.96 (old masses) | 5.14 kg CO2e/kg | B1 recompute (stdlib check) |
| Allocation error at 1:1 mix, mass-removed rule | n/a | +27.8% body (at quoted rho_E 0.677) | allocation closed form (stdlib check) |
| Allocation error at 1:1 mix, economic rule | n/a | +44.8% body (same basis) | allocation closed form (stdlib check) |

## Project status

| Project | Status | Key finding / blocker |
|---|---|---|
| theory/estimator_errors | built, closed forms validated (stdlib) | L0 bias = 1/u - 1; regime map; run locally for figures |
| theory/allocation_theory | built, closed forms validated (stdlib) | error surface; needs data only for measured rho_E |
| theory/power_decomposition | built, identity validated (stdlib) | explains the stable average-power constant; run locally |
| signature_mining | built, fixture-first | needs local run; real data for measured tables |
| energy_budget | built, fixture-first | needs local run; real data for measured tables |
| uncertainty_prediction | built, fixture-first | needs local run; real data for measured tables |
| explorations/B1_breakeven | updated with verified masses | headline numbers recomputed (see B1_breakeven.md); run locally for figures |
| estimation_ladder | parked | needs CNC_DATA_DIR |
| allocation | parked | needs CNC_DATA_DIR |
| wear_runorder | parked | needs CNC_DATA_DIR (+ scipy, statsmodels) |

## Discrepancies found vs quoted numbers

- Old stock-mass estimates (2500 g body, 610 g lid) were high by 25 to 33
  percent vs the owner-verified BOM. Every derived number that used them
  (B1 scenario shares, break-even thresholds) moved in the direction of
  MORE manufacturing relevance; nothing weakened.
- No other quoted numbers could be checked without the measurement CSVs;
  the checks are wired (`check_against_expected` calls in each project) and
  fire automatically once data is present.
