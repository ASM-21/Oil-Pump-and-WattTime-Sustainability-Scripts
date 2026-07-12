# B1_breakeven: findings

**Status:** explored
**Date:** 2026-06-21

## Headline
The 'materials dominate' conclusion (~98% of footprint) is conditional on aluminum
source. At virgin aluminum (global average ~12 kg CO2e/kg) and Indiana grid
(0.45 kg CO2e/kWh), manufacturing is ~1.7% of total footprint. At secondary (recycled) aluminum (~0.5 kg CO2e/kg), manufacturing
can exceed 20%. This converts the paper's limitation into a forward argument:
decarbonizing aluminum is exactly what makes operation-level monitoring start to matter.

## Numbers

### Manufacturing share by aluminum scenario (Indiana grid fixed)
| Scenario | CF (kg CO2e/kg) | E_mat | E_mfg | Mfg share |
|---|---|---|---|---|
| Virgin (global avg) | 12.0 | 37.32 | 0.6485 | 1.71% |
| Virgin (low-carbon smelter) | 4.0 | 12.44 | 0.6485 | 4.95% |
| 50% recycled mix | 6.5 | 20.21 | 0.6485 | 3.11% |
| Recycled (secondary) | 0.5 | 1.55 | 0.6485 | 29.43% |

### Break-even thresholds (at what CF_al does manufacturing reach threshold?)
| Threshold | CF_al at break-even | Note |
|---|---|---|
| 5% | 3.96 kg CO2e/kg | Manufacturing reaches 5% of total footprint when aluminum CF... |
| 10% | 1.88 kg CO2e/kg | Manufacturing reaches 10% of total footprint when aluminum C... |
| 20% | 0.83 kg CO2e/kg | Manufacturing reaches 20% of total footprint when aluminum C... |

## Verification

| quantity | path A | path B | rel diff % | tol % | verdict | note |
|---|---|---|---|---|---|---|
| [vs quoted] manufacturing share at virgin aluminum + Indiana grid | 1.71 | 2 | 14.5 | 50.0 | AGREE | paper quotes ~2%; 50% tol because energy and mass values are estimates |


NOTE: Total energy values are context doc estimates. Update TOTAL_ENERGY_WH from estimation_ladder/outputs/summary_by_part.csv after running that project.

NOTE: Stock masses are estimates (body 2500 g, lid 610 g). Update STOCK_MASS_G from bom.csv once verified.

## Caveats
- Total energy is summed across body and lid CNC machining only (AM parts excluded).
- Stock mass estimates are from context docs, not measured.
- Grid carbon intensity (Indiana/MISO) is an approximate annual average.
  Marginal/hourly intensity from WattTime MOER would sharpen this.
- This is a parametric exhibit, not a sensitivity analysis of measured uncertainty.

## Feeds the journal paper?
Yes -- strong Discussion paragraph. Converts the '98% materials' finding from a
limitation into a forward argument. Shows why the measurement capability this paper
establishes will matter more as aluminum decarbonizes. Produces a citable figure.

## How to extend
- Replace TOTAL_ENERGY_WH with verified values from estimation_ladder.
- Replace STOCK_MASS_G with values from bom.csv.
- Replace INDIANA_GRID_CI with MOER-derived marginal intensity once available.
