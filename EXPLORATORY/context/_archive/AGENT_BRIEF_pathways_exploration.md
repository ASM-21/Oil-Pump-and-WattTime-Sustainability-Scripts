# AGENT BRIEF: Pathways Exploration for Operation-Level Energy Attribution Research
**Repo context:** This brief lives in Andrew Morrissey's research GitHub. It directs an autonomous coding agent to create and populate a new top-level folder, `pathways-exploration/`, that systematically explores nine research pathways extending the MSEC2026-182984 paper (UUID-based operation-level energy attribution for CNC and FDM manufacturing) and its JMSE journal extension.

**Hard constraint:** No new experimental data can be collected, ever. All analysis runs on data already in this repo or provided by Andrew. If a required input does not exist, the correct behavior is to document the gap and produce the fallback deliverable, never to synthesize, interpolate, or assume measurement values.

---

## 0. Ground rules for the agent

1. **Never fabricate data or results.** Every number in any RESULTS.md must be computed by a script in the same pathway folder and traceable to a raw input file. If an analysis cannot run because data is missing, write the finding as "BLOCKED: requires <file/description>" in that pathway's RESULTS.md and add an entry to `pathways-exploration/BLOCKERS.md`.
2. **Never reference any "48x" deviation figure relative to ecoinvent or any other database.** The research position is that aggregated databases mask operation-level variation; it makes no specific multiplier claim. If legacy files in the repo contain such a figure, do not propagate it.
3. **Reproducibility is mandatory.** Every figure and table regenerates from `make all` or a `run_all.py` at the pathway level. Pin seeds (`numpy`, `sklearn` random_state=42). Maintain one shared `environment.yml` or `requirements.txt` at `pathways-exploration/` root.
4. **Do not commit large data.** Raw 1 Hz streams and parquet files stay out of git. Add a `.gitignore` covering `*.parquet`, `*.csv` over 10 MB, and a `data/` symlink convention. Scripts take a `--data-root` argument defaulting to an environment variable `ENERGY_DATA_ROOT`.
5. **Units and conventions.** Energy in Wh at operation level, kWh at part/product level. Power in W. Always state which. Timestamps in ISO 8601 with timezone. CV reported as percent. Significance threshold 0.05 with multiple-comparison correction where more than 5 tests run together (Benjamini-Hochberg).
6. **Writing style in generated docs:** plain prose, no em dashes, minimal bolding, every claim tied to a script output.
7. **When judgment is needed** (e.g., mapping an operation name to a design feature, choosing an emission factor dataset variant), make the most defensible choice, record it in a `DECISIONS.md` at the pathway level, and flag it for Andrew's review. Do not silently bake judgment calls into results.

---

## 1. Folder structure to create

```
pathways-exploration/
  README.md                  (overview, status table of all pathways)
  BLOCKERS.md                (all missing inputs, one place)
  SUMMARY.md                 (cross-pathway findings, written last)
  environment.yml
  common/
    loaders.py               (canonical data loading: runs, operations, UUID logs)
    schema.py                (dataclasses for Operation, Run, Program, Part)
    stats.py                 (CV, replication-n formula, BH correction, bootstrap CI)
    plotting.py              (one consistent style)
    DATA_INVENTORY.md        (Phase 0 output, see below)
  p1_carbon_passport/
  p2_pcf_exchange/
  p3_disaggregation/
  p4_benchmark_dataset/
  p5_allocation/
  p6_tool_wear_signal/
  p7_emission_factor_sensitivity/
  p8_digital_twin_schema/
  p9_feature_energy_library/
```

Each pathway folder contains: `README.md` (objective, inputs, method), `run_all.py` or numbered scripts, `figures/`, `tables/`, `RESULTS.md`, and `DECISIONS.md` if any judgment calls were made.

---

## 2. Phase 0: Data inventory (do this first, everything depends on it)

