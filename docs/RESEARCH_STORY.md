# Research Story

This repository investigates how manufacturing sustainability decisions change when machine energy, grid emissions timing, CAD-feature energy estimates, and life-cycle assessment are connected instead of studied in isolation.

## Plain-language contribution

The central idea is: **manufacturing energy is not equally carbon-intensive at every hour or in every grid region.** If a manufacturing job has scheduling flexibility, WattTime grid-emissions signals can help identify lower-impact windows. Machine-specific energy measurements and CAD-feature estimates then connect those timing decisions to actual parts and processes, while OpenLCA provides the broader life-cycle context for an oil-pump case study.

## Research threads

1. **WattTime scheduling analysis**
   - Uses marginal/average/health-damage grid signals to evaluate time-shifting manufacturing jobs.
   - Produces Chapter 3-style summaries, heuristics, and supplemental analyses.
2. **Machine-specific energy analysis**
   - Uses CNC and additive manufacturing energy traces to estimate process/program/feature energy.
   - Provides measured inputs for feature libraries and LCA updates.
3. **OpenNX feature-energy estimation**
   - Extracts CAD/manufacturing features from Siemens NX parts.
   - Looks up feature energy values to estimate energy earlier in design.
4. **OpenLCA oil-pump modeling**
   - Pushes updated process energy values into OpenLCA and queries LCIA outputs.
   - Includes both direct automation scripts and an MCP/agent prototype.

## System flow

```text
Measured machine data ─┐
                       ├─> feature/process energy ─┐
CAD/NX part features ──┘                            ├─> oil-pump sustainability interpretation
                                                    │
WattTime grid signals ──> carbon-aware scheduling ──┘
                                                    │
OpenLCA model/results ──────────────────────────────┘
```

## What is strongest today

- The WattTime analysis folder has the deepest workflow and existing handoff guide.
- The OpenLCA MCP prototype has a clear README and some tests.
- The OpenNX feature-library draft is a strong future-work bridge from CAD to energy estimation.

## What still needs polish

- Finalize canonical script names and archive older exploratory variants.
- Add figure/table traceability for thesis or publication outputs.
- Add sample data and smoke tests so someone can run a small workflow without private data.
- Document data availability and licensing boundaries.
