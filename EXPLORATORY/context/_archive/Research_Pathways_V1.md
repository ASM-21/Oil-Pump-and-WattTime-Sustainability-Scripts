# Research Pathways: Extending Operation-Level Energy Attribution
**Companion to:** JMSE_Extension_Scope_V1.md and MSEC2026-182984 journal extension
**Purpose:** Map the research directions that the UUID-based operation-level energy attribution work naturally opens. Each pathway is assessed for (a) what it contributes to the June 30 journal paper now, as positioning text in Related Work, Discussion, or Future Work, and (b) what it could become as standalone follow-on research.

**The core asset, stated once:** This work produces something rare: energy data that is simultaneously operation-labeled (via UUID), statistically characterized (16 to 27 replicates with fitted distributions), and natively connected to the digital thread (CAM-originated identifiers that survive into production). Nearly every pathway below exists because some research community needs exactly that combination and currently lacks it.

---

## Pathway 1: Machine-verifiable carbon passports and Digital Product Passport readiness

**The hook.** The EU Ecodesign for Sustainable Products Regulation (ESPR) is rolling out Digital Product Passports by product category from 2026 to 2030, with iron and steel first in 2026 and aluminum following in 2027. DPPs require a unique product identifier linked to verified data including carbon footprint per unit. Your case study product is machined aluminum. The regulatory wave is arriving at exactly the material class you measured.

**The connection.** Almost everyone approaching DPPs treats the carbon number as something computed once from databases and pasted into the passport. Your architecture inverts that: the UUID hierarchy already assigns identity at the operation, program, and part level, and energy attribution happens automatically per physical unit produced. The passport entry becomes a measurement record rather than an estimate, traceable down to which operations on which runs produced this serial number. You already built a carbon passport module in the manufacturing_lca_toolkit, so a reference implementation exists.

**Research questions.**
- What data schema connects CAM-level UUIDs to the DPP unique-identifier requirements (QR/NFC data carrier, machine-readable record)?
- What is the minimal verification chain that lets a downstream auditor confirm a passport's manufacturing-energy entry traces to raw meter data?
- How does per-unit measured footprint variation (your run-to-run CVs) get represented in a passport that regulation assumes is a single number per model or batch?

**Novelty.** DPP literature is dominated by data-governance and traceability work; the manufacturing-measurement side (where the verified number actually comes from) is thin. A paper demonstrating end-to-end "CAM UUID to power meter to passport record" for a real multi-part product would be early in that space.

**For the June 30 paper.** Two to three sentences in the Implications section: the UUID hierarchy is structurally compatible with emerging product-passport requirements, since both rest on unique identifiers carrying verified per-unit data, and aluminum products enter the DPP regime in 2027. This upgrades the existing CBAM/CSRD motivation from "reporting pressure exists" to "a specific data infrastructure is being mandated, and this method feeds it."

**As follow-on work.** Standalone paper: "From Toolpath to Passport: Operation-Level Measurement as the Primary Data Layer for Digital Product Passports." Venues: JMSE, Journal of Industrial Information Integration, or CIRP conferences. Feasibility is high because it is mostly schema design and software around data you already have; no new machine time required.

---

## Pathway 2: Primary data share and PCF exchange networks (PACT, Catena-X)

**The hook.** Industry consortia (WBCSD PACT, Catena-X in automotive, TfS in chemicals) have built frameworks for exchanging primary-data-based product carbon footprints tier to tier through supply chains, including a formal data model, data quality metrics, and a "primary data share" indicator measuring what fraction of a PCF rests on measured rather than database values.

**The connection.** These frameworks specify how PCFs are exchanged and scored but are largely silent on how a machine shop generates high-primary-share data in the first place. Your method is the missing upstream generator: it raises the primary data share of the manufacturing stage to essentially 100 percent and produces the per-operation provenance the data quality metrics want. There is a clean systems argument: exchange standards without measurement infrastructure just move estimates around faster.

**Research questions.**
- Map UUID-attributed energy data onto the PACT data model fields (data quality ratings, primary data share) and quantify how operation-level measurement changes a part's reported data quality score versus database-based calculation.
- For a multi-tier assembly like the oil pump (in-house CNC, in-house AM, purchased hardware), what does the composite primary data share look like, and where is the next-best measurement investment?

**Novelty.** Academic work on primary data share indicators exists (recent Ecological Indicators work formalizes the metric), but the literature connecting shop-floor measurement methods to consortium exchange formats is nearly empty. You would be writing the manufacturing-engineering half of a conversation currently dominated by sustainability-software vendors.

