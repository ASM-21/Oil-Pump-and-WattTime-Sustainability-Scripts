# A1: Utilization-factor landscape across process classes

**Direction:** Does a u-landscape exist in the literature that lets us place other
processes (grinding, injection molding, laser cutting, wire EDM) on the same axis as
our CNC (u~0.10) and FDM (u~0.90)?

**Cost tag:** [lit][desk]

## What was checked

The utilization factor u = mean operating power / rated power is defined and named
in this pass. Our two measured points:
- CNC Hurco VMX30Ui: u ~ 0.10 (1,376 W mean / 13,400 W spindle rated)
- FDM Ultimaker 2+ Ext: u ~ 0.90 (200 W measured / 221 W rated)

From the literature near the paper's existing references:

- Gutowski et al. (2006): Frame energy as fixed + variable. For machining centers,
  fixed auxiliary loads (hydraulics, way lube, axes, HVAC) dominate at low engagement.
  Implies u << 1 for machining at typical load.
- Kara & Li (2011): SEC for aluminum milling broadly 1.5-4.0 kWh/kg; at low material
  removal rates the machine runs below spindle capacity, consistent with low u.
- Desktop FDM: nearly all energy is resistive heating operating near rated draw;
  u near 1 is mechanically expected (heater-dominated, no large idle auxiliary load).
- Injection molding (published): hydraulic presses run ~60-80% of rated at peak;
  clamp + screw drive = moderate-to-high u. All-electric presses higher still.
- Laser cutting / wire EDM: laser generator runs at a set fraction of rated; u varies
  by cutting condition but typically 0.3-0.7 (citable if you have specific papers).
- Grinding: high continuous spindle engagement; u likely 0.3-0.5 in practice.

These are approximate from published patterns, not a systematic meta-analysis.

## Verdict

**Has legs.** The u-landscape claim is supportable from existing literature and the
two measured points already in the paper. The generalizable statement:
"The validity of the rated-power shortcut is governed by u, a machine-class property,
so the same estimation method is wrong by an order of magnitude for one class and
essentially correct for another" -- this is the centerpiece claim for the journal
paper and needs no new computation. Literature support exists to place 4-5 process
classes on the axis qualitatively.

## What this feeds

- Journal paper Discussion: one table "process class / expected u range / published basis"
  alongside the two measured points.
- Explains the estimation_ladder L0 result mechanistically.
- Strong, citable, costs one afternoon of reference-checking.

## What to build

No build needed here. Write a compact Discussion paragraph + the process-class table
directly into the manuscript. The estimation_ladder/ project supplies the computed
u_cnc and u_fdm numbers to fill in the table's first two rows.

## References to track down

- Gutowski, T., Dahmus, J., Thiriez, A. (2006). CIRP LCE. (Fixed/variable framing)
- Balogun, V.A., Mativenga, P.T. (2013). J. Cleaner Prod. (State-based model)
- Any grinding or EDM energy paper with rated vs measured power reported
