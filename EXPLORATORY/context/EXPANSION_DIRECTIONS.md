# Expansion Directions to Explore for the Journal Paper

These are candidate angles to investigate, not finished content and not a build list. Each entry: the angle, why it could strengthen the paper, what exploring it actually involves, and a cost tag. The cost tag is the code-vs-argument lens applied as triage, not as a reason to cut: **[desk]** = explorable by reasoning and existing numbers, **[light analysis]** = small computation on data in hand, **[agent build]** = a real analysis project, **[lit]** = needs a literature scan to position. Treat the whole list as a menu to explore and prune later, after seeing what is fertile.

The organizing idea: the conference paper measured one product well. The journal paper becomes interesting when it uses that measurement to say something general. Most directions below are different ways to reach for a general claim. Explore several, keep the two or three that turn out to have the most behind them.

---

## A. Directions that broaden the central claim (utilization factor)

**A1. A utilization-factor landscape across process classes. [lit][desk]**
You have two points (CNC u≈0.10, FDM u≈0.9). Explore whether published energy studies let you place a handful of other processes (grinding, injection molding, laser cutting, wire EDM) on the same axis, even roughly. If three or four more points exist in the literature, the two-point observation becomes a small landscape, and the claim sharpens from "these two machines differ" to "process classes occupy a predictable range of u, and the rated-power shortcut's error is a known function of where a process sits." That is a much more citable statement. Worth a few hours of searching before committing.

**A2. What drives u, mechanistically. [desk]**
Explore framing u as the ratio of productive cutting power to installed capacity, and why machining centers carry large idle and auxiliary loads (spindle ready, hydraulics, way lube, chip conveyor) while a printer is almost all productive heating. This connects directly to the Gutowski fixed-vs-variable framing already near your literature. The exploration is whether you can decompose your own measured energy into a fixed baseline and a variable cutting component, which would explain u from your data rather than asserting it. Tips into [agent build] only if you want the decomposition figure.

**A3. The shortcut as a correctable bias, not just an error. [desk]**
Explore reframing: instead of "rated-power estimates are wrong," ask whether a single measured u turns the cheap shortcut into a usable estimator (corrected estimate = rated × u × time). If u is stable for a machine, the shortcut plus one calibration number recovers most of the accuracy. That reframes the contribution from a criticism into a method practitioners can adopt, which reviewers like better than a takedown.

---

## B. Directions that stress-test the paper's own headline conclusion

**B1. When does manufacturing energy stop being negligible. [light analysis]**
The paper concludes materials dominate (~98%) and manufacturing is small (~2%). The strongest journal move is to interrogate your own headline: under what conditions does that flip toward mattering? Explore a parametric sweep over aluminum embodied-carbon (virgin vs recycled vs low-carbon-smelter) and grid carbon intensity, and find the break-even where manufacturing crosses, say, 10% of total. This is mostly arithmetic on your existing footprint numbers, and it produces a clean figure plus a genuinely useful claim: the materials-dominate result is conditional, and decarbonizing aluminum is exactly what makes the monitoring this paper enables start to matter. It turns a limitation into a forward argument.

**B2. Sensitivity to the functional unit and product type. [desk]**
Explore how much the materials-dominate conclusion depends on this being a chunky aluminum part with high buy-to-fly ratio. For a thin, low-mass, high-precision part with long machining time, the balance shifts. You cannot measure new parts, but you can reason about where on a mass-versus-machining-time map the conclusion inverts, and place your body and lid on that map. A qualitative map with your two points and reasoned regions is a legitimate Discussion exhibit.

---

## C. Directions that add a methodological "when to measure" layer

**C1. Value of information: when is operation-level resolution worth it. [desk][light analysis]**
Explore positioning the whole method against its own cost. Operation-level attribution is more work than program-level or database lookup. When does the extra granularity change a decision? Your data already shows where program-level metering hides the energy hotspots (the two cavity-milling operations dominating). Explore framing a decision-oriented claim: granularity matters when energy is concentrated in few operations or when those operations map to design choices, and matters little for uniform programs. This is a meta-contribution that reviewers read as maturity, and it costs reasoning plus a little computation on the concentration you already report.

