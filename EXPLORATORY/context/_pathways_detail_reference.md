# Research Pathways V2: Extending Operation-Level Energy Attribution Without New Experiments
**Companion to:** JMSE_Extension_Scope_V1.md and MSEC2026-182984 journal extension
**Constraint governing this revision:** No new experimentation or data collection is possible. You are no longer physically at IN-MaC. A collaborator could in principle do a few small things in the lab, but that channel is unreliable and should be treated as a bonus, not a dependency. Every pathway below is therefore classified by what it actually requires.

**Feasibility classes used throughout:**
- **Class A: existing data plus analysis.** Runs entirely on the dataset and files you already possess. Fully under your control.
- **Class B: software, schema, and desk work.** No data or lab needed at all. Fully under your control.
- **Class C: one small collaborator favor.** A bounded, minutes-scale task someone at IN-MaC could do. Design these so the work survives if the favor never happens.
- **Class D: proposal-only.** Requires machine time or new instrumentation. You can write about these (future work, research statements, proposals) but cannot execute them. Kept here because articulating them well still has value for the paper and for job-search materials.

**Do this first, before anything else:** inventory what you actually have locally. The binding constraint is no longer lab access; it is whether the raw 1 Hz power streams, UUID timestamp logs, NX part and CAM files, and processed tables live on your own drive or only on the IN-MaC server. Every Class A pathway assumes local copies. If anything critical exists only on the server, getting a bulk copy pulled is the single collaborator favor worth spending goodwill on, because it unlocks everything else at once. One request for "zip the project directory and the raw data folder" is far more likely to happen than five separate small asks spread over months.

**The core asset, restated:** energy data that is simultaneously operation-labeled (UUID), statistically characterized (16 to 27 replicates with fitted distributions), and natively connected to the digital thread. The fortunate structural fact is that this asset is a dataset, not a machine. Losing lab access cost you the ability to grow it, not the ability to mine it, and most of the value was always in the mining.

---

## Pathway 1: Machine-verifiable carbon passports and Digital Product Passport readiness
**Class B (software and schema), demonstration on existing data.**

**The hook.** The EU Ecodesign for Sustainable Products Regulation rolls out Digital Product Passports by category from 2026 to 2030, iron and steel first, aluminum in 2027. DPPs require a unique product identifier linked to verified data including per-unit carbon footprint. Your case study product is machined aluminum; the regulatory wave arrives at exactly the material class you measured.

**The connection.** Most DPP work treats the carbon entry as a database estimate pasted into a passport. Your architecture inverts that: the UUID hierarchy assigns identity at operation, program, and part level, and attribution happens per physical unit. The passport entry becomes a measurement record traceable to raw meter data. You already built a carbon passport module in manufacturing_lca_toolkit; the demonstration product (the oil pump, with its full measured dataset) already exists. Nothing about this pathway needs a machine.

**Research questions.**
- What schema connects CAM-level UUIDs to DPP unique-identifier and data-carrier requirements?
- What minimal verification chain lets an auditor trace a passport's manufacturing-energy entry back to meter data?
- How should per-unit measured variation (your run-to-run CVs) be represented in a passport regime that assumes one number per model or batch? This question is uniquely yours to answer, because almost nobody else has per-unit measured distributions.

**For the June 30 paper.** Two to three sentences in Implications: the UUID hierarchy is structurally compatible with emerging product-passport requirements, and aluminum enters the DPP regime in 2027. Upgrades the CBAM/CSRD motivation from "reporting pressure exists" to "a specific data infrastructure is being mandated and this method feeds it."

**As follow-on work.** Standalone paper built entirely from your dataset plus schema design: "From Toolpath to Passport." Venues: JMSE, Journal of Industrial Information Integration, CIRP conferences. One of the two best post-graduation pathways because it is pure software over data you own.

---

## Pathway 2: Primary data share and PCF exchange networks (PACT, Catena-X)
**Class B (desk work and mapping exercise).**

**The hook.** Industry consortia (WBCSD PACT, Catena-X, TfS) have built frameworks for exchanging primary-data-based product carbon footprints tier to tier, with formal data models, data quality metrics, and a primary data share indicator scoring how much of a PCF rests on measurement rather than databases.

**The connection.** These frameworks specify how PCFs are exchanged but are largely silent on how a machine shop generates high-primary-share data. Your method is the missing upstream generator. The systems argument: exchange standards without measurement infrastructure just move estimates around faster.

