# Theory layer: the general results the case study instantiates

The conference paper measured one oil pump on one CNC and one FDM machine.
The journal version needs claims that hold beyond that bench. The existing
projects (estimation_ladder, allocation, wear_runorder) are empirical; this
folder holds the analytical results those experiments become instances of.
Every closed form below is validated two ways before it may appear in the
paper: against synthetic fixtures pushed through the real pipeline
(`shared/fixtures.py`), and against a stdlib-only brute-force simulation
(`selftest_stdlib.py`) that runs even where numpy is unavailable.

None of these projects park when measurement data is absent. The theory and
its fixture validation are complete now; the real data, when supplied via
`CNC_DATA_DIR`, only adds the empirical confirmation points.

## 1. `estimator_errors/` - when is an energy-estimation shortcut acceptable?

Let a machine have rated power `P_rated` and mean operating power `P_mean`,
and define utilization `u = P_mean / P_rated`.

- **L0 (rated-power estimate)** `E = P_rated * T` has exact relative bias
  `1/u - 1`. This is not an observation, it is an identity: the rated-power
  shortcut fails precisely as utilization falls. At the CNC's u of about
  0.10 the bias is +900 percent; at the FDM's u of about 0.90 it is +11
  percent, right at the edge of a 10 percent tolerance.
- **L1 (characterized mean power)** is unbiased with relative standard error
  `CV / sqrt(n)` after `n` replicate runs, giving the replication rule
  `n = (1.96 * CV / r)^2` for target precision `r`.
- **The regime map**: on the (u, CV) plane, L0 is acceptable only where
  `u >= 1/(1 + r)`, and elsewhere L1 requires the contoured `n`. Machine
  classes from the A1 landscape (CNC, FDM, injection molding, grinding,
  laser/EDM) land in visibly different regions, which is the design-stage
  takeaway: the right estimation shortcut is a property of the machine
  class, knowable before any meter is installed.

## 2. `allocation_theory/` - allocation error in closed form

Two co-products (body, lid) share a metered total. For per-unit true
energies with ratio `rho_E = e_lid / e_body`, an allocation attribute with
ratio `rho_x` (time, removed mass, finished mass/economic), and production
mix `phi = N_lid / N_body`, the body's relative allocation error is

    err_body = phi * (rho_E - rho_x) / (1 + phi * rho_x)

and the lid's follows by symmetry. Consequences the paper can state
generally: error vanishes only when the attribute is proportional to true
energy (`rho_x = rho_E`) or the mix is degenerate (`phi = 0`); error grows
monotonically with mix imbalance; and for same-material co-products,
economic allocation inherits mass allocation's error with the finished-mass
ratio in place of the removed-mass ratio. The measured body/lid pair supplies
`rho_E` and turns the surface into numbers.

## 3. `power_decomposition/` - why duration-based estimation works here

Write `P(t) = P0 + P_proc(t)` (fixed-plus-variable, per Gutowski and
Kara/Li). With per-operation load factor `lambda_i = mean(P_proc,i) / P0`,
operation energy is `E_i = P0 * T_i * (1 + lambda_i)`, so a duration-only
model with the fleet-average power has per-operation relative error

    err_i = (lambda_bar - lambda_i) / (1 + lambda_i)

bounded by the machine's process-power heterogeneity. A base-load-dominated
machine (small lambda across operations) is exactly a machine where the
stable average-power constant (the ~1,376 W regression slope, to be
recomputed from data) makes L1 accurate. This wires the estimation ladder
into established machining-energy theory and yields the literature SEC
benchmark table the Discussion needs.

## Running

    python EXPLORATORY/theory/selftest_stdlib.py      # stdlib only, runs anywhere
    python EXPLORATORY/theory/estimator_errors/run.py  # needs numpy/matplotlib
    python EXPLORATORY/theory/allocation_theory/run.py
    python EXPLORATORY/theory/power_decomposition/run.py

Each run.py validates its closed forms on fixtures through the real pipeline,
writes figures/CSVs to its `outputs/`, and regenerates its FINDINGS.md.
