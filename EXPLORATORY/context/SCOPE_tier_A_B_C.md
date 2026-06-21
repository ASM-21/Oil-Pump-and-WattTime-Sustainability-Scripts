# JMSE Special Issue Extension: Scoped Plan for New Contributions
**Target:** JMSE, Joint Special Issue on Advances in Design and Manufacturing for Sustainability (Series 2)
**Deadline:** June 30, 2026 (extended). Initial review completed August 1, 2026; publication January 2027.
**Working assumption:** MSEC (June 14 to 18) takes most of that week, leaving roughly 8 to 10 working days of real analysis and writing time.

This document covers three things: (1) prioritized new contributions with effort estimates and exactly what data or computation each needs, (2) drop-in draft text for the highest-priority items, and (3) the revised journal structure. Items from the existing merge worksheet (Chapter 2 transplants) are assumed done or in progress and are not repeated here.

---

## 1. Strategic framing for this special issue

The joint JMD/JMSE issue explicitly wants work at the design-manufacturing interface. The conference paper is a manufacturing measurement paper. The single highest-leverage move for this venue is to add a contribution that makes the measured data useful at the **design stage**, before any metering exists. Two of the priority items below (A1 and A2) do exactly that, and they convert your strongest intuition (practitioners estimate energy as rated power times duration, but machines run far below rating) into quantified, generalizable findings.

The generalizable takeaways the journal version should land on:

1. Simplified LCI estimation methods carry quantifiable, systematic error, and the error depends on machine class. Nameplate-based estimates overestimate CNC machining energy by roughly an order of magnitude but are nearly correct for desktop FDM.
2. Average power is a stable machine-level constant (your 1,376 W regression slope with tight clustering), which means cycle time from CAM simulation is sufficient for credible design-stage energy prediction after a one-time machine characterization.
3. Run-to-run variability is structured by operation type, not random, so LCI replication requirements can be prescribed per operation category.
4. Aggregated single-value LCI factors mask real within-product variation in specific energy, demonstrated entirely with your own measured data (body vs lid energy per kg removed), with no external multiplier claims needed.

---

## 2. Prioritized new contributions

### Tier A: do these (core of the journal delta)

**A1. Estimation-fidelity ladder: quantified error of simplified energy estimation methods**
*Effort: 2 to 3 days. Highest impact per hour of work.*

Compare five estimation approaches against your operation-level measured ground truth, for both the CNC parts and the AM parts:

| Level | Estimator | Data required |
|---|---|---|
| L0 | Rated (nameplate) power × cycle time | Machine spec plate |
| L1 | Characterized average power × cycle time | One-time metering campaign (your 1,376 W) |
| L2 | Specific energy (kWh/kg removed) × mass removed | Literature SEC values (Kara and Li; Gutowski) |
| L3 | Program-level metering | Power meter, no UUID |
| L4 | Operation-level UUID attribution | Full method (ground truth) |

Computation needed: almost none beyond arithmetic you can do from existing tables. L0 uses the Hurco VMX30Ui 18 hp (13.4 kW) spindle rating (verify against the electrical plate on the machine; total connected load including auxiliaries will be higher and makes the point stronger; report both spindle-rating and connected-load variants if you can read the plate). L0 for AM uses the Ultimaker 2+ Extended rated 221 W against your measured roughly 200 W draw. L2 uses mass removed (1,437 g body, 448 g lid; verify against your stock and finished masses) with published SEC values.

Expected headline numbers (verify before quoting): CNC L0 overestimates by roughly 10x on spindle rating alone; AM L0 is within about 10 percent. That contrast is the generalizable finding: the validity of the duration-times-rating shortcut is machine-class dependent, governed by the ratio of average draw to rated power (a utilization factor you can define formally).

Deliverables into the paper: one new table (estimated vs measured energy and signed percent error per part per level), one short subsection in Results, two paragraphs in Discussion. Optionally a small bar chart of percent error by level.

**A2. Design-stage energy prediction from CAM cycle time**
*Effort: 1 day if NX-estimated cycle times are retrievable from your CAM files; skip if they are not.*

Figure 4's origin-forced regression (slope 1,376 W) already shows energy is essentially linear in duration. Close the loop: take the **CAM-predicted** cycle times from NX (not measured durations), multiply by the characterized average power, and compare predicted program energy to measured. If prediction error is within roughly 10 to 15 percent, you have a design-stage tool: an engineer comparing two toolpath strategies or two part geometries can rank their energy footprint inside CAM, before cutting metal, using one constant from a one-time metering campaign.