**For the June 30 paper.** One Discussion sentence: consortium frameworks such as PACT and Catena-X formalize the exchange of primary-data-based footprints across supply chains, and operation-level attribution provides the shop-floor measurement layer those exchanges presuppose.

**As follow-on work.** Medium effort, high industrial relevance, very strong job-market signaling for sustainability roles in manufacturing. Could be a magazine-style or review-plus-demonstration paper.

---

## Pathway 3: UUID labels as ground truth for energy disaggregation (the NILM inversion)

**The hook.** Non-intrusive load monitoring (NILM) research tries to decompose an aggregate electrical signal into individual loads, and its chronic bottleneck is labeled training data. Your system generates exactly that labeling automatically: every 1 Hz sample carries an operation identity.

**The connection, and why it matters economically.** Per-machine metering at $200 to 500 per machine is cheap for one machine and expensive for a facility with hundreds. The research question is whether a model trained on UUID-labeled data from a few metered machines can attribute energy from a single facility-level or panel-level meter. If yes, the deployment cost of operation-level footprinting collapses: meter a few machines once, then disaggregate everywhere. This is the scalability argument your reviewers will eventually ask about, answered with a research program.

**Research questions.**
- Can operation category (cavity milling, drilling, finishing, idle, homing) be classified from power signatures alone, trained on UUID labels? Your Figure 4 power profiles suggest the signatures are distinctive.
- How does classification accuracy degrade moving from machine-level to panel-level to facility-level metering, with multiple machines superimposed?
- Does a model trained on one Hurco transfer to a different machining center (the transfer question shared with Pathway 4)?

**Novelty.** NILM is mature for buildings and appliances, immature for industrial loads, and almost untouched for operation-level (sub-machine) resolution because nobody had labels at that granularity. You do.

**For the June 30 paper.** One Future Work sentence framing UUID-labeled data as supervised training data for disaggregation, addressing scale-up beyond per-machine metering.

**As follow-on work.** This is a strong standalone ML-for-manufacturing paper and arguably the most publishable single follow-on (JMSE, Journal of Manufacturing Systems, Applied Energy). Needs only your existing dataset for the first paper (classification on machine-level data); facility-level superposition can be simulated by summing signals before requiring any new hardware.

---

## Pathway 4: A benchmark dataset and the attribution-versus-prediction bridge

**The hook.** The ML energy-prediction literature (the Brillinger, Xu, Schmitt line already going into your Related Work) predicts energy from process parameters, and every one of those papers is limited by small, privately collected, inconsistently labeled datasets.

**The connection.** Your dataset is the complement: measured, operation-labeled, replicated, with CAM metadata. Publishing it (45+ operations, 16 to 27 runs each, 1 Hz, UUID-labeled, with the BOM and program structure tables) creates a citable community resource. The r3DiM benchmark in your merge worksheet did this for FDM resource characterization and gets cited precisely because benchmarks are scarce. There is also a conceptual contribution: attribution systems and prediction models are usually treated as rivals, but attribution is actually the label factory for prediction. A short position-style section or paper making that argument, with your data as evidence, ties the two literatures together.

**Research questions.**
- What metadata schema makes an operation-level energy dataset reusable (operation type taxonomy, tool, material, engagement parameters, machine state)?
- Train the simplest credible baseline models (random forest on operation features, as in Brillinger) on your data and report baselines for others to beat.

**For the June 30 paper.** Optional single sentence offering the dataset upon publication (check with Liddell/Hartman and IN-MaC on data release policy first). Data availability statements measurably increase citation rates and reviewers like them.

**As follow-on work.** A data descriptor paper (Scientific Data, Data in Brief, or JMSE technical brief) is fast to produce and compounds: every future user cites both the dataset and the method paper.

---

## Pathway 5: The allocation problem, measured

**The hook.** Allocation (dividing shared burdens among products) is one of the oldest unresolved arguments in LCA methodology. Facilities allocate overhead energy by mass, machine hours, or economic value, and the choice changes results materially. The methodological literature is enormous; the empirical literature measuring how wrong each allocation rule is, is small.