**Research questions.**
- Map UUID-attributed energy onto the PACT data model fields and quantify how operation-level measurement changes a part's data quality score versus database calculation.
- For the oil pump assembly (in-house CNC, in-house AM, purchased hardware), compute the composite primary data share and identify the next-best measurement investment. Entirely computable from existing tables.

**For the June 30 paper.** One Discussion sentence: consortium frameworks formalize the exchange of primary-data-based footprints, and operation-level attribution provides the shop-floor measurement layer those exchanges presuppose.

**As follow-on work.** Medium effort, high industrial relevance, and strong job-market signaling for manufacturing-sustainability roles. Requires literally nothing but the frameworks' public documents and your existing results.

---

## Pathway 3: UUID labels as ground truth for energy disaggregation (the NILM inversion)
**Class A (existing data). Multi-machine transfer portion is Class D.**

**The hook.** Non-intrusive load monitoring research decomposes aggregate electrical signals into individual loads, and its chronic bottleneck is labeled training data. Your system generated that labeling automatically: every 1 Hz sample carries an operation identity.

**The connection and the economics.** Per-machine metering is cheap once and expensive at facility scale. If a model trained on UUID-labeled data can attribute energy from a panel-level or facility-level signal, the deployment cost of operation-level footprinting collapses. This is the scalability answer reviewers will eventually ask for.

**What is executable without the lab.** More than it first appears:
- Operation-category classification from power signatures (cavity milling vs drilling vs finishing vs idle vs homing), trained and tested on your existing machine-level data. Your Figure 4 profiles suggest the signatures are distinctive. This alone is a paper.
- Facility-level superposition can be **simulated**: sum your CNC stream with your AM streams (time-shifted, resampled) to synthesize a multi-machine aggregate signal with perfect ground-truth labels, then test disaggregation against it. Synthetic aggregation from real component signals is an accepted methodology in the NILM literature precisely because labeled aggregate data is scarce. No new hardware, no lab.

**What is not executable.** Transfer to a physically different machining center requires someone else's metered machine. That moves to Class D and one future-work sentence.

**For the June 30 paper.** One Future Work sentence framing UUID-labeled data as supervised training data for disaggregation.

**As follow-on work.** The strongest standalone ML paper available to you, fully feasible from your laptop. Venues: Journal of Manufacturing Systems, Applied Energy, JMSE.

---

## Pathway 4: A benchmark dataset and the attribution-versus-prediction bridge
**Class A (existing data). Gating item is permission, not access.**

**The hook.** The ML energy-prediction literature (the Brillinger, Xu, Schmitt line in your Related Work) is limited by small, private, inconsistently labeled datasets.

**The connection.** Your dataset is the complement: measured, operation-labeled, replicated, with CAM metadata, BOM, and program structure. Publishing it creates a citable community resource, the way the r3DiM benchmark did for FDM. The conceptual contribution rides along: attribution and prediction are usually framed as rivals, but attribution is the label factory for prediction.

**The real gate.** Not lab access but release permission: IN-MaC and Purdue data policy, plus co-author sign-off from Liddell and Hartman. That is an email thread, not an experiment, and it is worth starting now because institutional permissions move slowly. Also verify you hold a complete local copy of what you would release (see the inventory note at the top).

**Executable work.** Curate and document the dataset; define the metadata schema (operation taxonomy, tool, material, machine state); train simple baselines (random forest per Brillinger) so future users have numbers to beat. All local.

**For the June 30 paper.** Optional sentence offering the dataset upon publication, contingent on the permission thread resolving in time. If unresolved by submission, omit; it can accompany the follow-on instead.

**As follow-on work.** Data descriptor in Scientific Data or Data in Brief. Fast, and it compounds: every future user cites the dataset and the method paper.

---

## Pathway 5: The allocation problem, measured
**Class A (existing data, arguably the cleanest desk paper here).**

**The hook.** Allocation of shared burdens among products is one of LCA's oldest unresolved arguments. The methodological literature is enormous; the empirical literature measuring how wrong each allocation rule is, is small, because doing so requires sub-machine measured ground truth. You have it.

**The connection.** Take measured per-part energy as truth, then compute what mass-based, time-based, and economic allocation would have assigned each part, and report each rule's error. The body/lid pair is the perfect test case: mass-based allocation fails badly (the lid draws 67.7 percent of the body's energy at a fraction of its mass). The homing finding (11.7 percent non-productive energy) poses the unallocated-burden question in miniature: which operation, and therefore which design feature, owns that energy?

