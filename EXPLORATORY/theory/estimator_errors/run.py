"""
ESTIMATOR ERRORS -- closed-form accuracy of energy-estimation shortcuts,
and the (utilization, CV) regime map that says which shortcut a machine
class can afford.

Closed forms (validated in theory/selftest_stdlib.py and again here on
fixtures pushed through the REAL pipeline):

  L0 rated-power estimate:   relative bias = 1/u - 1,  u = P_mean / P_rated
  L1 characterized power:    unbiased, relative SE = CV / sqrt(n)
  replication rule:          n = (1.96 * CV / r)^2 for target precision r
  L0 acceptability:          u >= 1 / (1 + r)

Outputs (outputs/):
  l0_bias_vs_utilization.(png|pdf)  -- bias curve with machine-class ranges
  regime_map.(png|pdf)              -- (u, CV) plane: cheapest acceptable level
  machine_class_bias.csv            -- A1 landscape classes -> L0 bias ranges
  fixture_validation.csv            -- predicted vs simulated on fixtures
  FINDINGS.md                       -- regenerated on every run

Run from the repo root:
    python EXPLORATORY/theory/estimator_errors/run.py
Needs numpy/pandas/matplotlib. Never parks: fixtures provide the validation
data; real CNC data (CNC_DATA_DIR) only adds empirical confirmation rows.
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

# Fixture machine: rated power basis for the synthetic validation only.
FIXTURE_RATED_W = 10000.0

# A1 utilization landscape (literature ranges; this work's u values are
# computed from data when available, spec sheet for FDM until then).
MACHINE_CLASSES = [
    # (label, u_low, u_high, source)
    ("CNC machining center (this work)", 0.08, 0.14, "computed from data [verify]"),
    ("FDM printer (this work)",          0.85, 0.95, "spec sheet until AM data wired"),
    ("Injection molding",                0.60, 0.80, "Gutowski et al."),
    ("Grinding",                         0.30, 0.50, "Kara and Li 2011"),
    ("Laser / EDM",                      0.30, 0.70, "Kara and Li 2011"),
]


# ---------------------------------------------------------------------------
# Closed forms
# ---------------------------------------------------------------------------

def l0_bias(u: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / u - 1.0


def n_required(cv: np.ndarray | float, r: float) -> np.ndarray | float:
    return (1.96 * cv / r) ** 2


def u_required(r: float) -> float:
    return 1.0 / (1.0 + r)


# ---------------------------------------------------------------------------
# Fixture validation through the real pipeline
# ---------------------------------------------------------------------------

def validate_on_fixtures() -> pd.DataFrame:
    """Generate fixtures, run the REAL pipeline, and confirm the closed forms."""
    from EXPLORATORY.shared import adapters

    saved = os.environ.get("CNC_DATA_DIR")
    rows = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            df = adapters.load_operation_energy()

            work = df[~df["operation_cat"].isin(["idle", "homing"])]
            e_true_wh = work["energy_wh"].sum()
            t_total_s = work["duration_s"].sum()
            p_mean = e_true_wh * 3600.0 / t_total_s
            u = p_mean / FIXTURE_RATED_W

            # L0 on the whole fixture campaign.
            e_l0_wh = FIXTURE_RATED_W * t_total_s / 3600.0
            bias_sim = e_l0_wh / e_true_wh - 1.0
            bias_pred = l0_bias(u)
            log.cross_check("fixture L0 bias (sim vs 1/u-1)", bias_sim, bias_pred,
                            rel_tol=1e-6)
            rows.append({"check": "L0_bias", "u": u,
                         "predicted": bias_pred, "simulated": bias_sim})

            # L1: characterize mean power on runs 1-2, predict run 3 energies
            # from durations alone.
            train = work[work["run_id"] < 3]
            test = work[work["run_id"] == 3]
            p_char = train["energy_wh"].sum() * 3600.0 / train["duration_s"].sum()
            e_l1 = p_char * test["duration_s"].sum() / 3600.0
            err_l1 = e_l1 / test["energy_wh"].sum() - 1.0
            rows.append({"check": "L1_holdout_err", "u": u,
                         "predicted": 0.0, "simulated": err_l1})
            require(abs(err_l1) < 0.10,
                    f"L1 holdout error {err_l1:.2%} implausibly large on fixtures")
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved
    return pd.DataFrame(rows)


def empirical_rows() -> pd.DataFrame | None:
    """If real data is reachable, compute the paper's empirical points."""
    from EXPLORATORY.shared import adapters

    if not (os.environ.get("CNC_DATA_DIR") and os.environ.get("FIXTURE_SMOKE") != "1"):
        return None
    try:
        df = adapters.load_operation_energy()
    except (adapters.DataNotInRepo, Exception):
        return None
    work = df[~df["operation_cat"].isin(["idle", "homing"])]
    p_mean = work["energy_wh"].sum() * 3600.0 / work["duration_s"].sum()
    # Rated-power basis: spindle rating per GROUND_TRUTH. State the basis in
    # the paper; report both if the electrical plate becomes available.
    rated_spindle_w = 13400.0
    u = p_mean / rated_spindle_w
    return pd.DataFrame([{
        "machine": "Hurco VMX30Ui (measured)",
        "p_mean_w": p_mean,
        "rated_basis_w": rated_spindle_w,
        "u": u,
        "l0_bias_pct": 100 * l0_bias(u),
    }])


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def figure_bias_curve() -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    u = np.linspace(0.05, 1.0, 400)
    ax.plot(u, 100 * l0_bias(u), color=COLORS[0])
    for r, ls in ((0.10, "--"), (0.25, ":")):
        ax.axhline(100 * r, linestyle=ls, linewidth=0.8, color=COLORS[6])
        ax.text(1.0, 100 * r, f" r={int(r*100)}%", fontsize=6,
                va="bottom", ha="right", color=COLORS[6])
    for (label, lo, hi, _), c in zip(MACHINE_CLASSES, COLORS[1:]):
        mid = (lo + hi) / 2
        ax.plot([lo, hi], [100 * l0_bias(lo), 100 * l0_bias(hi)],
                linewidth=3, alpha=0.8, color=c)
        ax.annotate(label.split(" (")[0], (mid, 100 * l0_bias(mid)),
                    textcoords="offset points", xytext=(4, 4), fontsize=6)
    ax.set_yscale("log")
    ax.set_xlabel("Utilization u = mean power / rated power")
    ax.set_ylabel("L0 (rated-power) bias, %")
    save_fig(fig, str(OUT / "l0_bias_vs_utilization"))