Scan the repo (and `ENERGY_DATA_ROOT` if set) and produce `common/DATA_INVENTORY.md` cataloging:

- Raw 1 Hz power streams: file paths, machines covered (Hurco VMX30Ui CNC, Ultimaker 2+ Extended AM units), date ranges, columns present (active power, reactive power, cumulative energy register, voltage/current), sampling completeness.
- UUID logs: operation-level timestamp boundaries, the operation taxonomy (expected: roughly 45 to 49 CNC operations across 6 programs covering body and lid, plus AM print jobs; note the known 45 vs 49 count discrepancy and report which the data supports).
- Processed tables: per-operation energy statistics (mean, SD, CV, n runs), program totals, part totals, the duration-energy regression inputs (expected slope near 1,376 W), homing energy decomposition, AM energy statistics.
- CAM artifacts: NX part files, CAM setups, any exported cycle-time estimates.
- WattTime MOER data: parquet files, grid regions covered (expect BPA, CAISO_N, ERCOT_NC, ISONE_CT, MISO_INDY, SPP_KS), date ranges, resolution. Identify which region and period overlaps the production timestamps (production was in Indiana; MISO_INDY is the relevant region).
- Existing software assets: manufacturing_lca_toolkit (carbon_passport, feature_library, training_table modules), olca-contrib, OpenLCA MCP agent. Record module paths and what they already implement, because P1, P8, and P9 build on them rather than starting fresh.

For every pathway below, append a line to DATA_INVENTORY.md: pathway id, required inputs, status (AVAILABLE / PARTIAL / MISSING), and which deliverable tier that status permits.

Build `common/loaders.py` against whatever formats are actually found. All pathway scripts import from it; no pathway parses raw files directly.

---

## 3. Execution order

Run pathways in this order, committing each before starting the next:

1. **P6** (smallest, fast signal check)
2. **P7** (both datasets local, biggest unfair advantage)
3. **P5** (pure arithmetic on processed tables)
4. **P3** (largest compute, start after the quick wins are banked)
5. **P9** (depends on a human-in-the-loop mapping step, start the template early so Andrew can fill it while P3 runs)
6. **P4** (curation; can interleave)
7. **P2**, then **P1**, then **P8** (desk/schema work, no data risk)

---

## 4. Pathway specifications

### P6: Tool wear and process health signal in run-order energy trends
**Question:** Within each nominally identical operation, does energy or peak power drift monotonically with run order, consistent with tool wear?

**Inputs:** per-run, per-operation energy values with timestamps (run order derivable from timestamps).

**Method:**
1. For each operation UUID with n >= 10 runs: OLS of energy on run index; also Spearman rank correlation (robust to nonlinearity). Same for peak power if the 1 Hz streams are available.
2. BH-correct p-values across all operations tested. Report effect size as percent energy change from first to last run implied by the fitted slope.
3. Stratify findings by operation category (drilling, spotting, tapping, cavity milling, face milling, finishing). Hypothesis: wear-sensitive categories (drilling, spotting) show trends; sustained milling does not.
4. Control check: regress on wall-clock date as well as run index; if programs were run in interleaved sessions, separate session effects from cumulative-run effects where the timestamps permit.
5. Secondary analysis: for each operation, compute what fraction of its variance (CV^2) the fitted trend explains. This directly upgrades the journal paper's limitations section.

**Deliverables:** `RESULTS.md` with a findings table (operation, n, slope, percent drift, q-value), one figure of energy vs run order for the 6 strongest cases, one summary figure of percent drift by operation category. Explicit statement of whether a wear-consistent signal exists.

**Acceptance:** every operation with n >= 10 appears in the table; corrections applied; nulls reported as plainly as positives.

### P7: Emission-factor temporal-resolution sensitivity
**Question:** Holding production fixed, how much does reported manufacturing CO2e change purely from the choice of emission factor: annual average vs hourly average vs hourly marginal?