**The connection.** You have ground truth. Your homing finding (11.7 percent of CNC energy is non-productive repositioning) is an unallocated burden question in miniature: which operation, and therefore which design feature, owns that energy? At facility scale: take your measured per-part energy as truth, then compute what mass-based, time-based, and economic allocation would have assigned each part, and report the error of each rule. The body/lid pair is a perfect test case because mass-based allocation fails badly for them (the lid draws 67.7 percent of the body's energy at a fraction of its mass).

**Research questions.**
- Quantify allocation-rule error against measured attribution for a multi-product machine. Which rule is least bad, and does the answer depend on product mix?
- Propose a measured-attribution allocation hierarchy: meter where you can, allocate residual overhead (idle, HVAC-adjacent loads) by a defensible rule, and report the allocated fraction explicitly.

**Novelty.** Empirical falsification of allocation rules using sub-machine measured data appears genuinely rare. This is the kind of paper LCA methodologists cite for a decade.

**For the June 30 paper.** The body/lid mass-versus-energy decoupling text (already planned via the merge worksheet and item C1 of the scope document) is this pathway's seed. Add one sentence naming it explicitly: this decoupling implies mass-based allocation of facility energy would misassign burden between these components, motivating measured attribution as an allocation method.

**As follow-on work.** Target Journal of Industrial Ecology or Int. J. of LCA, which would also diversify your publication portfolio outside ASME.

---

## Pathway 6: Energy signatures as a process-health and tool-wear signal

**The hook.** Your variability section keeps gesturing at this: drilling and spotting CVs near 20 percent, tool wear untracked across 16 to 27 runs and flagged as a likely variability contributor in the limitations. Condition-monitoring research wants exactly the longitudinal, operation-resolved power data you already collected, because energy drift within a nominally identical operation is a wear and anomaly indicator.

**The connection, and the strategic value.** This pathway changes the economics of the whole method. Sustainability monitoring alone struggles to justify shop-floor investment; condition monitoring (catching a dulling tool before it scraps a part) pays for itself. If the same UUID-tagged meter stream serves both, the carbon data rides for free on a quality system. That dual-use argument is the strongest answer to "why would a real shop do this."

**Research questions.**
- Within a single operation UUID across runs, is there a monotonic energy or peak-power trend consistent with tool wear, distinguishable from random variation? (Run order is in your timestamps; this is analyzable from existing data.)
- Can operation-level energy distributions serve as statistical control limits, so an out-of-distribution run flags inspection?

**For the June 30 paper.** Strengthen the existing tool-wear limitation sentence into a forward statement: because each operation's energy distribution is now characterized, departures from it become a detectable signal, suggesting a shared infrastructure for environmental accounting and process health monitoring.

**As follow-on work.** First analysis is free (regress energy on run order per operation in existing data). If a wear trend shows up in the drilling operations, that single plot seeds a paper for Journal of Manufacturing Processes or MSEC 2027.

---

## Pathway 7: Emission-factor temporal resolution applied to measured runs

**The hook.** The paper converts measured electricity to CO2e using one annual average factor (eGRID Indiana). But grid carbon intensity varies hour to hour, and you have deep expertise and a 408M-row marginal-emissions dataset from the thesis's other half. There is a clean question that is not scheduling: holding production fixed, how much does the reported footprint change purely from the analyst's choice of emission factor (annual average, hourly average, hourly marginal)?

**The connection.** Your runs are timestamped at 1 Hz, so each run can be re-converted with the hourly factor in effect when it actually ran. This is a sensitivity analysis on an accounting choice, performed on measured data, and it quantifies a methodological uncertainty most product footprints silently ignore. Keep it strictly diagnostic; the moment it recommends moving production in time, it becomes the scheduling work, which stays separate per the merge worksheet.

**Research questions.**
- What is the spread in reported manufacturing CO2e for identical runs executed at different times, under each factor convention?
- Is the factor-choice uncertainty larger or smaller than the run-to-run measurement variability you quantified? (Comparing the two uncertainty sources in one figure would be elegant and very citable.)

**For the June 30 paper.** Probably too much for June 30 unless Tier A finishes early; if so, it slots into the carbon footprint section as a short sensitivity paragraph. Otherwise one Future Work sentence, phrased carefully to stay distinct from scheduling.

**As follow-on work.** Natural bridge paper between your two thesis chapters that is neither of them, suitable for Journal of Cleaner Production or Applied Energy.

---

## Pathway 8: Standards-based digital twin and automated LCI integration

**The hook.** ISO 23247 defines a digital twin framework for manufacturing; the Asset Administration Shell (AAS) ecosystem is developing submodels for carbon footprint data; and the Brundage et al. work already in your Related Work demonstrated standards-based reusable LCI data models. The automated-LCA reviews you cite (Da Costa, Schneider) both conclude implementations remain absent.

**The connection.** Your system is one of the missing implementations, but it is currently bespoke (custom NX macro, custom Python post-processing, custom OpenLCA handoff). The research move is formalization: define the UUID-attributed energy record as a standard submodel or information model so any CAM system, controller, and LCA tool can implement it. Your OpenLCA MCP agent and olca-contrib work mean you have already built two-thirds of the reference pipeline.

**Research questions.**
- What is the minimal information model for an operation-level energy record (identifier, time bounds, energy, power statistics, machine state, upstream CAM reference) that supports both LCA import and DPP export?
- Demonstrate round-trip automation: NX toolpath to controller execution to metered attribution to OpenLCA inventory to footprint report, with no manual steps, and report where the standards gaps are.

**Novelty.** "We propose a framework" papers are common in this space; "we ran the full automated loop on a real product and here is what broke" papers are rare and far more useful.

**For the June 30 paper.** The existing OpenLCA-integration future-work paragraph covers this; add the standards vocabulary (one clause referencing digital twin frameworks and standardized information models) so the paper signals awareness of where the field is heading.

**As follow-on work.** Strong fit for Journal of Computing and Information Science in Engineering (Hartman's home turf) or Robotics and Computer-Integrated Manufacturing.

---

## Pathway 9: Feature-level energy mapping for design (the JMD-facing program)

**The hook.** The special issue is joint with the Journal of Mechanical Design for a reason: the field wants tools that put manufacturing-environmental consequences in front of designers. Your data already contains the seed result: the lid's deep pockets make it twice as energy-intensive per kg removed as the body.

**The connection.** Operations map to features (this cavity-milling UUID exists because that pocket exists). Accumulate operation-level energy against the features that caused the operations and you get a measured feature-energy library: pockets of given depth-to-width cost X Wh per cm3, tapped holes cost Y, tight-tolerance finishing surfaces cost Z. That library plugs into design-stage tools: a CAD plugin or design-rule table flagging energy-expensive features before CAM even runs. Your existing feature library module in manufacturing_lca_toolkit and the A2 cycle-time prediction item are both stepping stones.

**Research questions.**
- How stable are feature-normalized energy values (Wh per cm3 removed, per feature class) across runs and across parts? Your CV data partially answers this already.
- Can feature recognition on a new part geometry, combined with the library, predict part energy without CAM programming at all? (This goes one level earlier than A2, which still requires toolpaths.)
- Where does the feature library break: across tools, materials, machines?

**Novelty.** Design-for-environment feature guidance exists but rests on modeled or database energy values. A measured, statistically characterized feature-energy library, with uncertainty per feature class, would be a distinct contribution and the most JMD-shaped thing on this list.

**For the June 30 paper.** The Discussion already says designers can evaluate features against quantified energy; sharpen with one sentence proposing the feature-energy library as the design-stage artifact this method produces over time.

**As follow-on work.** This is the most coherent multi-paper program here: paper 1 (library construction from existing data), paper 2 (prediction on unseen geometry), paper 3 (design tool integration and user study). If you ever pursue a PhD or an R&D role pitch, this is the slide.

---

## Cross-cutting notes

**Access reality.** Pathways 3, 4, 5, 6, and 7 run entirely on data you already possess, which matters now that you have graduated and IN-MaC machine time is no longer guaranteed. Pathways 1, 2, and 8 are mostly software and schema work. Only Pathway 9's later stages and any near-net-shape comparison genuinely require new machine experiments; structure collaborations with the remaining IN-MaC group accordingly.

**What goes into the June 30 paper from all this.** Roughly six to eight sentences total, distributed: DPP and PCF-exchange sentences in Implications (Pathways 1 and 2), an allocation clause attached to the body/lid discussion (Pathway 5), an upgraded tool-wear sentence (Pathway 6), a standards clause in the OpenLCA future-work paragraph (Pathway 8), a feature-library sentence in Discussion (Pathway 9), and disaggregation plus emission-factor-sensitivity sentences in Future Work (Pathways 3 and 7). This widens the paper's perceived horizon substantially at near-zero word cost, which is exactly what distinguishes a journal discussion from a conference one.

**Sequencing if you pursue follow-ons.** Fastest publishable wins in order: Pathway 6 first analysis (days), Pathway 4 data descriptor (weeks), Pathway 3 classification paper (one to two months), Pathway 5 allocation paper (one to two months). Pathways 1, 8, and 9 are the larger programs that those smaller papers feed.

**One caution.** Resist putting any new pathway's analysis into the June 30 submission beyond the sentences above. The Tier A items in the scope document are the journal delta; these pathways are the horizon the paper points at. A reviewer reads breadth in the discussion as vision, but half-executed extra analyses as padding.