This is the contribution that speaks directly to the JMD half of the special issue (sustainable design optimization, AI-driven methods and digital tools for sustainability). It is also a clean validation experiment with zero new data collection.

Deliverable: one table (NX-predicted time, predicted energy, measured energy, error per program), one Results subsection, one Discussion paragraph.

**A3. Replication requirements for statistically valid LCI data**
*Effort: half a day. Pure arithmetic on existing CVs.*

For each operation category, compute the number of replicate runs needed to estimate mean energy within a relative margin r at 95 percent confidence: n = (1.96 × CV / r)^2. Present a small table at r = 5% and r = 10% by operation category (finishing, cavity milling, drilling, spotting/tapping, AM prints). Expected pattern: finishing and sustained milling need 2 to 4 runs; spotting and short drilling need 15 or more at the 5 percent margin.

This turns your variability section from a descriptive observation into prescriptive methodology that any practitioner building primary LCI data can apply. It also retroactively justifies your own 16 to 27 run sample sizes.

### Tier B: strong additions if Tier A finishes early

**B1. Uncertainty propagation to the product footprint**
*Effort: 1 to 2 days.*

Since 40 of 45 operations pass Shapiro-Wilk, propagate operation-level variance analytically (variance of a sum of independent operations) up to program, part, and product level, and report the manufacturing carbon contribution as a mean with a 95 percent confidence interval instead of a point value. A simple Monte Carlo (sampling each operation from its fitted distribution) is an easy robustness check and one extra figure if you want it. Tie to ISO 14067's expectation that footprint studies address uncertainty. The punchline writes itself: even the materials-dominated total footprint can now carry a defensible interval on its manufacturing component, which database-only studies cannot produce.

**B2. Fixed vs variable power decomposition**
*Effort: 1 to 2 days, only viable if you can pull idle-power segments from the raw 1 Hz data.*

Decompose each operation's energy into baseline (machine on, spindle idle) and cutting components, following the Gutowski framing that fixed auxiliary loads dominate machine tool energy. You already quantified homing at 11.7 percent of CNC energy; extending to a full fixed/variable split connects your measurements to the most-cited theory in the field and explains *why* the utilization factor in A1 is so low. If raw data access is awkward during conference week, drop this one.

### Tier C: include only as text, no new analysis

**C1. Within-product specific energy spread.** Compute energy per kg removed separately for body and lid from numbers already in the paper. Body comes to roughly 0.36 kWh/kg and lid roughly 0.78 kWh/kg (verify; lid energy can be derived from the 67.7 percent ratio and the 0.859 kWh CNC total). Same machine, same material, same product, and the per-kg energy differs by about 2x because of the lid's deep pocketing. This demonstrates the aggregation-masking argument entirely from your own measurements. Important: keep this purely as a measured within-product spread. Do not attach any multiplier claim against ecoinvent's value; the thesis position is that aggregation masks variation, not that a specific deviation factor exists.

**C2. Regulatory motivation (CBAM/CSRD).** Already drafted in the merge worksheet; one sentence in the introduction. Strengthens the "why now" for primary, product-specific data.

### Future work only (do not analyze, one sentence each)

- Carbon-aware scheduling (keep as separate forthcoming work per the merge worksheet warning).
- Machine learning on the UUID-labeled dataset: your operation-labeled energy corpus is exactly the training data the Brillinger/Xu line of work lacks; note that attribution and prediction are complementary, with UUID data able to serve as labeled ground truth for predictive models.
- Multi-machine transfer of the utilization factor and average-power constant (does the one-time characterization in A2 hold across machine sizes and controllers?).
- Tool wear as an explanatory variable for the drilling/spotting variability.

---

## 3. Drop-in draft text

All text below avoids claims you have not verified. Numbers in [brackets] need to be computed or confirmed before submission.

### 3.1 New Results subsection: "Accuracy of Simplified Energy Estimation Methods" (item A1)