**Inputs:** timestamped per-run energy; MISO_INDY MOER parquet covering the production window; the annual average factor used in the paper (eGRID Indiana/RFCW value; locate the exact value and vintage used in the paper or thesis and record it in DECISIONS.md).

**Method:**
1. Join each run's 1 Hz (or per-operation interval) energy to the hourly marginal factor in effect at execution time. Compute per-run, per-part, and total CO2e under: (a) annual average, (b) hourly marginal. If an hourly *average* intensity series is available or derivable, include it as (c); if not, document and proceed with two conventions.
2. Report the distribution of per-run CO2e for nominally identical runs under each convention. Key comparison figure: for each program, two error bars side by side, one showing run-to-run measured energy variability converted at fixed factor, one showing factor-choice spread at fixed energy. The question the figure answers: which uncertainty source is bigger?
3. Sensitivity table: total product manufacturing CO2e under each convention, signed percent difference from the paper's published value.
4. Guardrail: purely diagnostic. No scheduling recommendations, no "if production moved to hour X" counterfactuals. That is separate forthcoming work and must not appear here.

**Deliverables:** RESULTS.md, the two-uncertainty-sources figure, sensitivity table. One paragraph drafted in journal-paper voice that Andrew can lift if Tier A of the paper finishes early.

**Acceptance:** factor vintages and sources documented; timezone handling verified (production timestamps vs MOER timestamps must align; off-by-one-hour errors are the classic failure here, write a unit test for the join).

### P5: Allocation rules vs measured ground truth
**Question:** How wrong are standard LCA allocation rules (mass, machine-time, economic) compared to measured per-part attribution?

**Inputs:** measured per-part energy (body, lid, AM components); part masses (stock and finished, both, because the known mass-basis discrepancy of 72 vs 84 percent lighter must be handled explicitly: compute on both bases and report both); machine time per part; placeholder economic values (flag in DECISIONS.md; use relative machining cost proxied by machine time at a single rate if no prices exist, and clearly label the economic rule as proxy-based).

**Method:**
1. Define the facility-energy pool as total measured CNC energy plus the homing/non-productive share. Compute each part's allocated share under each rule. Error = allocated minus measured, in Wh and percent.
2. Synthetic product-mix sweep: reweight the measured per-part data into hypothetical mixes (e.g., 10:1 body:lid through 1:10) and show how each rule's error moves with mix. Pure arithmetic, no new data.
3. The homing question: compute how the 11.7 percent non-productive energy lands under each rule, and propose (in prose) a measured-attribution hierarchy: meter what you can, allocate the documented residual by a stated rule, report the allocated fraction.

**Deliverables:** RESULTS.md, allocation-error table (rule x part x mass-basis), mix-sweep figure, a drafted paragraph in journal voice for the body/lid discussion.

**Acceptance:** both mass bases computed; the proxy nature of the economic rule labeled; no rule silently dropped.

### P3: Operation classification and synthetic-aggregate disaggregation (NILM inversion)
**Question A:** Can operation category be classified from power signatures alone, using UUID labels as ground truth?
**Question B:** Does classification survive when multiple machines' signals are superimposed (synthetic facility meter)?

**Inputs:** 1 Hz power streams with UUID interval labels. If only processed summaries exist and raw streams are missing, this pathway is BLOCKED beyond a degraded variant (classify from summary features only); say so and stop.

**Method:**
1. Windowing: segment streams into UUID-labeled windows. Feature extraction per window: mean, SD, min, max, percentiles, ramp rates, duration, simple spectral features (FFT band energies at 1 Hz Nyquist limits, document the limitation), transient counts.
2. Classifier: random forest and gradient boosting baselines. **Split by run, never by sample**, so no window from a test run leaks into training. Report macro F1, per-class confusion matrix. Classes: operation categories (cavity milling, face milling, drilling, spotting, tapping, finishing, engraving, homing/idle) rather than the 45+ individual operations; record the category mapping in DECISIONS.md.
3. Synthetic aggregation: time-shift and sum the CNC stream with one and then multiple AM streams (resample to common 1 Hz grid) to create aggregate signals with perfect labels. Test (a) whether CNC operation classification degrades on the aggregate, and (b) whether a simple source-separation baseline (e.g., subtract the known AM signature template) recovers performance. Cite the synthetic-aggregation precedent from NILM literature in the README.
4. Honest scoping: single machine per class means no cross-machine generality claim. Write the transfer question as future work requiring other labs' data.