**Research questions.**
- Quantify allocation-rule error against measured attribution for a multi-product machine. Which rule is least bad, and does it depend on product mix? Product mix can be varied **synthetically** by reweighting your measured per-part data into hypothetical production mixes, again requiring nothing new.
- Propose a measured-attribution allocation hierarchy: meter where possible, allocate residual overhead by a stated rule, report the allocated fraction explicitly.

**For the June 30 paper.** Attach one sentence to the body/lid decoupling discussion: this decoupling implies mass-based allocation of facility energy would misassign burden between these components, motivating measured attribution as an allocation method.

**As follow-on work.** Journal of Industrial Ecology or Int. J. of LCA. Diversifies your portfolio outside ASME, and it is the paper LCA methodologists would cite for a decade.

---

## Pathway 6: Energy signatures as a process-health and tool-wear signal
**Class A for the discovery analysis. Deployment validation is Class D.**

**The hook.** Drilling and spotting CVs near 20 percent, with tool wear untracked across 16 to 27 runs and flagged in your limitations as a likely contributor. Condition-monitoring research wants longitudinal, operation-resolved power data, which you already collected.

**The strategic value.** This pathway fixes the business case for the whole method: sustainability monitoring alone struggles to justify shop-floor investment, but catching a dulling tool before it scraps a part pays for itself. If one UUID-tagged meter stream serves both, carbon data rides for free on a quality system.

**Executable now, from your desk.** Run order is in your timestamps. Regress energy (and peak power) on run order within each operation UUID. A monotonic trend in the drilling and spotting operations, distinguishable from noise, is the discovery result, and it doubles as a partial explanation of your variability findings. This is days of work on data you have.

**Not executable.** Controlled wear experiments (machining to known wear states, flank wear measurement) and live control-limit deployment need the lab. Class D; write them as the validation step a future group should run.

**For the June 30 paper.** Strengthen the tool-wear limitation into a forward statement: because each operation's energy distribution is characterized, departures from it become a detectable signal, suggesting shared infrastructure for environmental accounting and process health. If the run-order regression shows a trend, one sentence reporting it materially upgrades the limitations section; do this analysis before the submission if any analysis time remains after Tier A.

**As follow-on work.** If the trend exists, that single plot seeds a Journal of Manufacturing Processes paper or an MSEC 2027 submission, executed entirely without lab access.

---

## Pathway 7: Emission-factor temporal resolution applied to measured runs
**Class A (existing data on both sides: 1 Hz timestamped runs plus your MOER dataset).**

**The hook.** The paper converts measured electricity using one annual average factor. Grid carbon intensity varies hourly, and you hold a 408M-row marginal-emissions dataset from the thesis's other half. The clean, non-scheduling question: holding production fixed, how much does the reported footprint change purely from the analyst's choice of emission factor (annual average, hourly average, hourly marginal)?

**The connection.** Each run is timestamped at 1 Hz, so each can be re-converted with the hourly factor in effect when it actually ran. This is a sensitivity analysis on an accounting choice, performed on measured data. The elegant comparison: is factor-choice uncertainty larger or smaller than the run-to-run measurement variability you quantified? Putting both uncertainty sources in one figure would be genuinely novel and entirely computable from files on your machine. Keep it diagnostic; any move toward recommending when to produce becomes the scheduling work, which stays separate.

**For the June 30 paper.** Too much for June 30 unless Tier A finishes very early; otherwise one carefully phrased Future Work sentence.

**As follow-on work.** A natural bridge paper between your two thesis chapters that is neither of them. Journal of Cleaner Production or Applied Energy. Among the Class A options this is the one where you have the most unfair advantage, since both required datasets already sit on your drive.

---

## Pathway 8: Standards-based digital twin and automated LCI integration
**Class B for the information model and replay pipeline. Live round-trip is Class C/D.**

**The hook.** ISO 23247 defines a manufacturing digital twin framework; the Asset Administration Shell ecosystem is developing carbon-footprint submodels; Brundage et al. (already in your Related Work) demonstrated standards-based reusable LCI data models; and the automated-LCA reviews you cite conclude implementations remain absent.

**The connection, reframed for no lab access.** Your pipeline is bespoke (custom NX macro, custom post-processing, custom OpenLCA handoff). The formalization work (defining the operation-level energy record as a standard information model that any CAM system, controller, and LCA tool could implement) is pure desk work. The demonstration changes form: instead of a live shop-floor round trip, run a **replay** of your recorded production data through the standardized pipeline end to end (recorded UUID stream in, OpenLCA inventory and footprint report out, zero manual steps). A replayed demonstration on real recorded data is honest, reproducible, and publishable; a live demonstration becomes the one-paragraph future validation. Your OpenLCA MCP agent and olca-contrib work mean two-thirds of the reference implementation already exists.