> In the absence of metering infrastructure, practitioners commonly estimate manufacturing energy by multiplying machine cycle time by a representative power value, often the rated power from the machine specification. The operation-level measurements collected here permit direct quantification of the error introduced by this and other simplified approaches. Five estimation levels were evaluated against measured operation-level energy: (L0) rated power multiplied by cycle time, (L1) characterized machine-average power multiplied by cycle time, (L2) published specific energy consumption multiplied by mass removed, (L3) program-level metering without operation attribution, and (L4) the operation-level UUID attribution presented in this work.
>
> For the CNC machining center, the 13.4 kW rated spindle power [verify against electrical plate; report connected load if available] overestimates measured energy by approximately [X]x, because the machine drew an average of 1,376 W across all operations, a utilization factor of [1376/13400 = 0.10] relative to spindle rating. For the desktop FDM printer, by contrast, the 221 W rated power approximates the measured draw of approximately 200 W within [10] percent, because nearly all consumption is resistive heating that operates close to rating. The validity of the rated-power shortcut is therefore machine-class dependent: it is approximately correct for heater-dominated processes and produces order-of-magnitude error for machining centers, where installed spindle and axis capacity greatly exceeds typical engagement loads. Characterized average power (L1) reduced program-level error to [X] percent, indicating that a one-time metering campaign to establish a machine's average operating power recovers most of the accuracy of continuous metering at the program level, though it cannot resolve operation hotspots or run-to-run variability.

### 3.2 New Results subsection: "Design-Stage Energy Prediction from CAM Cycle Time" (item A2)

> The strong linear relationship between operation duration and energy (Figure 4, slope 1,376 W) suggests that energy can be predicted before production from information already available in the CAM environment. To test this, CAM-estimated cycle times generated by Siemens NX during toolpath verification were multiplied by the characterized average power and compared against measured program energy. Predicted energy agreed with measurements within [X] percent across all six CNC programs [verify]. This enables a design-stage workflow in which alternative toolpath strategies, feature geometries, or stock selections are compared on predicted energy inside the CAM environment, using a single machine constant obtained from a one-time metering campaign. Because CAM cycle-time estimates are routinely generated during process planning, this prediction step adds no engineering effort.

### 3.3 New Results paragraph: replication requirements (item A3)

> The structured nature of run-to-run variability permits prescriptive guidance on replication for primary data collection. For an operation with coefficient of variation CV, the number of replicate runs required to estimate mean energy within a relative margin r at 95 percent confidence is n = (1.96 CV / r)^2. Applying this to the measured operation categories, finishing and sustained milling operations (CV below 5 percent) require [2 to 4] runs for a 5 percent margin, while spotting and short drilling operations (CV near 20 percent) require [n approximately 60 at 5 percent, or 15 at 10 percent; compute from your actual CVs]. Practitioners constructing operation-level inventories can therefore concentrate replication effort on short, transient-dominated operations while characterizing sustained operations with minimal repetition. Because such operations also contribute the least absolute energy, a margin of 10 percent is typically sufficient for them without affecting part-level totals.

### 3.4 Discussion paragraph: within-product specific energy (item C1)

> Aggregation also masks variation within a single product. Normalizing measured machining energy by mass removed yields approximately [0.36] kWh/kg for the body and [0.78] kWh/kg for the lid [verify both], a difference of roughly [2]x for the same machine, material, and operator. The lid's deep pocketing features require longer engagement per unit of removed material than the body's bulk cavity removal. A single per-kilogram impact factor, however well characterized, cannot represent both components simultaneously, which illustrates the structural limitation of mass-normalized database factors for products whose features differ in machining character.

### 3.5 Discussion paragraph: uncertainty reporting (item B1, if done)

> Because [40 of 45] operations exhibited energy distributions consistent with normality, operation-level variances were propagated to part and product level to express the manufacturing carbon contribution as [mean ± 95 percent CI]. Reporting footprints as intervals rather than point values aligns environmental claims with the statistical reality of production and is consistent with the treatment of uncertainty expected under ISO 14067. Database-derived footprints cannot produce such intervals because the underlying datasets do not retain run-level variation.

---

## 4. Revised journal structure

1. **Introduction.** Conference intro plus the Schmitt LCI-scatter sentence and CBAM/CSRD sentence from the merge worksheet. Add one sentence trailing the contribution list: the paper now also quantifies the error of simplified estimation approaches and demonstrates design-stage prediction.
2. **Related Work** (new section). Chapter 2 §2.1 transplant per the merge worksheet (ML prediction paragraph, monitoring paragraph with Lee and Lee, Brundage, FDM variability). Add two to three sentences positioning against the SEC modeling line (Gutowski; Kara and Li; Balogun and Mativenga): those works predict energy from process parameters or empirical models, while this work measures and attributes it, and Section [A1] quantifies how much accuracy each approach sacrifices. This makes Related Work set up a Results section instead of just listing literature, which reviewers reward.
3. **Materials and Methods.** As merged (active/reactive power, cross-validation, UUID scaling, Tables 2-1 and 2-2). Add a short subsection defining the estimation levels L0 to L4 and the utilization factor, plus the replication formula. If doing A2, one paragraph on extracting NX cycle-time estimates.
4. **Results.**
   - 4.1 Operation-level attribution and hotspots (existing, plus duration-energy regression text from worksheet; finish the FINISH THIS SECTION stub with the Figure 4 slope interpretation already drafted in the worksheet).
   - 4.2 Run-to-run variability (existing, plus normality and complexity-vs-variability text, plus the replication-requirements paragraph, A3).
   - 4.3 Accuracy of simplified estimation methods (new, A1).
   - 4.4 Design-stage prediction from CAM cycle time (new, A2).
   - 4.5 Total manufacturing energy (existing, plus Table 2-6 and homing quantification).
   - 4.6 Carbon footprint (existing, plus uncertainty interval if B1 is done).