**Deliverables:** RESULTS.md with metrics, confusion matrices, one figure showing example labeled power signatures per category, one figure of accuracy vs number of superimposed machines. A `models/` folder with the trained baselines and a `predict.py` demo.

**Acceptance:** run-level splits verified by an assertion in code; class imbalance reported; degraded-variant fallback documented if raw streams missing.

### P9: Feature-energy library with leave-one-part-out validation
**Question:** Do measured operation energies, mapped to the design features that caused them, predict the energy of a part not used to build the library?

**Inputs:** per-operation energy statistics; an operation-to-feature mapping. The mapping is the human-in-the-loop step: **generate `feature_mapping_TEMPLATE.csv`** (columns: operation_id, operation_name, program, inferred_feature_class, feature_dimensions_if_known, confidence, notes) pre-filled with the agent's best inference from operation names (e.g., "cavity milling" implies pocket; "tapping" implies threaded hole), flag low-confidence rows, and ask Andrew to verify before the validation step runs. Check whether manufacturing_lca_toolkit's feature_library module already encodes some of this mapping; reuse it if so. Normalizations to support: Wh per operation, and Wh per cm3 removed where removal volumes are derivable from CAM or part geometry, with the source of each volume documented.

**Method:**
1. Build the library from body operations only: per feature class, energy statistics with uncertainty (use common/stats.py bootstrap CIs).
2. Predict lid energy by summing library values over the lid's features; compare to measured lid energy. Repeat in reverse (lid-trained, body-predicted). Report signed percent error with propagated uncertainty.
3. State the validation thinness plainly: two parts, one machine, one material. The result is proof of mechanism, not generality.

**Deliverables:** the verified mapping CSV, library table per feature class, validation RESULTS.md, one figure of predicted vs measured with uncertainty bands.

**Acceptance:** validation does not run until the mapping CSV has Andrew's sign-off recorded (a `mapping_approved: true` flag in the CSV header or a signoff note); until then deliver the template and the library-construction code tested on the unverified mapping with results clearly marked PRELIMINARY.

### P4: Benchmark dataset curation and baselines
**Question:** What would releasing this dataset look like, and what baseline numbers should accompany it?

**Inputs:** everything inventoried in Phase 0. **Gate:** public release requires Purdue/IN-MaC permission and co-author sign-off; the agent's job is to prepare everything so release is a button-press once permission lands, not to publish anything.

**Method:**
1. Define the release schema: per-operation records (UUID, category, program, part, run index, timestamps, energy, power stats), per-run records, program/part rollups, plus a metadata datasheet following the "Datasheets for Datasets" structure (motivation, composition, collection process, recommended uses, limitations).
2. Write the curation pipeline: raw to release format, with an anonymization pass (strip any facility-identifying fields, absolute file paths, personnel names).
3. Train and report the baseline models from P3's classifier and a simple energy-prediction regressor (predict operation energy from category plus duration) so the descriptor paper has numbers others can beat.
4. Draft `DATASET_README.md` and a data-descriptor paper skeleton (target: Scientific Data or Data in Brief format).

**Deliverables:** curation pipeline, datasheet, baselines table, descriptor skeleton, and a PERMISSIONS.md listing exactly who must approve what before release.

### P2: PCF exchange mapping (PACT / Catena-X)
**Desk work, no data risk.**