**For the June 30 paper.** Add standards vocabulary to the existing OpenLCA future-work paragraph: one clause referencing digital twin frameworks and standardized information models.

**As follow-on work.** Journal of Computing and Information Science in Engineering (Hartman's home turf) or Robotics and Computer-Integrated Manufacturing.

---

## Pathway 9: Feature-level energy mapping for design
**Class A for library construction and a leave-one-part-out validation. Broader validation is Class D.**

**The hook.** The special issue is joint with JMD because the field wants manufacturing-environmental consequences in front of designers. Your seed result already exists: the lid's deep pockets make it roughly twice as energy-intensive per kg removed as the body.

**The connection, reframed.** Operations map to features. Accumulating operation-level energy against causal features yields a measured feature-energy library (pockets of given depth-to-width cost X Wh per cm3, tapped holes cost Y, tight-tolerance finishing costs Z), with uncertainty per feature class straight from your CV data. The original three-paper program assumed new parts for validation; without the lab, the honest validation is **leave-one-part-out within your existing data**: build the library from body operations only, predict the lid's energy from its features, compare against the lid's measured energy (and the reverse). Two parts is a thin validation set and the paper must say so plainly, but as a proof of mechanism it stands, and it is the most JMD-shaped result you can produce from your desk.

**Research questions (executable subset).**
- How stable are feature-normalized energy values across runs? (Directly answerable from existing CV data.)
- Does a body-trained feature library predict lid energy within useful bounds, and vice versa?

**Class D remainder.** Library coverage across more feature types, tools, materials, and machines; CAD-plugin integration; designer user studies. These become the future-work program and, frankly, the strongest slide in any PhD application or R&D job pitch you assemble.

**For the June 30 paper.** One Discussion sentence proposing the feature-energy library as the design-stage artifact this method produces over time.

---

## Cross-cutting notes

**The honest summary of what changed.** Surprisingly little died. Of the nine pathways, seven are executable to a publishable result with zero lab access (1, 2, 3, 4, 5, 6, 7), one needs only reframing from live demo to replay demo (8), and one needs an honest thin-validation caveat (9). What you lost is the ability to *validate at breadth*: new machines, new materials, new parts, controlled wear states. The consistent writing move across everything is to convert those validations from claimed work into well-specified future work that a group with a lab could pick up, which is also exactly what makes the journal paper's future-work section credible rather than hand-wavy.

**Collaborator favors, ranked by value per minute of their time.** Spend goodwill in this order and stop when it runs out:
1. Bulk copy of anything not already on your local drive (raw 1 Hz streams, UUID logs, NX project files). One request, unlocks everything. If you already have complete local copies, skip entirely.
2. Photo of the Hurco electrical plate for the connected-load figure in scope item A1. Pure bonus: the published 18 hp spindle rating already supports the analysis, the plate only strengthens it. Do not block A1 on this.
3. Nothing else. Every other favor (re-running a part, wear measurements, metering another machine) is real work, not a favor, and belongs in a proper collaboration conversation, not a request.

**NX cycle times for scope item A2, without the lab.** If you have the NX part and CAM files locally, the toolpath time estimates regenerate on any machine with an NX license (Purdue students and recent grads often retain academic license access; check yours before assuming this is blocked). If the CAM files are server-only, fold them into favor 1. If neither works, A2 drops and B1 (uncertainty propagation, fully local) takes its timeline slot, exactly as the scope document already provides.

**What goes into the June 30 paper from all of this.** Unchanged from V1: roughly six to eight sentences distributed across Implications, Discussion, and Future Work, mapped per pathway above. The constraint changes nothing about the paper, because the paper was never going to contain new experiments anyway.

**Sequencing for follow-on work, revised for the constraint.** Fastest publishable wins in order: Pathway 6 run-order regression (days), Pathway 7 emission-factor sensitivity (one to two weeks, biggest unfair advantage), Pathway 4 data descriptor (weeks, start the permission email now), Pathway 3 classification paper (one to two months), Pathway 5 allocation paper (one to two months). Pathways 1, 2, 8, and 9 are the framing-heavy programs those papers feed. All of it runs from your laptop in New Jersey.
