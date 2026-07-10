# Paper argument map: code outputs to journal sections

Each row maps a computed number or figure to the paper section where it lands,
what claim it supports, and which output file to pull it from.

This is not a draft. It is a checklist for wiring analysis results into the manuscript.

---

## Results section: estimation fidelity ladder (new vs conference paper)

| Claim in paper | Number / figure | Source file | Status |
|---|---|---|---|
| L0 (rated power) overestimates CNC energy by X% | `L0_mean_error_pct` per part | `estimation_ladder/outputs/program_run_errors.csv` | run estimation_ladder |
| Characterized average power (L1) reduces error to ~0% | `L1_mean_error_pct` per part | same | run estimation_ladder |
| SEC x mass (L2) error depends on aluminum milling SEC assumption | `L2_mean_error_pct` per part | same | run + verify MASS_REMOVED_G |
| Fleet average operating power = X W (two-path verified) | `avg_power_w` in FINDINGS.md | `estimation_ladder/FINDINGS.md` | run estimation_ladder |
| CNC utilization u = X (mean/rated) | `u_cnc` in summary | `estimation_ladder/outputs/summary_by_part.csv` | run estimation_ladder |
| FDM utilization u ~= 0.90 (contrast with CNC ~0.10) | `u_fdm` in summary | spec sheet now; computed by `explorations/A2_fdm_utilization.py` once AM_DATA_DIR is set | available now |
| Replication requirements: n = (1.96 x CV / r)^2 per category | full table | `estimation_ladder/outputs/operation_cv_replication.csv` | run estimation_ladder |

**Figure:** `estimation_ladder/outputs/estimation_error_by_level.png` -- bar chart of signed % error per level per part. Goes in Results as the main estimation-fidelity exhibit.

**Figure:** `estimation_ladder/outputs/duration_vs_energy_slopes.png` -- scatter of all operations with L0 and L1 slope lines. Shows why L1 works and L0 does not.

---

## Results section: operation-level attribution (carry from conference, reinforce)

| Claim | Number / figure | Source | Status |
|---|---|---|---|
| 40 of 45 operations near-normal (Shapiro-Wilk p > 0.05) | `n_near_normal` / `n_sw_tested` | `estimation_ladder/outputs/normality_shapiro_wilk.csv` | run estimation_ladder |
| Per-program 95% CI on mean energy: X% | `ci_95_pct` per program | `estimation_ladder/outputs/uncertainty_intervals.csv` | run estimation_ladder |
| Lid energy = 67.7% of body energy (or measured value) | `lid_body_ratio` | `allocation/outputs/part_mean_energy.csv` | run allocation |
| Homing (non-productive repositioning) = 11.7% of CNC energy | `homing_share` | `allocation/FINDINGS.md` | run allocation |

---

## Results section: LCA allocation analysis (new contribution)

| Claim | Number / figure | Source | Status |
|---|---|---|---|
| Time-based allocation error for body: X%, lid: Y% | `time_error_pct` | `allocation/outputs/allocation_rule_errors.csv` | run allocation |
| Mass-based allocation error (removed basis): X% | `mass_error_pct` | same | run allocation + verify masses |
| Economic allocation collapses to mass allocation for same-material products | text only | argue from first principles | no code needed |
| Allocation error varies with production mix (body:lid ratio) | sweep figure | `allocation/outputs/mix_sweep.csv` | run allocation |

**Figure:** `allocation/outputs/allocation_error_by_rule.png` -- bar chart of time vs mass allocation error per part.

**Figure:** `allocation/outputs/allocation_error_mix_sweep.png` -- allocation error vs body:lid production ratio. Key exhibit for the new contribution.

---

## Results section: within-product specific energy (C1, new)

| Claim | Number / figure | Source | Status |
|---|---|---|---|
| Body specific energy: ~0.36 kWh/kg removed | `body_sec_kwh_per_kg` | `allocation/outputs/specific_energy_per_part.csv` | run allocation + verify masses |
| Lid specific energy: ~0.78 kWh/kg removed | `lid_sec_kwh_per_kg` | same | same |
| Same material, different energy intensity per kg -- aggregation masks this | comparison of two rows | same | run allocation |

This is the "aggregation-masking" argument made concrete: the body and lid are both Al6061,
but their per-kg energy differs by ~2x. An aggregate SEC number hides this.

---

## Discussion: when does manufacturing energy start to matter (B1)

| Claim | Number / figure | Source | Status |
|---|---|---|---|
| At virgin aluminum (~12 kg CO2e/kg), manufacturing = ~2% of product footprint | `manufacturing_share_pct` for "Virgin (global avg)" | `explorations/outputs/B1_scenarios.csv` | run B1_breakeven.py |
| At recycled aluminum (~0.5 kg CO2e/kg), manufacturing can exceed 20% | same row for "Recycled (secondary)" | same | run B1_breakeven.py |
| Manufacturing crosses 5% when aluminum CF drops to X kg CO2e/kg | `cf_al_breakeven_kgco2e_per_kg` at 5% | `explorations/outputs/B1_breakeven_thresholds.csv` | run B1_breakeven.py |

**Figure:** `explorations/outputs/B1_breakeven_contour.png` -- contour of manufacturing share vs aluminum CF and grid CI. One figure, citable, for Discussion.

**Framing argument (no new code needed):** the paper's "limitation" (materials dominate, so manufacturing energy is small) is conditional. As aluminum decarbonizes and as grid intensity falls, the manufacturing component grows in relative importance. The measurement capability this paper establishes matters more in that future, not less.

---

## Discussion: run-to-run variability and wear (wear_runorder)

