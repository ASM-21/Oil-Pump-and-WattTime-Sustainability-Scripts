# B1: When does manufacturing energy stop being negligible?

**Direction:** Under what conditions does the manufacturing energy contribution
flip from ~2% of the product footprint toward something that actually matters
for design or sourcing decisions?

**Cost tag:** [light analysis]

## What was checked

The paper reports materials ~98%, manufacturing ~2%. The strongest journal move
is to interrogate this conclusion: under what conditions does it break?

Key levers (arithmetic from existing numbers):
- The total product footprint is dominated by aluminum embodied carbon.
- The footprint is approximately: F = E_materials + E_manufacturing
  where E_materials depends on aluminum source and E_manufacturing is fixed from data.
- Manufacturing's share = E_manuf / (E_mat + E_manuf)

For the manufacturing share to reach, say, 10%:
  E_mat must fall to 9 * E_manuf

Parametric sweep:
1. Aluminum embodied carbon: virgin ~12 kg CO2e/kg, recycled ~0.5 kg CO2e/kg,
   low-carbon smelter ~4 kg CO2e/kg (approximate published values)
2. Grid carbon intensity: average US grid ~0.4 kg CO2e/kWh, wind/solar ~0.02

The oil pump body uses roughly 2.5 kg of aluminum stock (estimate; verify from BOM).
At virgin aluminum:  E_mat ~ 2.5 * 12 = 30 kg CO2e
Manufacturing CNC energy ~0.86 kWh * 0.4 kg CO2e/kWh ~ 0.34 kg CO2e
=> manufacturing share ~ 0.34 / (30 + 0.34) ~ 1.1%   [consistent with ~2%]

At recycled aluminum (0.5 kg CO2e/kg):  E_mat ~ 2.5 * 0.5 = 1.25 kg CO2e
=> manufacturing share ~ 0.34 / (1.25 + 0.34) ~ 21%   [FLIPS to significant]

With renewable grid (0.02 kg CO2e/kWh): E_manuf ~ 0.86 * 0.02 = 0.017 kg CO2e
Even with recycled Al: share ~ 1.3%  [goes down again]

## Update 2026-07-09: owner-verified masses computed

The owner verified the BOM (now committed as `EXPLORATORY/bom.csv`): body
stock 1880 g (not the 2500 g estimated above), lid stock 518 g. With the
context-doc energy totals (0.859 + 0.582 = 1.441 kWh CNC, still to be
confirmed by estimation_ladder) and the Indiana grid (0.45 kg CO2e/kWh),
the recomputed table (stdlib cross-computation; run B1_breakeven.py locally
to regenerate the CSVs and figures):

| Scenario | CF_al (kg CO2e/kg) | Mfg share |
|---|---|---|
| Virgin (global avg) | 12.0 | 2.20% |
| 50% recycled mix | 6.5 | 3.99% |
| Virgin (low-carbon smelter) | 4.0 | 6.33% |
| Recycled (secondary) | 0.5 | 35.10% |

Break-even: manufacturing reaches 5% at CF_al = 5.14, 10% at 2.43, and 20%
at 1.08 kg CO2e/kg. The verified stock masses are smaller than the old
estimates, which shrinks the materials term and STRENGTHENS the finding:
manufacturing now crosses 5% even for low-carbon-smelter virgin aluminum,
and the recycled scenario rises from ~29% to ~35%. The 2.20% baseline stays
consistent with the paper's ~2% quote.

## Update 2026-07-11: MEASURED energies (data now in repo)

The CNC measurement CSVs are committed (Al6061Body/, Al6061Lid/) and the
analyzer now integrates the cumulative forward-kWh register (exact, gap
immune). Register-based mean per-run totals (from
`EXPLORATORY/compare_outputs/compare_allocation.csv`): body 647.3 Wh, lid
364.0 Wh, total 1.011 kWh. These are LOWER than the old context-doc estimate
(1.441 kWh), so manufacturing shares drop slightly from the estimate above,
but the conditional-dominance finding holds. Measured lid/body energy ratio
is 0.562, not the quoted 0.677 (see allocation and _summary.md).

Recomputed at the Indiana grid (0.45 kg CO2e/kWh), stock masses 1880 / 518 g:

| Scenario | CF_al (kg CO2e/kg) | Mfg share |
|---|---|---|
| Virgin (global avg) | 12.0 | 1.56% |
| 50% recycled mix | 6.5 | 2.84% |
| Virgin (low-carbon smelter) | 4.0 | 4.53% |
| Recycled (secondary) | 0.5 | 27.51% |

Break-even: manufacturing reaches 5% at CF_al = 3.61, 10% at 1.71, and 20%
at 0.76 kg CO2e/kg. The 1.56% virgin baseline is consistent with the paper's
~2% quote; recycled aluminum still pushes manufacturing above 27%. B1_breakeven.py
now carries these measured values (ENERGY_VERIFIED = True); run it to
regenerate the CSVs and contour figure.

## Verdict

**Has legs.** The break-even arithmetic is simple and produces a clear and genuine
finding: the materials-dominate result is conditional on aluminum source. At recycled
aluminum, manufacturing crosses 10% even with average grid. This converts a paper
limitation into a forward argument: "decarbonizing aluminum is exactly what makes
the measurement capability this paper enables start to matter."

The result is reachable in a few hours of arithmetic and one figure (2D sweep over
aluminum carbon intensity vs grid intensity, with iso-share contours and our two
data points).

## What to build

This is the B1 [light analysis] item in EXPANSION_DIRECTIONS.md. No separate project
needed -- build it as a standalone script `explorations/B1_breakeven.py` or fold into
a manuscript exhibit. The inputs are:
- CNC total energy per part (from estimation_ladder output)
- Stock mass per part (from BOM, or estimated from context docs)
- Parametric ranges for aluminum CF and grid CI from published sources

## Key numbers to nail down first

1. Total CNC energy per body and lid from the estimation_ladder run.
2. Stock mass per part (needed here and for the allocation project).
3. Verify AM parts energy too (drive shaft), though body/lid dominate.

## References

- Embodied carbon of aluminum: IAI (International Aluminium Institute) data
- Low-carbon smelter aluminum: ~3-5 kg CO2e/kg (published range)
- IPCC grid emission factors or EIA average US grid intensity
