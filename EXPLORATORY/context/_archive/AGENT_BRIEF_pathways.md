# AGENT BRIEF: Research Pathways Exploration
**Repo context:** UUID-based operation-level energy attribution for CNC and FDM manufacturing (basis of MSEC2026-182984 and its JMSE journal extension).
**Your job (the agent):** Create a new top-level folder `pathways/` in this repository and systematically execute the analysis workstreams below against the data already in this repo. Produce reproducible code, quantified results, and honest writeups. No new experimental data exists or will exist; everything must come from files already present.

---

## 0. Ground rules (read before any work)

1. **Never fabricate or assume numbers.** Every figure you report must be computed from data files in this repo, with the computing script committed. Numbers quoted in this brief (1,376 W average power, 11.7% homing share, 67.7% lid/body ratio, CVs, run counts) are from the paper drafts and are *expectations to verify*, not inputs. If your computed value disagrees with a quoted value, report both and flag the discrepancy in the pathway's RESULTS.md; do not silently adopt either.
2. **Prohibited claim:** never compute, state, or imply a specific numerical deviation multiplier against the ecoinvent aluminum-milling dataset (e.g. "Nx higher than ecoinvent"). The permitted framing is measured within-product and between-operation spread in specific energy, presented on its own terms.
3. **Missing data is a result, not a blocker to route around.** If a pathway needs data that is not in the repo, write what is missing to `pathways/DATA_GAPS.md` with the exact filename pattern or content you expected, mark the pathway BLOCKED in the dashboard, and move on. Do not substitute synthetic stand-ins for missing measurements (synthetic *superposition* of real measured signals in Pathway P5 is the one sanctioned exception, and must be labeled as such everywhere it appears).
4. **Units and conventions:** energy in Wh (kWh above 10,000 Wh), power in W, mass in g, durations in s, CO2e in kg. CV = standard deviation / mean, reported as a percentage. Significance threshold 0.05 throughout. Timestamps treated as the local timezone of collection (Indiana, Eastern); confirm from the data and record the determination in P0.
5. **Reproducibility:** plain Python scripts (3.11+), one `requirements.txt` at `pathways/`, every script runnable from the repo root with relative paths, deterministic seeds for anything stochastic, every figure regenerable by a single script. Notebooks are allowed for exploration but every reported number must trace to a script.
6. **Statistics hygiene:** report n alongside every mean; use Welch's t-test for two-sample comparisons unless variances are demonstrably equal; report effect sizes, not just p-values; when fitting regressions, report slope, CI, R2, and n; when a result is negative or null, say so plainly. Null results are publishable context for the journal paper.
7. **Write for a reader who will be skeptical.** Each RESULTS.md should be readable by the repo owner's thesis advisors. Caveats belong next to the numbers they qualify, not in a footer.

## 1. Repository layout to create

```
pathways/
  DASHBOARD.md          # status table: pathway, state (TODO/RUNNING/DONE/BLOCKED/NULL-RESULT), headline finding, date
  DATA_GAPS.md          # accumulating list of missing inputs
  DATA_MANIFEST.md      # output of P0
  requirements.txt
  shared/               # loaders, schema definitions, plotting style used by all pathways
    loaders.py          # canonical functions to load power streams, UUID logs, summary tables
    operations.py       # the operation taxonomy and the canonical operation/program/part mapping
    style.py            # one matplotlib style for every figure
  P0_data_inventory/
  P1_wear_runorder/
  P2_estimation_ladder/
  P3_allocation/
  P4_emission_factors/
  P5_disaggregation/
  P6_benchmark_dataset/
  P7_feature_library/
  P8_schemas_standards/
```

Each `P*` folder contains: `README.md` (plan, written before coding), `code/`, `outputs/` (figures + CSV tables), `RESULTS.md` (findings). Update `DASHBOARD.md` after every pathway state change. Commit per pathway with messages like `P1: wear run-order regression complete, null result for milling, positive trend in drilling`.

**Execution order:** P0 strictly first. Then P1, P2, P3 (cheap, journal-relevant). Then P4, P5, P7 (heavier). P6 and P8 last (curation and schema work that benefits from everything learned). If a pathway is BLOCKED, proceed to the next.

---

## P0. Data inventory and schema audit (prerequisite, blocking)

**Objective:** establish exactly what data exists, its schema, and its integrity, so every later pathway loads through `shared/loaders.py` instead of ad hoc parsing.

