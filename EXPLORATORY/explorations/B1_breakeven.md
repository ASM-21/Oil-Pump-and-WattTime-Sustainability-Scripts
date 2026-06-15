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
