# AGENT BRIEF: Additive Exploratory Projects
**Repo:** UUID-based operation-level energy attribution for CNC and FDM manufacturing (basis of MSEC2026-182984 and its JMSE journal extension). Data, pipeline, and analysis modules already exist here.

**Task:** Add self-contained exploratory projects under one new `EXPLORATORY/` folder, each building on the repo's existing loaders and tables. Do not restructure the repo or rebuild what works. Each project produces one verified result, writes honest findings, and stops. Some will pan out, some will not.

**Use the scaffolding.** `shared/` (style, checks, adapters), `_templates/`, and `_example_project/run.py` already exist. Read them first; every project copies the example's shape (load via adapter, compute, dual-path verify, smoke test, plot, write findings).

---

## 0. Discovery and loader gate (blocks everything)

The repo already has a data layer; wire it into `shared/adapters.py`, the one place that knows the repo's data access. Projects import only from the adapter.

1. Find the loader behind the paper's per-operation energy table (likely in `manufacturing_energy` or `manufacturing_lca_toolkit`). Grep: `energy`, `Wh`, `uuid`, `operation`, `MTConnect`, `IAMMETER`, `read_parquet`, `read_csv`. Also locate raw 1 Hz streams, UUID/MTConnect logs, program/BOM tables, any MOER parquet, and the OpenLCA/olca code.
2. Implement the adapter TODOs to the documented column contract. Reconcile the 45-vs-49 operation count and the per-program run counts here, once, and encode the taxonomy. Record findings in `_repo_map.md` (one page).
3. **Gate:** write `shared/test_adapters.py` that calls each adapter, prints shape/columns, and asserts the contract. It must pass before any project runs. Absent required source -> adapter raises `DataNotInRepo`, log to `_data_gaps.md`, dependents park. Optional source (MOER) returns `None`.

Do not start projects until the gate passes for the operation-energy table.

## 1. Ground rules

1. **Additive only.** Write only inside `EXPLORATORY/` and `shared/adapters.py`. Read the rest freely. The paper pipeline must still run untouched.
2. **Reuse, don't rebuild.** Load existing tables through the adapter; recompute only what the repo lacks.
3. **Verify the quoted numbers.** Figures in this brief (~1,376 W avg power, 11.7% homing, 67.7% lid/body, the CVs, 16 to 27 runs, 45 vs 49 ops) are expectations to check via `check_against_expected`, never inputs. A DISAGREE is a finding to report, not suppress.
4. **Dual-path + smoke test.** Compute each headline number two independent ways via `cross_check` (2% tol); each project's `smoke_test()` asserts cheap invariants with `require()` and must include `require(not log.any_disagreements())`. Both must pass before writing FINDINGS.
5. **Prohibited claim.** Never state a numeric deviation multiplier vs the ecoinvent aluminum-milling dataset. Allowed: measured within-product and between-operation spread in specific energy, on its own terms.
6. **Missing data is a finding.** Append the exact expected content to `_data_gaps.md`, set status `parked-pending-data`, exit 0, move on. No stand-ins. Only sanctioned synthetic step: superposition of real measured signals in `disaggregation/`, labeled synthetic everywhere.
7. **Effort box.** Get the first real result (defined per project), verify, write findings, stop. No gold-plating, no second analysis in the same project; record next steps under "How to extend." Breadth beats depth.
8. **Reproducible + honest.** Run from repo root via `python EXPLORATORY/<project>/run.py`, relative imports, fixed seeds, figures from one script. FINDINGS states results plainly including nulls, caveats beside the numbers, from the template.

## 2. Projects

Each folder mirrors `_example_project/`: README (template, "first real result" filled), `run.py`, `outputs/`, FINDINGS (template). Do the first three first: cheap, run off the energy table without raw streams, feed the paper.

**`wear_runorder/`** Does energy drift with run order within an operation (tool wear)?
- OLS energy~run-index and Spearman per operation; same for peak power; Benjamini-Hochberg FDR 0.10; group by category and test whether high-CV ops trend more.
- Dual-path: OLS vs Spearman sign/significance agree per op.
- Result: per-op trend table (slope %/run, CI, p, q) + grouped figure. Null is valid.

