# Paper goal and journal fit

## What this is
The repo owner is expanding ASME MSEC 2026 paper MSEC2026-182984 ("From Cam to Carbon: Operation-Level Energy Monitoring for Automated Product-Level Carbon and Energy Footprinting") into a journal article for the **JMD/JMSE Joint Special Issue on Advances in Design and Manufacturing for Sustainability (Series 2)**. Submission deadline **June 30, 2026** (extended). Initial review by Aug 1, 2026; publication Jan 2027.

## The intellectual move from conference to journal
The conference paper proved a measurement system works. The journal version needs **generalizable claims** that the measurement reveals. The repo agent's job is to help find and substantiate those claims by exploring the directions in `context/EXPANSION_DIRECTIONS.md`, not to bulk up the paper with undirected analysis.

## What the method does (one paragraph)
A UUID-based scheme assigns identity at the operation, program, and part level, originating in CAM and surviving into production. Power is metered at 1 Hz (IAMMETER on a Hurco CNC; monitoring on Ultimaker/Stratasys FDM). Energy is attributed to individual operations per run, replicated 16 to 27 times per program, and rolled up to a product carbon footprint. Case study: an oil pump assembly (body, lid, AM components) at IN-MaC.

## The paper's current headline findings (to build on, not re-prove)
- Materials dominate the product footprint (~98%, aluminum-heavy); manufacturing energy is small (~2%).
- Operation energy is highly concentrated (two cavity-milling operations carry over half a program's energy).
- Run-to-run variability is structured by operation type, not random (finishing low CV, spotting/tapping high CV).
- Average operating power is a stable per-machine constant (regression slope ~1,376 W with tight clustering).

## The journal fit
This is a joint **design + manufacturing** issue. Directions that connect measurement to the **design stage** (feature energy, CAM-time prediction) and to **external data demands** (product passports, primary-data-share frameworks) are what make it fit the joint scope, alongside the core manufacturing-measurement contribution.

## Hard constraint
**No new experimental data is possible.** The owner has graduated and is not physically at the lab. Everything must come from data already in this repo. A collaborator might do a small favor, but nothing should depend on it. See `context/GROUND_TRUTH.md`.
