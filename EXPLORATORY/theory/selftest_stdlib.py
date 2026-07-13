"""
Stdlib-only validation of every closed form in the theory layer.

Each check builds a brute-force simulation with `random` and compares it to
the analytical result. No numpy, no pandas: this file runs in any Python 3.10+
environment, including ones where the scientific stack cannot be installed.
It is the fastest way to confirm the derivations are right before trusting
the (numpy-based) run.py projects that plot them.

Run from anywhere:
    python EXPLORATORY/theory/selftest_stdlib.py
"""

from __future__ import annotations

import math
import random


def _mean(xs):
    return sum(xs) / len(xs)


def check_l0_bias() -> None:
    """L0 relative bias equals 1/u - 1, independent of workload details."""
    rng = random.Random(1)
    p_rated = 10000.0
    for _ in range(5):
        # A workload of operations with arbitrary powers/durations.
        ops = [(rng.uniform(400, 4000), rng.uniform(20, 600)) for _ in range(40)]
        e_true = sum(p * t for p, t in ops)          # J-scale units, arbitrary
        t_total = sum(t for _, t in ops)
        e_l0 = p_rated * t_total
        u = (e_true / t_total) / p_rated             # mean power / rated
        bias_sim = e_l0 / e_true - 1.0
        bias_formula = 1.0 / u - 1.0
        assert abs(bias_sim - bias_formula) < 1e-9, (bias_sim, bias_formula)
    print(f"  L0 bias = 1/u - 1: OK (e.g. u=0.10 -> +{(1/0.10 - 1) * 100:.0f}%, "
          f"u=0.90 -> +{(1/0.90 - 1) * 100:.1f}%)")


def check_l1_replication_rule() -> None:
    """Std error of a characterized mean follows CV/sqrt(n); n-rule inverts it."""
    rng = random.Random(2)
    true_mean, cv, n = 200.0, 0.15, 12
    reps = 4000
    means = [
        _mean([rng.gauss(true_mean, true_mean * cv) for _ in range(n)])
        for _ in range(reps)
    ]
    grand = _mean(means)
    sd_of_mean = math.sqrt(_mean([(m - grand) ** 2 for m in means]))
    predicted = true_mean * cv / math.sqrt(n)
    assert abs(sd_of_mean - predicted) / predicted < 0.05, (sd_of_mean, predicted)

    r = 0.10
    n_req = (1.96 * cv / r) ** 2
    assert 8 < n_req < 9, n_req  # cv=0.15, r=10% -> n = 8.64
    print(f"  L1 SE = CV/sqrt(n) and n-rule: OK (CV 15%, r 10% -> n = {n_req:.1f})")


def check_allocation_closed_form() -> None:
    """err_body = phi(rho_E - rho_x) / (1 + phi rho_x) matches brute force."""
    rng = random.Random(3)
    for _ in range(200):
        e_body = rng.uniform(100, 1000)      # per-unit true energies
        rho_e = rng.uniform(0.1, 2.0)
        e_lid = e_body * rho_e
        x_body = rng.uniform(1, 100)         # per-unit attribute (time, mass...)
        rho_x = rng.uniform(0.1, 2.0)
        x_lid = x_body * rho_x
        n_body = rng.randint(1, 20)
        n_lid = rng.randint(1, 20)
        phi = n_lid / n_body

        e_total = n_body * e_body + n_lid * e_lid
        w_body = n_body * x_body / (n_body * x_body + n_lid * x_lid)
        alloc_body = w_body * e_total / n_body
        err_sim = alloc_body / e_body - 1.0
        err_formula = phi * (rho_e - rho_x) / (1.0 + phi * rho_x)
        assert abs(err_sim - err_formula) < 1e-9, (err_sim, err_formula)

    # Headline instance from the paper's numbers (quoted rho_E, bom masses).
    rho_e = 0.677                       # lid/body energy ratio, verify from data
    rho_mass = 448.0 / 1437.0           # removed-mass basis from bom.csv
    rho_econ = 70.0 / 443.0             # finished-mass basis (economic proxy)
    at = lambda rho_x: (rho_e - rho_x) / (1.0 + rho_x) * 100  # phi = 1
    print("  allocation closed form: OK "
          f"(at 1:1 mix, quoted rho_E=0.677: mass-removed {at(rho_mass):+.1f}%, "
          f"economic/finished {at(rho_econ):+.1f}% body error)")


def check_power_decomposition_l1_error() -> None:
    """Duration-only estimation error per operation = (lam_bar - lam_i)/(1 + lam_i)."""
    rng = random.Random(4)
    p0 = 700.0
    lambdas = [rng.uniform(0.05, 3.0) for _ in range(30)]
    durations = [rng.uniform(30, 600) for _ in range(30)]
    energies = [p0 * t * (1 + lam) for t, lam in zip(durations, lambdas)]

    # Fleet mean power implied by a duration-weighted characterization.
    p_fleet = sum(energies) / sum(durations)
    lam_bar = p_fleet / p0 - 1.0

    for lam, t, e in zip(lambdas, durations, energies):
        est = p_fleet * t
        err_sim = est / e - 1.0
        err_formula = (lam_bar - lam) / (1.0 + lam)
        assert abs(err_sim - err_formula) < 1e-9, (err_sim, err_formula)
    print("  power-decomposition L1 error form: OK "
          f"(fleet lambda_bar = {lam_bar:.2f})")


def check_mc_vs_delta_total() -> None:
    """Stdlib MC of a sum of normals matches the exact delta-method moments."""
    rng = random.Random(5)
    stats = [(rng.uniform(5, 200), rng.uniform(0.5, 8)) for _ in range(25)]
    n_draws = 20000
    totals = [
        sum(max(0.0, rng.gauss(m, s)) for m, s in stats) for _ in range(n_draws)
    ]
    mc_mean = _mean(totals)
    mc_sd = math.sqrt(_mean([(t - mc_mean) ** 2 for t in totals]))
    d_mean = sum(m for m, _ in stats)
    d_sd = math.sqrt(sum(s * s for _, s in stats))
    assert abs(mc_mean - d_mean) / d_mean < 0.01, (mc_mean, d_mean)
    assert abs(mc_sd - d_sd) / d_sd < 0.05, (mc_sd, d_sd)
    print(f"  MC vs delta method: OK (mean {mc_mean:.1f} vs {d_mean:.1f}, "
          f"sd {mc_sd:.2f} vs {d_sd:.2f})")


def main() -> None:
    print("THEORY SELFTEST (stdlib only)")
    check_l0_bias()
    check_l1_replication_rule()
    check_allocation_closed_form()
    check_power_decomposition_l1_error()
    check_mc_vs_delta_total()
    print("ALL THEORY CLOSED FORMS VALIDATED")


if __name__ == "__main__":
    main()