**Tasks:**
1. Walk the repo. Identify and catalog: raw 1 Hz power streams (CNC via IAMMETER, AM), UUID/MTConnect event logs mapping timestamps to operation identities, processed summary tables (per-operation energy per run, program tables, BOM), CAM/NX artifacts (cycle-time estimates if present), WattTime MOER parquet files, and any emission-factor constants used previously.
2. For each dataset write into `DATA_MANIFEST.md`: path pattern, row counts, columns and dtypes, time coverage, sampling rate (verify 1 Hz empirically, report gaps), units (verify W vs kW from magnitudes), and how operation identity attaches to samples.
3. Reconcile the operation count: the thesis materials variously reference 45 and 49 operations. Determine from the data what the true count of distinct tracked operations is, what the 16 to 27 run counts per program actually are, and record the canonical mapping in `shared/operations.py`. Every later pathway imports this mapping; none redefines it.
4. Integrity checks: duplicated timestamps, negative power values, runs with missing UUID boundaries, the ~20% MTConnect-downtime exclusions (identify which runs were excluded and confirm later pathways use the same inclusion set the paper used, or document the difference).
5. Compute and store one canonical per-run, per-operation energy table at `pathways/shared/canonical_energy.parquet` (run id, part, program, operation id, operation category, start, end, duration s, energy Wh, mean power W, peak power W). Cross-check totals against the paper's headline numbers (total CNC energy, total AM energy, per-program means) and report agreement in RESULTS.md.

**Definition of done:** DATA_MANIFEST.md complete; canonical table built and cross-checked; operation-count question answered with evidence; loaders importable by all pathways.

---

## P1. Tool-wear / run-order signal (fast, do first after P0)

**Objective:** test whether energy drifts with run order within nominally identical operations, consistent with tool wear, using existing timestamps.

**Method:**
1. From the canonical table, order runs chronologically per operation. Confirm run order is a valid wear proxy (same tool across runs, no recorded tool changes; if tool-change information exists anywhere in the repo, use it to segment; if not, state the assumption).
2. Per operation: OLS of energy on run index; also Spearman rank correlation (robust to nonlinearity); also the same for peak power. Multiple-comparison control across ~45 operations with Benjamini-Hochberg at FDR 0.10.
3. Aggregate by operation category: do drilling/spotting (high-CV, wear-prone) show systematically more positive trends than finishing/cavity milling? One summary figure: per-operation trend slope (normalized, % energy change per run) with CI, grouped by category.
4. Secondary: variance decomposition. How much of each operation's CV is explained by the run-order trend (R2)? This directly refines the journal paper's variability narrative.

**Outputs:** trend table (operation, category, slope %/run, CI, p, q), the grouped figure, RESULTS.md including a 3-sentence summary usable in the journal paper's limitations/future-work section.
**Acceptance:** result reported either way; a null result is explicitly stated as evidence that wear does not dominate observed variability at this run count.

---

## P2. Estimation-fidelity ladder and replication requirements (feeds the journal paper directly)

**Objective:** quantify the error of simplified energy-estimation approaches against measured ground truth, and derive replication guidance.

**Method, part A (ladder):**
1. Define estimators per part and per program: L0 = rated power × measured cycle time (CNC rated spindle 13.4 kW per Hurco VMX30Ui published spec, 18 hp; AM rated 221 W per Ultimaker 2+ Extended spec; record sources in README, and parameterize rated power so a connected-load value can be swapped in later). L1 = machine-average power × cycle time, where machine-average power is computed from the data as total energy / total duration (verify against the quoted 1,376 W regression slope; also fit the origin-forced duration-energy regression and report the slope). L2 = literature SEC × mass removed (use Kara & Li model form and a representative published SEC range for aluminum milling; cite values in README; if mass-removed per part is not derivable from repo data, mark L2 partial in DATA_GAPS). L3 = program-level metering = measured program totals (zero error at program level by construction; its error is at operation level, quantify what it cannot resolve: report the share of energy in the top-2 operations it cannot see). L4 = ground truth.
2. Report signed percent error per level, per part (body, lid, AM components), at program and part level. One table, one bar figure. Compute the utilization factor (mean power / rated power) for CNC and AM and state the machine-class contrast explicitly.
3. Sensitivity: rerun L0 with a plausible connected-load value (parameter, default 2× spindle rating, clearly labeled assumption) to bound the error range.