5. **Discussion.** Existing implications section, plus: material decarbonization argument (worksheet, with the scheduling phrase dropped), within-product specific energy (C1), utilization-factor generalization, limitations block from the worksheet.
6. **Future Work.** Trim to the four one-sentence items listed above.
7. **Conclusion.** Add one sentence each for the A1 and A2 findings; these become the second and third headline results after the variability finding.

Length check: the conference paper plus the worksheet transplants plus A1 to A3 should land around 9,000 to 11,000 words with 3 new tables and optionally 1 new figure, which is normal JMSE research-paper territory.

---

## 5. New references to add (beyond the merge worksheet list)

- Gutowski, T., Dahmus, J., and Thiriez, A., 2006, "Electrical Energy Requirements for Manufacturing Processes," Proc. 13th CIRP Int. Conf. on Life Cycle Engineering, Leuven. (Fixed/variable framing; utilization argument.)
- Kara, S., and Li, W., 2011, "Unit Process Energy Consumption Models for Material Removal Processes," CIRP Annals, 60(1), pp. 37-40. DOI 10.1016/j.cirp.2011.03.018. (SEC estimator for L2.)
- Balogun, V. A., and Mativenga, P. T., 2013, "Modelling of Direct Energy Requirements in Mechanical Machining Processes," J. Cleaner Prod., 41, pp. 179-186. (Improved state-based energy model; cite alongside Gutowski.)
- Kellens, K., Dewulf, W., Overcash, M., Hauschild, M. Z., and Duflou, J. R., 2012, "Methodology for Systematic Analysis and Improvement of Manufacturing Unit Process Life-Cycle Inventory (UPLCI) CO2PE!," Int. J. Life Cycle Assess., 17(1), pp. 69-78. (The standard methodology your work operationalizes and automates; reviewers in this space expect it.)
- ISO 14067:2018, Greenhouse Gases, Carbon Footprint of Products. (For the uncertainty-reporting paragraph if B1 is done.)
- Hurco Companies, machine specification for VMX30Ui (18 hp / 13.4 kW spindle, 12,000 rpm). Cite the official brochure or manual, and verify the figure against the machine's electrical plate at IN-MaC.

Verify the three "finalize from identifier" references in the merge worksheet (r3DiM, turbine-blade LCA, wire arc) the same week.

---

## 6. Timeline to June 30

- **June 10 to 13 (before MSEC):** Finish merge-worksheet transplants and the four WARNING reconciliations (45 vs 49 operations, lid mass basis, Table 2.5 cross-reference, scheduling phrase). Pull NX cycle-time estimates and photograph the Hurco electrical plate while you are physically near the machine, since A1 and A2 die without those two inputs.
- **June 14 to 18 (MSEC):** No writing. One useful task: the special-issue guest editors include Karl Haapala and people active in the LCE track; if any are at MSEC, a two-minute conversation about the planned extension is worth more than a day of writing.
- **June 19 to 23:** A1 analysis and text, A3 table and text. Resolve remaining reference identifiers.
- **June 24 to 26:** A2 if cycle times came through; otherwise B1. Draft Related Work positioning sentences.
- **June 27 to 29:** Full integration pass, conclusion rewrite, ASME formatting, co-author review window (give Liddell and Hartman the draft by the 26th at the latest).
- **June 30:** Submit via ASME Journal Tool, selecting JMSE and the Series 2 special issue.

## 7. Inputs checklist (things only you can get)

1. Photo of the Hurco VMX30Ui electrical/spec plate (rated spindle kW and total connected load).
2. NX CAM-estimated cycle times for all six programs.
3. Confirmation of mass-removed values per part (stock minus finished, per the mass-basis reconciliation).
4. The 45 vs 49 operation count reconciliation, since A3's table inherits whichever is correct.
5. Raw idle/baseline power segments, only if attempting B2.
