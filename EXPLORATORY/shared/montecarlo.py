"""
Uncertainty propagation for product-level energy and carbon footprints.

WHY THIS EXISTS
The conference paper reports point estimates. A journal reviewer will ask for
an interval, and for where the interval comes from. This module propagates
the three uncertainty sources the measurement campaign actually quantifies:

  1. operation energy   - replicated 16 to 27 times per program, so each
                          operation has an empirical mean and sd;
  2. part mass          - scale resolution / weighing repeatability;
  3. carbon factors     - scenario ranges for aluminum embodied carbon and
                          grid intensity (not distributions; reported as
                          scenario rows, never averaged away).

Two propagation paths are provided ON PURPOSE: a Monte Carlo sampler and a
first-order delta-method approximation. Every reported interval must come
with the two-path agreement check (see shared/checks.py CheckLog); a wide
disagreement means the linearization is invalid or the sampler is wrong,
and either way the number is not ready for the paper.

Machine-agnostic: consumes per-operation statistics, not raw data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "OperationStat",
    "fit_operation_stats",
    "mc_total_energy",
    "delta_total_energy",
    "footprint_from_energy",
    "summarize_samples",
]


@dataclass
class OperationStat:
    """Per-operation replicate statistics (energy in Wh)."""
    operation: str
    mean_wh: float
    sd_wh: float
    n_runs: int

    @property
    def se_wh(self) -> float:
        """Standard error of the mean across replicates."""
        return self.sd_wh / np.sqrt(self.n_runs) if self.n_runs > 0 else float("nan")


def fit_operation_stats(df) -> list[OperationStat]:
    """
    Build OperationStat rows from an adapter operation-energy table
    (columns: operation_id, energy_wh, run_id). Normality across replicates
    is the working assumption; the paper's Shapiro-Wilk screen (40 of 45
    near-normal, verify from data) is the justification, and heavy-tailed
    operations should be flagged, not silently averaged.
    """
    stats = []
    for op, g in df.groupby("operation_id"):
        stats.append(OperationStat(
            operation=str(op),
            mean_wh=float(g["energy_wh"].mean()),
            sd_wh=float(g["energy_wh"].std(ddof=1)) if len(g) > 1 else 0.0,
            n_runs=int(g["run_id"].nunique()),
        ))
    return stats


def mc_total_energy(
    stats: list[OperationStat],
    n_draws: int = 20000,
    seed: int = 42,
    use_se: bool = True,
) -> np.ndarray:
    """
    Sample the total product energy (Wh) by summing per-operation draws.

    use_se=True samples the uncertainty of each operation's MEAN (the right
    quantity for "what is the energy of the average part"); use_se=False
    samples run-to-run spread (the right quantity for "what will the next
    single part draw"). State which question a reported interval answers.
    Draws are truncated at zero; energy cannot be negative.
    """
    rng = np.random.default_rng(seed)
    total = np.zeros(n_draws)
    for s in stats:
        scale = s.se_wh if use_se else s.sd_wh
        scale = 0.0 if not np.isfinite(scale) else scale
        total += np.clip(rng.normal(s.mean_wh, scale, n_draws), 0.0, None)
    return total


def delta_total_energy(stats: list[OperationStat], use_se: bool = True) -> tuple[float, float]:
    """
    First-order (delta method) mean and sd of total energy. For a plain sum
    of independent terms this is exact, which is what makes it a strong
    cross-check on the Monte Carlo path: agreement is required, not hoped for.
    """
    mean = float(sum(s.mean_wh for s in stats))
    var = float(sum(
        (s.se_wh if use_se else s.sd_wh) ** 2
        for s in stats
        if np.isfinite(s.se_wh if use_se else s.sd_wh)
    ))
    return mean, float(np.sqrt(var))


def footprint_from_energy(
    energy_wh: np.ndarray,
    mass_g: float,
    mass_sd_g: float,
    cf_al_kg_per_kg: float,
    grid_ci_kg_per_kwh: float,
    seed: int = 43,
) -> dict[str, np.ndarray]:
    """
    Combine sampled manufacturing energy with sampled part mass under ONE
    (aluminum carbon factor, grid intensity) scenario.

    Returns arrays (same length as energy_wh):
      materials_kg  - stock_mass * CF_aluminum
      mfg_kg        - energy * grid CI
      total_kg      - sum
      mfg_share_pct - manufacturing share of the total, in percent

    Carbon factors are deliberately scalars: they are scenario axes, and
    averaging over them would manufacture false confidence. Sweep scenarios
    in the calling project and report rows per scenario.
    """
    rng = np.random.default_rng(seed)
    n = len(energy_wh)
    mass_kg = np.clip(rng.normal(mass_g, mass_sd_g, n), 0.0, None) / 1000.0
    materials = mass_kg * cf_al_kg_per_kg
    mfg = (np.asarray(energy_wh) / 1000.0) * grid_ci_kg_per_kwh
    total = materials + mfg
    return {
        "materials_kg": materials,
        "mfg_kg": mfg,
        "total_kg": total,
        "mfg_share_pct": 100.0 * mfg / total,
    }


def summarize_samples(x: np.ndarray, ci: float = 0.95) -> dict[str, float]:
    """Mean, sd, and central credible interval of a sample array."""
    lo = 100 * (1 - ci) / 2
    return {
        "mean": float(np.mean(x)),
        "sd": float(np.std(x, ddof=1)),
        f"p{lo:g}": float(np.percentile(x, lo)),
        f"p{100 - lo:g}": float(np.percentile(x, 100 - lo)),
    }