**Method, part B (replication):** per operation category, n_required = (1.96 × CV / r)^2 for r ∈ {0.05, 0.10}. One table. Cross with part A: note that categories needing high replication contribute little absolute energy (verify and quantify that claim from the data rather than asserting it).

**Outputs:** two tables and one figure formatted for direct lift into the journal manuscript (ASME-friendly: no color-dependence, serif-safe labels), RESULTS.md with draft-quality paragraph text.
**Acceptance:** every number traceable to script; the [bracketed verify] placeholders in the owner's scope document resolvable from this pathway's outputs.

---

## P3. Allocation-rule error analysis

**Objective:** score common LCA allocation rules against measured per-part attribution.

**Method:**
1. Ground truth: measured energy per part (body, lid; include AM parts if facility framing makes sense, else CNC-only and say so).
2. Compute allocations of the total CNC energy under: mass-based (finished mass and stock mass variants, both, labeled), machine-time-based, and economic (if no price data exists, use stock material cost as proxy and label it; if not derivable, drop economic and note in DATA_GAPS).
3. Report signed error per rule per part. Then sweep synthetic production mixes (vary body:lid ratio from 10:1 to 1:10 by reweighting measured per-part values) and plot each rule's worst-case error across mixes.
4. Treat overhead explicitly: quantify the homing/non-productive energy share from the data (expected ~11.7%, verify) and show how each rule implicitly assigns it; propose and compute one "measured attribution + explicit overhead rule" hybrid.

**Outputs:** error table, mix-sweep figure, RESULTS.md with the body/lid decoupling stated from computed values (energy per kg removed per part, if mass-removed is available).
**Acceptance:** all rules computed from the same canonical table; mass-basis (stock vs finished) handled explicitly everywhere, never mixed.

---

## P4. Emission-factor temporal sensitivity (requires the MOER parquet data)

