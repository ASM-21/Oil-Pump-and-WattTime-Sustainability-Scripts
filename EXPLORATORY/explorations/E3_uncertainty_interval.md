# E3: Uncertainty propagation to the product footprint

**Direction:** Is the propagated manufacturing carbon uncertainty interval large enough
to be interesting, or so small it is a footnote?

**Cost tag:** [light analysis]

## What was checked

The paper reports 40 of 45 operations near-normal (Shapiro-Wilk). For independent
normal random variables, variance of the sum = sum of variances. So the program-level
energy distribution is approximately normal with:

  mean = sum(mean_i over operations)
  var  = sum(var_i over operations)

Quick estimate from expected data structure:
- Body has ~4 programs, each with ~8-10 distinct operations
- Finishing operations: CV ~ 2-3%, contributing ~30% of energy
- Cavity milling (large): CV ~ 5-10%
- Spotting/drilling (small energy, high CV ~ 15-25%): contribute little total energy

Expected CV at program level: dominated by the large-energy operations.
Cavity milling at CV~8%, energy ~40% of program -> contributes 0.4 * 8% = 3.2% to program CV.
Finishing at CV~3%, energy ~30% of program -> contributes 0.3 * 3% = 0.9%.
All others similar: total program CV likely 3-6%.

At 95% CI: interval width ~ 2 * 1.96 * 5% * mean ~ +/-10% of program energy.
For a program energy of ~0.2 kWh per program: interval ~ +/-0.02 kWh.

At part level (sum across programs): CV shrinks further if programs are independent.
For the body total (~0.86 kWh): if 4 programs each 5% CV and similar energy,
  combined CV ~ 5% / sqrt(4) ~ 2.5%
  95% CI: +/-5% of 0.86 kWh ~ +/-0.043 kWh

At product footprint level (manufacturing ~2% of total):
  The manufacturing CI in CO2e units = 0.043 kWh * 0.4 kg CO2e/kWh ~ 0.017 kg CO2e
  Total footprint ~30 kg CO2e (material dominated)
  This CI represents <0.1% of total footprint -> nearly invisible at product level.

BUT if the paper reports the manufacturing component specifically (as it should), then
"+/-5% of 0.86 kWh CNC machining energy" is a meaningful, reportable interval that
database-only LCI cannot produce. The ISO 14067 alignment is real.

## Verdict

**Worth doing as a quick computation.** The interval is meaningful for the
manufacturing component specifically, even if invisible at product level. The
framing is: "we can report it as an interval, which database-only studies cannot."
This is a positioning claim, not a large-effect finding -- which is fine.

A Monte Carlo cross-check (sample each operation from its fitted distribution N=10000
times) would take ~30 minutes to implement and provides a robustness check on the
analytic propagation. The estimation_ladder project already computes the per-operation
CV, so the inputs are ready.

## What to build

No separate project needed for the paper. Implement as a short computation at the
bottom of the estimation_ladder run.py or as a standalone script once estimation_ladder
is working. The inputs are:
- Per-operation mean_wh and std_wh (from op_stats in estimation_ladder)
- Program structure (which operations belong to which program)

Then:
  std_program = sqrt(sum(std_i^2 for ops in program))
  CI_95 = 1.96 * std_program

Report as: "CNC machining energy for the body = [mean] +/- [CI_95] Wh (95% CI,
n=[runs], [k] of [N] operations near-normal)"

## What it feeds

- Results section 4.6 if you implement B1 (uncertainty propagation)
- The ISO 14067 paragraph in Discussion (already drafted in SCOPE_tier_A_B_C.md 3.5)