1. Obtain the public PACT Technical Specifications for PCF Data Exchange (v2.x data model) and the Catena-X PCF Rulebook. Build `pact_mapping.md`: a field-by-field table mapping UUID-attributed measurement outputs to PACT data model fields, with special attention to primary data share (pds) and data quality indicators.
2. Compute the oil pump's composite primary data share under the PACT definition: manufacturing-stage energy is measured (primary); raw material and purchased hardware are database (secondary). Use the paper's published footprint shares (materials roughly 97.9 percent of total). Produce the number and show its sensitivity to the materials assumption.
3. Output a JSON example: one operation-level energy record serialized as a PACT-conformant PCF data fragment, plus prose on what the spec cannot represent (run-to-run distributions, operation provenance) as identified gaps. Those gaps are the research contribution.

**Deliverables:** mapping table, pds computation script and result, example JSON, gaps memo.

### P1: Carbon passport / DPP readiness demonstrator
**Software over existing data; builds on P2's mapping and the existing carbon_passport module.**

1. Audit manufacturing_lca_toolkit's carbon_passport module: document what it already does in `EXISTING_CAPABILITY.md`.
2. Define a passport record schema for one physical oil pump unit: unique product identifier, per-part manufacturing energy and CO2e with measurement provenance (which UUIDs, which runs, which meter), materials entries marked as database-derived, and a per-unit uncertainty field carrying the run-to-run CI. Align field names with ESPR DPP vocabulary where public guidance exists (unique identifier, data carrier reference, carbon footprint per unit) and with the P2 PACT mapping.
3. Generate the demonstrator: a script producing a complete passport JSON for a hypothetical serial-numbered unit from the measured dataset, plus a rendered human-readable version, plus a QR code pointing at the JSON (static demo is fine).
4. Write `VERIFICATION_CHAIN.md`: the auditor's path from passport entry back to raw meter records, and where the current pipeline would fail an audit (gaps again framed as research contributions).

**Deliverables:** schema, demonstrator script and example passport, verification-chain memo.

### P8: Standardized information model and replay pipeline
**Software; the live shop-floor loop is out of scope by constraint.**

1. Define the minimal operation-level energy record information model (identifier, time bounds, energy, power statistics, machine state, upstream CAM reference, downstream LCA reference) as a JSON Schema plus prose. Cross-reference ISO 23247 digital twin framework vocabulary and note where an AAS-style carbon submodel would carry it; cite Brundage et al. 2019 as the standards-based LCI lineage.
2. Build the **replay** demonstration: recorded UUID stream and meter data in, standardized records out, OpenLCA inventory generated via the existing olca-contrib / OpenLCA MCP agent tooling, footprint report out, zero manual steps. Wrap as `replay_pipeline.py` with a single command entry point.
3. Document every point where the replay needed bespoke glue: that list is the standards-gap finding.

**Deliverables:** JSON Schema, replay pipeline, gaps list, architecture diagram (mermaid in markdown is fine).

---

## 5. Reporting and wrap-up

After all pathways have run or blocked:

1. Write `SUMMARY.md`: one paragraph per pathway (finding or blocker), then a cross-cutting section answering: which pathways produced publishable-grade results, which produced journal-paper sentences, which are blocked and on what. Include a status table: pathway, class (A/B/C/D), status, headline result, next human action.
2. Update the top-level `README.md` status table.
3. Produce `JOURNAL_SENTENCES.md`: the six to eight sentences for the June 30 JMSE paper, each tagged with its target section (Implications, Discussion, Future Work) and the pathway and script output that backs it. Andrew lifts from this file directly.
4. Open one issue per blocker in the repo tracker if issue creation is available; otherwise BLOCKERS.md suffices.

**Definition of good results, overall:** a reviewer-skeptical reader can clone the repo, set ENERGY_DATA_ROOT, run each pathway's run_all, and reproduce every number in every RESULTS.md. Negative and null findings written up with the same care as positive ones. No claim anywhere that outruns the single-machine, single-material, two-part scope of the underlying data.
