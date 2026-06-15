# Triage: what needs code, what is just argument, and what actually makes this a journal paper

## Bottom line

The conference paper proved a system works. A journal paper needs a *generalizable claim* the system reveals. Almost every claim that does that work here is provable from numbers already in the paper, by arithmetic, and belongs in the Discussion as reasoning. The code projects mostly add supporting rigor to claims you can already make. Two of them earn their keep with a real figure. The rest are future work. Treating all eight as equal builds is the mistake to avoid before June 30.

So the priority is inverted from the agent brief: write the principles first, then add the two analyses that give them teeth, then stop.

---

## The generalizable claims, and whether they need code

A claim "needs code" only if a skeptical reviewer would not accept the number without seeing the computation. By that test:

| Claim | Needs code? | Why |
|---|---|---|
| Rated-power shortcut overestimates CNC energy ~10x | No | 1,376 W measured / ~13,400 W rated = 0.10. Two numbers you have. |
| Same shortcut is near-correct for FDM | No | ~200 W measured / 221 W rated ≈ 0.9. Two numbers. |
| Utilization factor is the predictor of shortcut error | No (framing) | It is a definition (mean/rated) plus the two points above. The contribution is naming and generalizing it, not computing it. |
| Mass-based allocation misassigns body vs lid energy | No | Lid is much lighter yet uses 67.7% of body energy. Already in the paper. |
| Aggregation masks within-product specific-energy variation | No | Body vs lid energy-per-kg-removed, both derivable from existing numbers. |
| Average power is a stable per-machine constant | Mostly no | The tight clustering and 1,376 W slope are already shown in Figure 4. |
| Replication needed scales with operation CV | Barely | n = (1.96·CV/r)^2 is one formula applied to CVs you already report. |
| Allocation *rule-by-rule* error, swept across product mixes | Yes | The sweep and the worst-case-error figure are genuinely new computation. |
| Estimation error *per level, per part*, as a clean ladder figure | Yes | The L0 to L4 table and bar chart are new artifacts a reviewer will want to see. |
| Tool wear shows up as run-order energy drift | Yes | Cannot be argued; the regression either finds a trend or does not. |

Read the table top to bottom: the claims that carry the paper sit in the "No" rows. That is the point. The journal contribution is intellectual framing of measured facts, and the facts are in hand.

---

## What is actually key for a journal-level new direction

Three things, in order. Only the first is truly novel; the other two are strong.

**1. The utilization factor as a machine-class invariant (the centerpiece).**
Define u = mean operating power / rated power. Show u ≈ 0.10 for the machining center and u ≈ 0.9 for the FDM printer. The generalizable statement: the validity of the near-universal "rated power × cycle time" LCI shortcut is governed by u, a machine-class property, so the same estimation method is wrong by an order of magnitude for one class and essentially correct for another. This converts your original intuition (machines run well below rating) into a named, quantified, transferable concept that any practitioner can compute for their own equipment. It is the most citable idea in the paper and it needs no new data, only clean framing and a table. Everything else can orbit this.

**2. Allocation-rule error measured against sub-machine ground truth.**
Most allocation debate is theoretical because almost nobody has measured per-part energy to falsify a rule against. You do. The body/lid pair already shows mass-based allocation failing; the new direction is to quantify how wrong each common rule (mass, time, economic) is and where it breaks across product mixes. This is a methodological contribution that LCA reviewers value, and it diversifies the paper beyond "we measured stuff."

**3. Measurement-to-design and measurement-to-regulation bridges (positioning, not analysis).**
Average power as a design-stage constant (predict energy from CAM cycle time), and the fit of UUID-per-unit data to emerging product-passport and primary-data-share requirements. These are what make a JMD/JMSE joint-issue reviewer see design-manufacturing relevance. They are paragraphs, not projects. They widen the paper's horizon at near-zero cost and signal that the work points somewhere.

What is *not* a key new direction for this paper, despite being interesting: energy disaggregation (a whole separate ML paper), emission-factor temporal sensitivity (orthogonal, brushes the scheduling boundary you are keeping separate), feature-energy prediction with two parts (too thin to validate), and the dataset release (permission-gated, future). All belong in Future Work as one sentence each, not in the June 30 build.

---

## Revised scope for the agent

Cut the agent's job to what genuinely needs computation, and let the rest be writing.

**Build (code, for the paper):**
- `estimation_ladder/` — the one indispensable analysis. Produces the L0 to L4 error table, the utilization factors, the bar figure, and the replication table. This is the empirical body behind key direction 1.
- `allocation/` — the rule-error table and the mix-sweep figure. Empirical body behind key direction 2.

**Build only if time remains after the above and the manuscript draft:**
- `wear_runorder/` — cheap, but it is a limitations-section strengthener, not a contribution. A null result is fine and likely.

**Do not build for this paper (convert each to one Future Work sentence):**
- `disaggregation/`, `emission_factors/`, `feature_energy/`, `dataset_card/`, most of `schemas/`. Keep only the schemas *positioning table* (PACT/DPP field mapping) as a short Discussion exhibit if you want the regulatory bridge to feel concrete, and even that is optional.

**Compute directly, no project needed (verify-and-state):**
- The utilization factors (two divisions), the body/lid energy-per-kg-removed (already derivable), and the replication numbers (one formula). A skeptical co-author can check these by hand. Put them straight into Discussion. The `estimation_ladder/` build will reproduce them anyway as a byproduct, which doubles as the verification.

Net effect: the agent builds two focused analyses instead of eight, each tied to a claim the paper actually makes, and the paper's intellectual weight comes from framing you write rather than code you wait on.

---

## One caution on the "obvious" claims

Obvious-by-arithmetic does not mean it skips verification. The two-number calculations rest on inputs that must be right: the rated spindle power (confirm against the machine's electrical plate, and decide spindle-rating vs total connected load, since that choice moves the 10x figure), the measured average power (confirm 1,376 W against the data rather than the slide), and the mass basis for body/lid (stock vs finished, the inconsistency already flagged in your merge worksheet). The arithmetic is trivial; the inputs are where a reviewer could catch you. That is exactly what the `estimation_ladder/` dual-path check is for, which is why it stays a build even though the headline is "obvious."