**Objective:** holding production fixed, quantify how reported manufacturing CO2e changes with the emission-factor convention: annual average (the paper's eGRID value, locate the constant in the repo), hourly average, hourly marginal (WattTime MOER).

**Method:**
1. From P0, confirm the MOER dataset's region(s), units (lb/MWh vs kg/kWh; convert explicitly), and time coverage overlapping the production timestamps. If the relevant balancing authority for Indiana production (expect MISO) is present, use it; otherwise run the analysis across the available grid archetypes as a sensitivity envelope and label it as such.
2. Convert each run's 1 Hz energy trace to CO2e under each convention (5-minute MOER aligned to sample timestamps where resolution allows; document alignment).
3. Headline comparison figure: per-program CO2e under each convention, plus the run-to-run measurement variability band, on one axis, answering "is accounting-choice uncertainty larger than measurement uncertainty?" with a number.
4. Strictly diagnostic: no statements about when production *should* run. That framing is reserved for separate work.

**Outputs:** comparison table, the one headline figure, RESULTS.md.
**Acceptance:** unit conversions unit-tested; the convention definitions written precisely enough to survive review.

---

## P5. Operation classification and synthetic-aggregate disaggregation (ML pathway)

**Objective:** test whether UUID labels turn power signatures into a supervised learning resource: (a) classify operation category from the power signal alone; (b) attribute energy within a synthesized multi-machine aggregate signal.

**Method, part A (classification):**
1. Windowed features from 1 Hz streams (window 10 to 30 s, justify choice): mean, std, peaks, spectral features if sampling supports them, ramp rates.
2. Models: logistic regression baseline, then random forest, then (optional) a small 1D CNN on raw windows. Grouped cross-validation with runs (never samples) as the grouping unit to prevent leakage; report per-class precision/recall and confusion matrix. Classes: the operation categories from `shared/operations.py` plus idle/homing.
3. Report which categories are separable from signal alone and which confuse, tied back to the physics (sustained engagement vs transients).

**Method, part B (synthetic superposition, the sanctioned synthetic exception):**
1. Construct aggregate signals by summing time-shifted real streams (CNC + AM printers; multiple offset CNC copies as a harder variant, labeled clearly as a same-machine approximation). Ground-truth labels come free from the constituent streams.
2. Energy attribution task: estimate per-machine, per-operation energy from the aggregate; baseline NMF or sparse optimization approach is sufficient, this is a feasibility result not a SOTA claim. Report attribution error vs the known truth as a function of number of superimposed machines.

**Outputs:** metrics tables, confusion matrix figure, attribution-error-vs-machines figure, RESULTS.md positioning the result honestly (single machine type, synthetic aggregation) with the transfer-to-other-machines question stated as the open follow-on.
**Acceptance:** no leakage (grouped CV verified), seeds fixed, synthetic provenance labeled on every artifact.

---

## P6. Benchmark dataset curation (no public release; prepare only)

**Objective:** package the dataset to release-ready state pending the owner's institutional permission. Do NOT publish, push to external services, or add licenses implying release; permission is unresolved.

**Tasks:**
1. Design the release schema: per-sample table (timestamp, power, run id, operation UUID), per-operation metadata (category, tool if known, program, part, nominal parameters available in repo), per-run metadata (date, inclusion flag and reason), data dictionary in CSV and markdown.
2. Export to the schema under `P6_benchmark_dataset/staging/`, with a validation script asserting schema conformance and referential integrity.
3. Train and record baseline models for the descriptor paper: the P5 part A random forest plus a per-operation energy-prediction baseline (features: operation category, duration; report MAE/MAPE), so the eventual data paper ships with numbers to beat.
4. Draft `DATASET_CARD.md`: collection conditions, machine, material, known limitations (single machine/material, downtime exclusions), intended uses, and the verbatim caveat list from the journal paper's limitations.

**Acceptance:** a third party with repo access could reproduce the staging set from raw data via one script.

---

## P7. Feature-energy library with leave-one-part-out validation

**Objective:** build a measured feature-energy library and test cross-part prediction.

**Method:**
1. Construct the operation-to-feature mapping. Source it from CAM artifacts and program documentation in the repo; where a mapping is judgment-based (this cavity-milling op = this pocket), record every assignment in a reviewable CSV (`feature_map.csv`) with a confidence column, and have RESULTS.md state how many assignments are inferred vs documented. If volume-removed per operation is not derivable, normalize per feature instance and per second instead, and say so.
2. Library: per feature class, energy statistics (mean, CV, n) normalized by the best available basis (Wh/cm3 if volumes exist, else Wh per feature and W sustained).
3. Validation: train on body operations only, predict total lid energy from the lid's feature list; reverse; report both errors. State plainly that two parts is a proof of mechanism, not a validated tool.
4. Stability: per feature class, is normalized energy stable across runs (reuse CVs) and across the two parts where the same feature class appears on both?

**Outputs:** `feature_map.csv`, library table, LOPO prediction table, RESULTS.md.
**Acceptance:** every feature assignment auditable; prediction errors reported with the thin-validation caveat in the same paragraph.

---

## P8. Schemas and standards mapping (desk work, do last)

**Objective:** formalize the data structures so the measurement work plugs into external frameworks.

**Tasks:**
1. **PCF exchange mapping:** a markdown table mapping the canonical energy record and footprint outputs onto the PACT Tech Spec v2 data model fields (PCF, declared unit, primary data share, data quality indicators), identifying exactly which PACT fields this method can populate from measurement vs which require external inputs. Compute the manufacturing-stage primary data share for the oil pump from repo data and show the calculation.
2. **DPP-oriented record:** a JSON Schema for a per-unit "manufacturing energy passport entry": product UUID, constituent part/program/operation UUIDs, measured energy with uncertainty (from the run distributions), emission factor convention used, meter provenance. Generate one populated example instance per part from real data. This is schema design, not a compliance claim; say so in the README.
3. **Replay pipeline note:** a short architecture document (`replay_pipeline.md`) describing how recorded UUID streams replay through attribution to an OpenLCA-importable inventory with zero manual steps, referencing whatever olca/OpenLCA integration code exists in the repo, and listing the concrete gaps to a working replay. Implement the replay only if the existing integration code makes it a small step; otherwise the gap list is the deliverable.

**Acceptance:** schemas validate (use jsonschema), populated examples come from real computed values, primary-data-share calculation traceable.

---

## Final deliverable

When all pathways are DONE/BLOCKED/NULL-RESULT, write `pathways/SYNTHESIS.md`: one page per audience. (1) For the JMSE manuscript: the specific computed numbers that resolve the scope document's bracketed placeholders, plus any finding that changes the paper's claims. (2) For follow-on publication planning: which pathways produced publishable signal, ranked, each with its honest limitation. (3) For the repo owner: discrepancies found between computed values and previously quoted values, listed bluntly. Update DASHBOARD.md one final time.
