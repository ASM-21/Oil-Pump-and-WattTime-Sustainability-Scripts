"""
ALLOCATION THEORY -- closed-form error of LCA allocation rules for
co-produced parts, with the measured body/lid pair as the instance.

For per-unit true energies with ratio rho_E = e_lid / e_body, an allocation
attribute with ratio rho_x = x_lid / x_body, and production mix
phi = N_lid / N_body:

    err_body(phi, rho_x) = phi (rho_E - rho_x) / (1 + phi rho_x)
    err_lid(phi, rho_x)  = (rho_x / rho_E) (1 + phi rho_E) / (1 + phi rho_x) - 1

Validated in theory/selftest_stdlib.py (brute force) and here against
fixtures pushed through the real pipeline. The empirical rho_E comes from
the allocation/ project when real data is present; until then the quoted
0.677 is used and clearly marked unverified.

Outputs (outputs/):
  allocation_error_surface.(png|pdf)  -- err_body over (phi, rho_x), measured rho_E line
  allocation_rules_vs_mix.(png|pdf)   -- the three rules' error vs phi
  rule_errors_at_mixes.csv            -- table for the paper
  FINDINGS.md

Run from the repo root:
    python EXPLORATORY/theory/allocation_theory/run.py
Never parks; bom.csv (committed) supplies the mass ratios.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure, df_to_md
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared import fixtures

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

RHO_E_QUOTED = 0.677  # lid/body energy ratio from the paper; verify from data


def err_body(phi, rho_e, rho_x):
    return phi * (rho_e - rho_x) / (1.0 + phi * rho_x)


def err_lid(phi, rho_e, rho_x):
    return (rho_x / rho_e) * (1.0 + phi * rho_e) / (1.0 + phi * rho_x) - 1.0


# ---------------------------------------------------------------------------
# Inputs: attribute ratios from bom.csv; energy ratio from data if reachable
# ---------------------------------------------------------------------------

def attribute_ratios() -> dict[str, float]:
    from EXPLORATORY.shared import adapters

    bom = adapters.load_bom().set_index("part")
    return {
        "mass_removed": float(bom.loc["lid", "mass_removed_g"]
                              / bom.loc["body", "mass_removed_g"]),
        "mass_finished_economic": float(bom.loc["lid", "finished_mass_g"]
                                        / bom.loc["body", "finished_mass_g"]),
    }


def measured_rho_e() -> tuple[float, str]:
    """(rho_E, provenance). Uses real data when reachable, else quoted value."""
    from EXPLORATORY.shared import adapters

    if os.environ.get("CNC_DATA_DIR") and os.environ.get("FIXTURE_SMOKE") != "1":
        try:
            df = adapters.load_operation_energy()
            per_part = (df.groupby(["part", "run_id"])["energy_wh"].sum()
                          .groupby("part").mean())
            rho = float(per_part["lid"] / per_part["body"])
            log.check_against_expected("rho_E lid/body", rho, RHO_E_QUOTED)
            return rho, "measured (mean per-run total, all programs)"
        except Exception:
            pass
    return RHO_E_QUOTED, "quoted in paper, UNVERIFIED until data is supplied"


def time_ratio_from_data() -> float | None:
    from EXPLORATORY.shared import adapters

    if not (os.environ.get("CNC_DATA_DIR") and os.environ.get("FIXTURE_SMOKE") != "1"):
        return None
    try:
        df = adapters.load_operation_energy()
        per_part = (df.groupby(["part", "run_id"])["duration_s"].sum()
                      .groupby("part").mean())
        return float(per_part["lid"] / per_part["body"])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fixture validation: closed form vs actual allocation arithmetic
# ---------------------------------------------------------------------------

def validate_on_fixtures() -> None:
    from EXPLORATORY.shared import adapters

    saved = os.environ.get("CNC_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            df = adapters.load_operation_energy()
            per_part_e = (df.groupby(["part", "run_id"])["energy_wh"].sum()
                            .groupby("part").mean())
            per_part_t = (df.groupby(["part", "run_id"])["duration_s"].sum()
                            .groupby("part").mean())
            rho_e = float(per_part_e["lid"] / per_part_e["body"])
            rho_t = float(per_part_t["lid"] / per_part_t["body"])

            # Brute-force time allocation at mix phi = 2 lids per body.
            n_b, n_l = 3, 6
            e_tot = n_b * per_part_e["body"] + n_l * per_part_e["lid"]
            w_b = (n_b * per_part_t["body"]
                   / (n_b * per_part_t["body"] + n_l * per_part_t["lid"]))
            err_sim = (w_b * e_tot / n_b) / per_part_e["body"] - 1.0
            err_pred = err_body(n_l / n_b, rho_e, rho_t)
            log.cross_check("fixture time-allocation err_body (sim vs closed form)",
                            float(err_sim), float(err_pred), rel_tol=1e-9)
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved


# ---------------------------------------------------------------------------
# Figures and tables
# ---------------------------------------------------------------------------

def figure_surface(rho_e: float, ratios: dict[str, float]) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    phi = np.linspace(0.05, 4, 200)
    rho_x = np.linspace(0.05, 2, 200)
    P, R = np.meshgrid(phi, rho_x)
    Z = 100 * err_body(P, rho_e, R)
    cs = ax.contourf(P, R, Z, levels=15, cmap="RdBu_r",
                     vmin=-np.abs(Z).max(), vmax=np.abs(Z).max())
    fig.colorbar(cs, ax=ax, label="Body allocation error, %")
    ax.axhline(rho_e, color=COLORS[0], linewidth=1.0)
    ax.text(3.9, rho_e, " rho_x = rho_E (zero error)", fontsize=6,
            va="bottom", ha="right")
    for (name, r), c in zip(ratios.items(), COLORS[1:]):
        ax.axhline(r, linestyle="--", linewidth=0.9, color=c)
        ax.text(0.1, r, f" {name} ({r:.2f})", fontsize=6, va="bottom", color=c)
    ax.set_xlabel("Production mix phi = N_lid / N_body")
    ax.set_ylabel("Attribute ratio rho_x = x_lid / x_body")
    save_fig(fig, str(OUT / "allocation_error_surface"))


def figure_rules_vs_mix(rho_e: float, ratios: dict[str, float]) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    phi = np.linspace(0.05, 4, 300)
    for (name, r), c, ls in zip(ratios.items(), COLORS[1:], ["-", "--", "-."]):
        ax.plot(phi, 100 * err_body(phi, rho_e, r), color=c, linestyle=ls,
                label=f"{name} (rho_x={r:.2f})")
    ax.axhline(0, color=COLORS[0], linewidth=0.7)
    ax.set_xlabel("Production mix phi = N_lid / N_body")
    ax.set_ylabel("Body allocation error, %")
    ax.legend(fontsize=6)
    save_fig(fig, str(OUT / "allocation_rules_vs_mix"))


def main() -> None:
    validate_on_fixtures()

    ratios = attribute_ratios()
    rho_t = time_ratio_from_data()
    if rho_t is not None:
        ratios["time"] = rho_t
    rho_e, provenance = measured_rho_e()

    rows = []
    for name, rho_x in ratios.items():
        for phi in (0.5, 1.0, 2.0):
            rows.append({
                "rule": name, "rho_x": rho_x, "phi": phi,
                "err_body_pct": 100 * err_body(phi, rho_e, rho_x),
                "err_lid_pct": 100 * err_lid(phi, rho_e, rho_x),
            })
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "rule_errors_at_mixes.csv", index=False)

    figure_surface(rho_e, ratios)
    figure_rules_vs_mix(rho_e, ratios)

    require((table[table["phi"] == 1.0]["err_body_pct"].abs() < 200).all(),
            "allocation errors implausibly large; check ratios")
    require(not log.any_disagreements(), "a cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Allocation error theory: findings\n\n"
        f"rho_E (lid/body energy) = {rho_e:.3f} ({provenance}).\n"
        f"Attribute ratios from bom.csv: {ratios}.\n\n"
        "Allocation error is zero only where the attribute ratio equals the "
        "energy ratio. Neither mass basis achieves that here, and the error "
        "scales with production mix. Time-based allocation's ratio must come "
        "from measured durations (add CNC_DATA_DIR to fill it in).\n\n"
        "## Rule errors at representative mixes\n\n"
        + df_to_md(table) + "\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK allocation_theory")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