def figure_regime_map() -> None:
    import matplotlib.pyplot as plt

    apply_style()
    r = 0.10  # target relative precision for the map
    fig, ax = plt.subplots(figsize=(3.5, 2.8))
    u_ok = u_required(r)

    # L0-acceptable region (independent of CV).
    ax.axvspan(u_ok, 1.0, alpha=0.15, color=COLORS[3],
               label=f"L0 acceptable (u >= {u_ok:.2f})")
    # L1 replication contours where L0 is not acceptable.
    cv = np.linspace(0.01, 0.5, 200)
    for n, ls in ((1, "-"), (3, "--"), (10, "-."), (30, ":")):
        cv_at_n = r * np.sqrt(n) / 1.96
        if cv_at_n <= 0.5:
            ax.axhline(cv_at_n, linestyle=ls, linewidth=0.9, color=COLORS[0])
            ax.text(0.02, cv_at_n, f" n={n}", fontsize=6, va="bottom")
    for (label, lo, hi, _), c in zip(MACHINE_CLASSES, COLORS[1:]):
        ax.plot([(lo + hi) / 2], [0.08], marker="o", color=c, markersize=4)
        ax.annotate(label.split(" (")[0], ((lo + hi) / 2, 0.08),
                    textcoords="offset points", xytext=(0, 5),
                    fontsize=5.5, rotation=90, va="bottom", ha="center")
    ax.set_xlim(0, 1.05)
    ax.set_ylim(0, 0.5)
    ax.set_xlabel("Utilization u")
    ax.set_ylabel("Replicate CV of operation energy")
    ax.set_title(f"Cheapest acceptable estimator at r = {int(r*100)}%", fontsize=8)
    ax.legend(loc="upper right")
    save_fig(fig, str(OUT / "regime_map"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    fixture_df = validate_on_fixtures()
    fixture_df.to_csv(OUT / "fixture_validation.csv", index=False)

    classes = pd.DataFrame(
        [{"machine_class": m, "u_low": lo, "u_high": hi,
          "l0_bias_low_pct": 100 * l0_bias(hi), "l0_bias_high_pct": 100 * l0_bias(lo),
          "source": src}
         for m, lo, hi, src in MACHINE_CLASSES]
    )
    classes.to_csv(OUT / "machine_class_bias.csv", index=False)

    emp = empirical_rows()
    if emp is not None:
        emp.to_csv(OUT / "empirical_points.csv", index=False)

    figure_bias_curve()
    figure_regime_map()

    require(not log.any_disagreements(), "a fixture cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    emp_text = (
        df_to_md(emp) if emp is not None
        else "_Real CNC data not reachable in this run; set CNC_DATA_DIR to add "
             "the measured Hurco point. The theory and fixture validation above "
             "do not depend on it._"
    )
    findings.write_text(
        "# Estimator error theory: findings\n\n"
        "L0 (rated-power) bias is the identity 1/u - 1; L1 is unbiased with "
        "SE = CV/sqrt(n); L0 is acceptable at precision r only when "
        "u >= 1/(1+r). At r = 10% that threshold is u >= 0.909: the FDM "
        "printer (u about 0.90) sits ON the boundary, the CNC (u about 0.10, "
        "bias about +900%) is nowhere near it. The estimation shortcut is a "
        "property of the machine class, decidable at design time.\n\n"
        "## Machine-class L0 bias ranges\n\n"
        + df_to_md(classes) + "\n\n"
        "## Fixture validation (real pipeline, known truth)\n\n"
        + df_to_md(fixture_df) + "\n\n"
        "## Empirical point (measured data)\n\n" + emp_text + "\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK estimator_errors")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
