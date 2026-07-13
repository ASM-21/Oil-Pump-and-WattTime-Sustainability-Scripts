# EXPLORATORY summary

**Status as of 2026-07-11:** the measurement data is committed to the repo
(`Al6061Body/`, `Al6061Lid/`, `3D Printer Data/`) and merged into this branch.
The adapters now default to those in-repo folders, so every project runs with
NO environment variables. The register-based analyzer the owner added on
`main` (energy from the cumulative forward-kWh meter, exact and gap-immune) is
in place; the fixture generator emits that register too, so fixture validation
still exercises the real pipeline. Pandas code still could not be executed in
THIS session (PyPI blocked), so the measured numbers below are read from the
owner's committed `EXPLORATORY/compare_outputs/` run; stdlib checks here pass.

Run order (no env vars needed now):

    pip install -r requirements.txt statsmodels
    python EXPLORATORY/theory/selftest_stdlib.py     # passes anywhere (verified)
    python EXPLORATORY/shared/fixtures.py            # passes anywhere (verified)
    python EXPLORATORY/shared/test_shared.py         # first pandas-based gate
    python EXPLORATORY/smoke_fixture_all.py          # ALL nine projects on fixtures
    python EXPLORATORY/run_all.py                    # real pass, in-repo data
    python EXPLORATORY/explorations/A2_fdm_utilization.py

---

## [verify] placeholders from GROUND_TRUTH.md -- RESOLVED FROM DATA

Measured values are register-based, from `EXPLORATORY/compare_outputs/`
(the owner's committed run). Two quoted numbers FAIL verification and are
findings for the paper, not typos to hide.

| Quantity | Quoted | Measured | Verdict |
|---|---|---|---|
| Fleet average operating power (CNC) | ~1,376 W | 1,306 W (register) / 1,333 W (active) | 3 to 5% high; report measured |
| CNC utilization u = mean/rated | ~0.10 | 0.0975 | CONFIRMED |
| L0 (rated-power) error | large + | +962% | CONFIRMED (theory: 1/u-1 = +926%) |
| L1 (characterized power) error | ~0 | +3.5% | CONFIRMED |
| Lid / body energy ratio | 67.7% | **56.2%** | **FAILS**: quoted 0.677 is wrong; measured 0.562 |
| Homing share of CNC energy | ~11.7% | near 0 under register accounting | **artifact** of trapezoid attribution; see note |
| Distinct tracked operations | 45 vs 49 | 49 | resolved: 49 |
| Operations with significant wear trend | n/a | 7 of 49 (FDR) | new finding |

**Homing note:** the 11.7% figure came from trapezoid integration that
misassigned inter-operation ramp energy to TRANSITION_OVERHEAD. Under the
exact forward-kWh register the transition residual nearly vanishes, so the
"11.7% non-productive homing" claim does not survive the better accounting.
This is a methods-quality result worth stating, not burying.

Resolved earlier (no measurement data needed):

| Quantity | Old value | Verified value | Source |
|---|---|---|---|
| Body stock / finished / removed mass | 2500 / 1063 / 1437 g (estimates) | 1880 / 443 / 1437 g | owner, bom.csv |
| Lid stock / finished / removed mass | 610 / 162 / 448 g (estimates) | 518 / 70 / 448 g | owner, bom.csv |
| Body / lid measured energy (register mean/run) | est. 859 / 582 Wh | 647.3 / 364.0 Wh | compare_outputs/compare_allocation.csv |
| Mfg share at recycled Al (Indiana grid) | ~29% (old est.) | 27.5% (measured energy) | B1 recompute (stdlib check) |
| CF_al where mfg crosses 5% | 3.96 (old est.) | 3.61 kg CO2e/kg | B1 recompute (stdlib check) |

## Project status

| Project | Status | Key finding |
|---|---|---|
| theory/estimator_errors | built, stdlib-validated | L0 bias = 1/u-1; measured u 0.0975 gives +962%, matching data |
| theory/allocation_theory | built, stdlib-validated | error surface; measured rho_E is 0.562 (not quoted 0.677) |
| theory/power_decomposition | built, stdlib-validated | explains the stable ~1,306 W register mean power |
| signature_mining | built, runs on in-repo data | retrofit attribution metrics; run for measured tables |
| energy_budget | built, runs on in-repo data | full budget + closure; register makes homing residual tiny |
| uncertainty_prediction | built, runs on in-repo data | footprint CI + design-stage LOPO |
| explorations/B1_breakeven | measured energies wired | 1.56% virgin / 27.5% recycled mfg share |
| estimation_ladder | runs on in-repo data | L0 +962%, L1 +3.5%, u 0.0975 (per compare_outputs) |
| allocation | runs on in-repo data | lid/body 0.562; homing near 0 under register |
| wear_runorder | runs on in-repo data (needs scipy, statsmodels) | 7 of 49 operations show significant trend |

## Discrepancies found vs quoted numbers (state these in the paper)

- **Lid/body energy ratio: quoted 0.677, measured 0.562.** The 67.7% figure
  does not hold under the register-based measurement. Use 0.562.
- **Homing "11.7% of CNC energy" is a trapezoid-integration artifact.** The
  cumulative forward-kWh register attributes almost no energy to transition
  overhead. Report the register result and the methods lesson.
- **Fleet mean power 1,376 W quoted, 1,306 W (register) / 1,333 W (active)
  measured** (3 to 5% high). Recompute from data; do not quote the slide.
- Old stock-mass estimates (2500 / 610 g) were 25 to 33% high vs the verified
  BOM (1880 / 518 g); measured CNC energy (1.011 kWh) is also below the old
  1.441 kWh estimate. B1 shares shift down slightly but the conditional
  materials-dominance argument holds.
- Register vs active-power methods agree within ~2% on totals but diverge on
  transition attribution (186% on the body time-allocation error line); the
  register is the defensible basis. See `compare_outputs/compare_methods`.