**C2. Replication guidance as a reusable protocol. [light analysis]**
You already have the n=(1.96·CV/r)^2 idea. Explore elevating it from a number into a short protocol: how a practitioner building primary LCI data should budget replicate runs by operation type, with your CV-by-category data as the worked example. The exploration is whether your categories generalize enough to present as guidance rather than as a description of one machine. Cheap, and it gives the paper a transferable artifact.

---

## D. Directions that strengthen the design-side (JMD) relevance

**D1. Energy as a design-review signal. [desk]**
Explore the framing that operation energy maps back to features, and features are design decisions, so the data is design feedback. The lid's pocketing costing more per kg is the seed. The exploration is how far you can push "design-stage consequence" as a narrative without overclaiming on two parts. Likely a Discussion paragraph plus one conceptual figure (feature to operation to energy), not a validated tool.

**D2. Design-stage prediction from CAM cycle time. [agent build, if NX times exist]**
Explore whether CAM-estimated cycle times times the average-power constant predict measured program energy within useful bounds. If yes, that is a concrete design-stage tool and the most JMD-shaped result available. Whether it is explorable at all depends on whether NX retained cycle-time estimates in your files, so the first exploration is just checking that.

---

## E. Directions that connect to the external landscape (positioning)

**E1. Standards-operationalization map. [lit][desk]**
Explore which standards your method touches and where it could claim to operationalize rather than just cite: ISO 14955 (machine-tool energy), ISO 14067 (product carbon footprint, uncertainty), ISO 23247 (manufacturing digital twin), the UPLCI/CO2PE! methodology, and the Brundage reusable-LCI-data work already in your sights. A compact table of "standard / what it asks for / what this method supplies" is a strong positioning exhibit and pure desk work.

**E2. Regulatory data-demand map. [lit][desk]**
Explore the same move for regulation and consortia: CBAM and CSRD (already in the merge worksheet), Digital Product Passports under ESPR (aluminum enters 2027), and PACT/Catena-X primary-data-share scoring. The exploration is whether you can compute even one concrete number, the manufacturing-stage primary data share for the oil pump, to make the positioning tangible rather than hand-wavy.

**E3. Uncertainty as a first-class output. [light analysis]**
Explore propagating your per-operation distributions (40 of 45 near-normal) up to a product-footprint confidence interval, and taking the stance that manufacturing footprints should be reported as intervals, which database-only methods cannot do. The exploration is whether the propagated interval is large enough to be interesting or so small it is a footnote. Worth a quick computation to find out before deciding how much weight to give it.

---

## F. Directions kept explicitly as horizon (explore as framing, not as results)

These are real and worth naming so the paper points somewhere, but exploring them means writing them as future work, not producing results now: energy disaggregation using UUID labels as training data, emission-factor temporal sensitivity (kept distinct from scheduling), feature-energy prediction across more parts and machines, tool-wear as an explanatory variable, and dataset release for community benchmarking. Each is a candidate follow-on paper; for this submission, the exploration is deciding which two or three deserve a sentence that makes a reviewer think the work has a future.

---

## How to use this list

Pick the cheapest fertile ones first and see what is actually there before building anything. The [desk] and [light analysis] tags (A1, A2, A3, B1, C1, C2, E1, E2, E3) are explorable in an afternoon each and several may dead-end, which is fine and fast to discover. The [agent build] items (B1's figure, A2's decomposition, D2) are worth handing to the repo agent only once a desk pass shows the angle has legs. The goal of this pass is to find which generalizations have substance behind them, not to commit to any of them yet.

Strongest bets to explore first, on current evidence: A1 (does a u-landscape exist in the literature), B1 (the break-even that makes your own conclusion conditional), and E3 (whether the uncertainty interval is interesting). Those three could each become a distinct, general claim, and none requires new data.
