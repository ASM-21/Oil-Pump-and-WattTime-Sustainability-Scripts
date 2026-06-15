# AGENT BRIEF: Additive Exploratory Projects
**Repo context:** UUID-based operation-level energy attribution for CNC and FDM manufacturing (basis of MSEC2026-182984 and its JMSE journal extension). This repo already contains the data, processing pipeline, and analysis modules from the original work.

**Your job (the agent):** Add a set of self-contained exploratory projects that build *on top of* what is already here. Each is an independent folder that reuses the repo's existing loaders, tables, and modules. Do not restructure the repo, do not rebuild pipelines that already work, and do not regenerate data that already exists. These are seeds: each should produce a useful first result and leave a clear path to extend it later. Some will pan out, some will not, and that is the point.

---

## 0. Before writing any project: discover and reuse what exists

Do not build a new canonical data layer. The repo already has one in some form. Spend the first pass understanding it, then lean on it.

1. Read the existing structure. Identify where these already live and how they are loaded:
   - raw 1 Hz power streams (CNC via IAMMETER, AM)
   - UUID / MTConnect event logs that map timestamps to operation identity
   - processed per-operation / per-run energy tables (the ones behind the paper's figures)
   - the BOM and program-structure tables
   - WattTime MOER parquet data, if present in this repo
   - existing analysis modules (e.g. the manufacturing_lca_toolkit, the manufacturing_energy package, any olca-contrib / OpenLCA integration code)
2. Write a short `EXPLORATORY/_repo_map.md` recording, in a few lines each: the loader function or script that returns the processed energy table, the column names it produces, where raw streams live, and how operation identity is keyed. This is a map for the projects to import against, not a re-derivation. Keep it to one page.
3. Every project below imports the existing loaders. If a needed loader does not exist, write the smallest possible adapter inside that project's own folder and note it; do not refactor shared code.

Suggested home for all of this: a single new top-level folder `EXPLORATORY/` so nothing mixes into the validated paper pipeline. If the repo has an obvious existing place for scratch or research work, use that instead and say so in `_repo_map.md`.

---

## 1. Ground rules

1. **Additive only.** Never edit, move, or delete files outside `EXPLORATORY/`. Read from the existing repo freely; write only inside your project folders. The paper pipeline must still run untouched after you are done.
2. **Reuse over rebuild.** If a number or table already exists in the repo, load it. Only recompute when a project genuinely needs something the repo does not already produce.
3. **Never fabricate numbers.** Every reported figure comes from real data via committed code. Values quoted in this brief (≈1,376 W average power, 11.7% homing share, 67.7% lid/body energy ratio, the CVs, the 16 to 27 run counts, 45 vs 49 operations) are *expectations to check against*, not inputs. If your computed value disagrees, report both and flag it. Do not silently adopt either.
4. **Prohibited claim.** Never compute or state a specific numerical deviation multiplier against the ecoinvent aluminum-milling dataset. The allowed framing is measured within-product and between-operation spread in specific energy, on its own terms.
5. **Missing data is a finding.** If a project needs something not in the repo, write it to `EXPLORATORY/_data_gaps.md` (exact filename pattern or content expected), mark the project's README as "parked pending data," and move on. Do not invent stand-ins. The one sanctioned synthetic step is the superposition of *real measured* signals in the disaggregation project, labeled as synthetic wherever it appears.
6. **Self-contained projects.** Each folder runs on its own from the repo root with relative imports, has its own short `requirements.txt` only if it needs packages beyond what the repo already uses, fixes random seeds, and regenerates its figures from one script. Someone should be able to open any single project folder later and pick up where it left off without reading the others.
7. **Honest writeups.** Each project's `FINDINGS.md` states the result plainly, including null results, with caveats next to the numbers they qualify. Written to be readable by the repo owner's advisors.

---

## 2. Project folders to add under `EXPLORATORY/`

Each folder: `README.md` (one-paragraph plan + how to run), `*.py` (the code), `outputs/` (figures + CSVs), `FINDINGS.md` (what you found). Order is a suggestion; each stands alone, so skip and return freely. Start with the first three; they are cheap and feed the journal paper.

### `EXPLORATORY/wear_runorder/`
**Question:** does energy drift with run order within a fixed operation, consistent with tool wear?
**Approach:** load the existing per-run per-operation energy table. Order runs chronologically per operation. Per operation, regress energy on run index (OLS) and Spearman rank correlation; same for peak power. Control for multiple comparisons across operations (Benjamini-Hochberg, FDR 0.10). Group by operation category and test whether high-CV operations (drilling, spotting) trend more than finishing/cavity milling.
**First result:** a trend table and one grouped figure. A null result is a valid, useful finding for the paper's variability section. If a trend appears in drilling, that single plot is a follow-on seed.
**Reuses:** existing energy table, existing operation-category mapping. No raw-stream parsing needed.

### `EXPLORATORY/estimation_ladder/`
**Question:** how wrong are simplified energy estimates versus the measured ground truth, and how does the error depend on machine class?
**Approach:** compute, per part and program, L0 = rated power × cycle time (CNC: Hurco VMX30Ui 13.4 kW / 18 hp spindle, parameterized so a connected-load value can swap in; AM: Ultimaker 2+ Extended 221 W), L1 = machine-average power × cycle time (derive average power from the data; check against the ≈1,376 W slope), L2 = literature SEC × mass removed (Kara & Li form; mark partial if mass-removed is not in the repo), L3 = program totals (quantify what operation-level detail it cannot resolve), L4 = measured ground truth. Report signed % error per level; compute the utilization factor (mean/rated) for CNC vs AM and state the contrast.
**Also:** replication requirement per category, n = (1.96·CV/r)^2 at r = 5% and 10%, and check (from data, not assertion) that high-replication categories contribute little absolute energy.
**First result:** two tables and one bar figure, formatted for direct lift into the manuscript. This project resolves the bracketed [verify] numbers in the owner's scope document.
**Reuses:** existing energy and program tables.

### `EXPLORATORY/allocation/`
**Question:** how badly do standard LCA allocation rules misassign energy versus measured attribution?
**Approach:** take measured per-part energy as truth. Compute mass-based (stock and finished mass, both labeled), machine-time-based, and economic (material-cost proxy if no price data; else drop and note) allocations of total CNC energy. Report signed error per rule per part. Sweep synthetic production mixes by reweighting measured per-part values and plot worst-case error per rule. Quantify the homing / non-productive share (≈11.7%, verify) and show how each rule implicitly assigns it.
**First result:** error table + mix-sweep figure. Seeds a standalone allocation paper.
**Reuses:** existing per-part energy; mass values from BOM if present.

### `EXPLORATORY/emission_factors/`
**Question:** holding production fixed, how much does reported CO2e move with the emission-factor convention (annual average vs hourly average vs hourly marginal)?
**Approach:** only if MOER parquet data is in this repo (check; if not, park and log to `_data_gaps.md`). Confirm region, units (convert lb/MWh to kg/kWh explicitly), and time overlap with production timestamps. Re-convert each run's energy under each convention. Headline figure: per-program CO2e per convention with the run-to-run measurement band overlaid, answering whether accounting-choice uncertainty exceeds measurement uncertainty. Strictly diagnostic, no statements about *when* to run production (that is separate scheduling work).
**Reuses:** existing run energy traces + the thesis MOER data if co-located.

### `EXPLORATORY/disaggregation/`
**Question:** do UUID labels make operation energy recoverable from a power signal, and from a multi-machine aggregate?
**Approach:** (a) windowed features from existing 1 Hz streams; classify operation category with logistic regression then random forest; grouped cross-validation with *runs* as the group to prevent leakage; report confusion matrix. (b) synthesize an aggregate by summing time-shifted real streams (CNC + AM; label synthetic everywhere), then attribute per-operation energy with a simple NMF/sparse baseline and report error vs the known truth as machines are added.
**First result:** classification metrics + an attribution-error-vs-machines figure, framed honestly (single machine type, synthetic aggregate, transfer-to-other-machines stated as the open question).
**Reuses:** raw streams via existing loaders + the operation mapping.

### `EXPLORATORY/feature_energy/`
**Question:** can a measured feature-energy library predict one part's energy from another's?
**Approach:** map operations to the features that caused them, sourcing from existing CAM/program docs; record every assignment in `feature_map.csv` with a confidence column. Build per-feature-class energy stats (normalized by volume removed if available, else per feature and per second). Validate leave-one-part-out: train on body, predict lid, and reverse; report both errors with the explicit caveat that two parts is a proof of mechanism, not a validated tool.
**Reuses:** existing energy table + whatever feature_library module already exists in the toolkit (build on it, do not duplicate it).

### `EXPLORATORY/schemas/`
**Question:** what data structures connect this measurement work to external frameworks (PCF exchange, product passports, automated LCA)?
**Approach:** desk/software only. (a) Markdown table mapping the existing energy/footprint outputs onto PACT Tech Spec v2 fields (PCF, declared unit, primary data share, data-quality indicators); compute the manufacturing-stage primary data share for the oil pump from repo data. (b) A JSON Schema for a per-unit "manufacturing energy passport entry" (product UUID, constituent operation UUIDs, measured energy with uncertainty from the run distributions, factor convention, meter provenance) with one populated example per part from real values; this is schema design, not a compliance claim. (c) A short `replay_pipeline.md` describing how recorded UUID streams replay through the existing attribution + OpenLCA integration to an importable inventory with no manual steps, listing the concrete gaps; implement only if the existing integration makes it small.
**Reuses:** existing footprint outputs and OpenLCA/olca integration code.

### `EXPLORATORY/dataset_card/` (optional, permission-gated)
**Question:** what would it take to make the dataset release-ready later?
**Approach:** do not publish or add any release license; institutional permission is unresolved. Draft a schema and data dictionary, export a staged copy under `staging/` via one validation script, and write a `DATASET_CARD.md` (machine, material, conditions, downtime exclusions, intended uses, the paper's verbatim limitation list). Record baseline models (the disaggregation classifier + a duration-based energy-prediction baseline) so a future data paper ships with numbers to beat.

---

## 3. Wrap-up

When the projects are done or parked, add `EXPLORATORY/_summary.md`: (1) the computed numbers that resolve the scope document's bracketed placeholders, (2) which projects produced a real signal worth pursuing, ranked, each with its honest limitation, (3) any discrepancies between computed values and the previously quoted numbers, stated bluntly. Keep it to one page.

Leave a one-line status next to each project in `_summary.md`: explored / promising / null / parked-pending-data. The repo owner will decide which seeds to grow.