| Claim | Number / figure | Source | Status |
|---|---|---|---|
| Operations showing significant run-order trend at FDR 0.10 | count + which operations | `wear_runorder/outputs/wear_runorder_results.csv` | run wear_runorder (needs scipy, statsmodels) |
| i.i.d. assumption holds for most operations | fraction not significant | same | run wear_runorder |

If no significant trends are found: that is a clean verification result. The paper's implicit
assumption that runs are exchangeable is supported. Report it explicitly rather than omitting it.

If trends are found: report which operation categories show drift. High-variability categories
(spotting, tapping, drilling) are the most likely candidates.

---

## Discussion: utilization-factor landscape (A1, desk note)

No code output needed. Use these values from the literature (A1_utilization_landscape.md)
alongside computed u_CNC and u_FDM:

| Machine class | Utilization u | Source |
|---|---|---|
| CNC machining center (this work) | ~0.10 (computed) | estimation_ladder output |
| FDM / filament deposition (this work) | ~0.90 (computed) | estimation_ladder output |
| Injection molding | 0.60 to 0.80 | Gutowski et al. |
| Grinding | 0.30 to 0.50 | Kara and Li 2011 |
| Laser / EDM | 0.30 to 0.70 | Kara and Li 2011 |

The span is wide enough to make the argument that u is not a footnote: it determines which
estimation shortcut is acceptable for a given machine class.

---

## Results/Discussion: theory layer (new, added 2026-07-09)

These are closed-form results, complete and fixture-validated now; real data
adds only the empirical confirmation points. Derivations in `theory/README.md`,
brute-force validation in `theory/selftest_stdlib.py`.

| Claim in paper | Number / figure | Source file | Status |
|---|---|---|---|
| Rated-power (L0) bias is the identity 1/u - 1; acceptable only when u >= 1/(1+r) | bias curve + machine-class ranges | `theory/estimator_errors/outputs/l0_bias_vs_utilization.png`, `machine_class_bias.csv` | run estimator_errors |
| The right estimation shortcut is decidable from machine class alone | regime map on (u, CV) plane | `theory/estimator_errors/outputs/regime_map.png` | run estimator_errors |
| Allocation error = phi(rho_E - rho_x)/(1 + phi rho_x); zero only when attribute tracks energy | error surface + rules-vs-mix curves | `theory/allocation_theory/outputs/` | run allocation_theory |
| At 1:1 mix (quoted rho_E 0.677): mass-removed allocation errs +27.8%, economic +44.8% on the body | `rule_errors_at_mixes.csv` | same | computed (stdlib selftest); verify rho_E from data |
| Duration-based (L1) estimation works because base load dominates: err_i = (lam_bar - lam_i)/(1 + lam_i) | per-category lambda table + split figure | `theory/power_decomposition/outputs/` | run power_decomposition |
| Measured SEC sits inside published milling ranges | `sec_benchmark.csv` | same | needs CNC data for measured rows |

## Results: signature mining (new, added 2026-07-09)

| Claim in paper | Number / figure | Source file | Status |
|---|---|---|---|
| Operation boundaries are recoverable from power alone (retrofit claim) | boundary recall/precision/F1 | `signature_mining/outputs/boundary_recovery_measured.csv` | needs CNC data (fixture set exists) |
| Operation identity is recoverable from waveform features | LORO fingerprint accuracy | `signature_mining/outputs/` + FINDINGS.md | needs CNC data |
| Signatures transfer across parts at category level | cross-part transfer accuracy | FINDINGS.md | needs CNC data |
| Machine-state split (off/idle/positioning/cutting) of time and energy | `state_shares_measured.csv` + figure | `signature_mining/outputs/` | needs CNC data |

## Results: energy budget closure (new, added 2026-07-09)

| Claim in paper | Number / figure | Source file | Status |
|---|---|---|---|
| Full productive vs non-productive budget (generalizes the 11.7% homing number) | `category_budget_measured.csv` + stacked figure | `energy_budget/outputs/` | needs CNC data |
| Attribution closes against independent stream integration to < 5% | worst closure residual | `energy_budget/outputs/closure_measured.csv` | needs CNC data |

## Results/Discussion: uncertainty and design-stage prediction (new, added 2026-07-09)

| Claim in paper | Number / figure | Source file | Status |
|---|---|---|---|
| Product manufacturing energy has a defensible 95% interval (MC vs delta cross-checked) | interval per part | `uncertainty_prediction/outputs/footprint_intervals_measured.csv` | needs CNC data |
| Manufacturing-share intervals per aluminum scenario | interval fan figure | `uncertainty_prediction/outputs/mfg_share_intervals_measured.png` | needs CNC data |
| Program energy is predictable from CAM-planned durations (design-stage claim) | LOPO mean abs error % | `uncertainty_prediction/outputs/design_stage_loo_measured.csv` + scatter | needs CNC data |

## Numbers that reviewers will specifically challenge

These are the three flagged in GROUND_TRUTH.md. Make sure each has an explicit, stated basis:

1. **Rated power basis for u_CNC:** spindle rating (13,400 W) vs total connected load. State which you used.
   If you have the electrical plate, report both. If not, note the limitation explicitly.

2. **Measured average power (1,376 W):** computed from data via two independent paths.
   Do not quote this from a slide -- recompute from the CSV files and report the two-path agreement.

3. **Mass basis for allocation and specific energy:** stock mass, finished mass, or mass removed.
   Pick one basis, use it everywhere, state it explicitly. Old drafts mixed bases (72% vs 84% lighter).

---

## Checklist: what `_summary.md` should show when everything is run

After running all projects and `build_summary.py`, open `EXPLORATORY/_summary.md`.
Every row in the "Key numbers" table should show a computed value, not `[verify]`.

Remaining `[verify]` rows after running with data = either a data gap (log to `_data_gaps.md`)
or a parameter that needs updating in the script (e.g., MASS_REMOVED_G).