**`estimation_ladder/`** How wrong are simplified energy estimates vs measured, by machine class?
- Per part/program: L0 rated x time (CNC Hurco VMX30Ui 13.4 kW/18 hp spindle, parameterized for connected load; AM Ultimaker 2+ Ext. 221 W), L1 avg-power x time, L2 SEC x mass-removed (Kara & Li; partial if mass absent), L3 program totals, L4 ground truth. Signed % error per level; utilization factor (mean/rated) CNC vs AM. Then replication n=(1.96*CV/r)^2 at r=5%,10% per category; verify high-replication categories contribute little energy.
- Dual-path: avg power via energy/duration vs origin-forced regression slope.
- Result: % error per level/part (table + bar figure) + replication table, manuscript-ready. Resolves the scope doc's [verify] numbers.

**`allocation/`** How badly do LCA allocation rules misassign energy vs measured?
- Measured per-part energy = truth. Allocate total CNC energy by mass (stock and finished, labeled), machine-time, economic (material-cost proxy or drop+note). Signed error per rule/part. Sweep synthetic production mixes; plot worst-case error. Quantify homing share (~11.7%) and how each rule assigns it; propose a measured+explicit-overhead hybrid.
- Dual-path: allocated shares sum to measured total under every rule (conservation).
- Result: error table + mix-sweep figure; body/lid energy-per-kg-removed if mass available.

**`emission_factors/`** Holding production fixed, how much does CO2e move with factor convention (annual avg vs hourly avg vs hourly marginal)? *(needs MOER in repo, else park)*
- Confirm region, units (lb/MWh -> kg/kWh), time overlap. Re-convert each run under each convention. Strictly diagnostic, no scheduling claims.
- Dual-path: per-run-summed annual-avg CO2e vs program-total CO2e match; conversions unit-tested.
- Result: per-convention CO2e figure with the run-to-run measurement band overlaid + table.

**`disaggregation/`** Do UUID labels recover operation energy from a power signal and a multi-machine aggregate?
- (a) Windowed features from 1 Hz streams; logistic-reg then random-forest classifier; grouped CV with runs as the group (no leakage); confusion matrix. (b) Sum time-shifted real streams (synthetic, labeled); attribute per-op energy with NMF/sparse baseline; error vs truth as machines added.
- Dual-path: synthetic aggregate energy = sum of constituents; grouped CV verified leak-free.
- Result: classification metrics + confusion matrix; attribution-error-vs-machines figure. Frame honestly (single machine type, synthetic).

**`feature_energy/`** Can a measured feature-energy library predict one part's energy from another's?
- Map ops to causal features from CAM/program docs into `feature_map.csv` (confidence column; report inferred vs documented). Per-feature-class energy stats (per cm^3 if volumes exist, else per feature and per second). LOPO: train on body, predict lid, and reverse. Build on the existing feature_library module.
- Dual-path: library per-class means reconstruct the training part's total to rounding.
- Result: `feature_map.csv`, library table, LOPO errors both directions, with the two-parts caveat.

**`schemas/`** What structures connect this work to PCF exchange, passports, automated LCA? *(desk/software only)*
- (a) PACT Tech Spec v2 field-mapping table; compute the oil pump's manufacturing-stage primary data share from repo data. (b) JSON Schema for a per-unit energy passport entry (product/op UUIDs, measured energy + uncertainty, factor convention, meter provenance); one populated, jsonschema-validated example per part. (c) `replay_pipeline.md` describing recorded-stream replay through existing attribution + OpenLCA, with gap list; implement only if small.
- Result: validating JSON example per part + PACT mapping with the primary-data-share number.

**`dataset_card/`** *(optional, permission-gated)* What makes the dataset release-ready later?
- Do NOT publish or add a release license. Draft schema + data dictionary, stage a copy under `staging/` via one validating script, write `DATASET_CARD.md` (conditions, exclusions, uses, the paper's verbatim limitations). Record baseline models (classifier + duration-based energy baseline, MAE/MAPE).
- Result: validating staged export reproducible from raw via one script + the card.

## 3. Runner, wrap-up, done

- `run_all.py`: runs the gate, then each `run.py` in order, catching nonzero exits, printing per-project status (ok / parked / smoke-failed). Never stops on a parked or failed project.
- `_summary.md` (one page): computed numbers resolving the scope doc's [verify] placeholders; projects with real signal, ranked, each with its limitation; every discrepancy vs quoted numbers, blunt; status per project (explored / promising / null / parked).
- **Done when:** gate passes and `_repo_map.md` + `adapters.py` complete; each non-parked project has README, clean-running `run.py`, recorded cross-check, passing smoke test, outputs, FINDINGS; `_data_gaps.md`, `run_all.py`, `_summary.md` exist; nothing outside `EXPLORATORY/` changed.
