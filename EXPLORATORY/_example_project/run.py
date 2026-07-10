"""
EXAMPLE PROJECT: the canonical flow every EXPLORATORY project copies.

This is a runnable reference, not a real analysis. It shows the required shape:
load via the adapter, compute the headline number, verify it two independent
ways, run a smoke test of invariants, emit a figure and a CSV, then write
FINDINGS. Copy this file as the starting point for a new project and replace the
COMPUTE section.

Run from the repo root:  python EXPLORATORY/_example_project/run.py
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

# Make EXPLORATORY importable when run from the repo root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared.style import apply_style, save_fig
from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared import adapters

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()


def load() -> pd.DataFrame:
    """Pull existing data through the adapter. No reparsing, no hardcoded paths."""
    try:
        df = adapters.load_operation_energy()
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        # Park cleanly. A real project writes the gap and exits 0 so the runner
        # can continue to the next project.
        gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with gap.open("a") as f:
            f.write(f"- example_project: {e}\n")
        print(f"PARKED: {e}")
        sys.exit(0)
    return df


def compute(df: pd.DataFrame) -> dict:
    """
    Replace this with the real analysis. The headline number here is the
    fleet-average power, computed two independent ways so it can be cross-checked.
    """
    # Path A: energy-weighted, total energy over total duration.
    avg_power_a = df["energy_wh"].sum() * 3600 / df["duration_s"].sum()  # W

    # Path B: origin-forced regression slope of energy(Wh*3600=J) on duration(s).
    # slope of J vs s = average watts. Independent of Path A's aggregation.
    import numpy as np
    x = df["duration_s"].to_numpy()
    y = (df["energy_wh"] * 3600).to_numpy()  # joules
    slope = float(x @ y / (x @ x))  # least squares through origin

    log.cross_check("fleet average power (W)", avg_power_a, slope, rel_tol=0.02)
    log.check_against_expected("fleet average power (W)", avg_power_a, 1376.0)

    return {"avg_power_w": avg_power_a, "regression_slope_w": slope, "df": df}


def smoke_test(result: dict) -> None:
    """Cheap invariants. Must pass before FINDINGS is written."""
    df = result["df"]
    require(len(df) > 0, "energy table is empty")
    require((df["energy_wh"] > 0).all(), "non-positive energy present")
    # Homing (TRANSITION_OVERHEAD) rows carry duration 0 by construction
    # (EnergyForFeatureLib synthesizes them); exclude them from the check.
    require((df["duration_s"] >= 0).all(), "negative duration present")
    require((df.loc[df["operation_cat"] != "homing", "duration_s"] > 0).all(),
            "non-positive duration outside homing rows")
    require(df["energy_wh"].notna().all(), "NaN energy present")
    require(200 < result["avg_power_w"] < 13400,
            "average power outside physically plausible CNC range")
    require(not log.any_disagreements(),
            "a cross-check disagreed; investigate before reporting")


def plot(result: dict) -> None:
    apply_style()
    import matplotlib.pyplot as plt
    df = result["df"]
    fig, ax = plt.subplots()
    ax.scatter(df["duration_s"], df["energy_wh"], s=8)
    ax.set_xlabel("Operation duration (s)")
    ax.set_ylabel("Operation energy (Wh)")
    ax.set_title("Duration vs energy (example)")
    save_fig(fig, str(OUT / "duration_vs_energy"))


def write_findings(result: dict) -> None:
    (OUT / "summary.csv").write_text(
        pd.DataFrame([{
            "avg_power_w": result["avg_power_w"],
            "regression_slope_w": result["regression_slope_w"],
        }]).to_csv(index=False)
    )
    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Example project findings\n\n"
        f"Fleet average power: {result['avg_power_w']:.1f} W "
        f"(regression slope {result['regression_slope_w']:.1f} W).\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )


def main() -> None:
    df = load()
    result = compute(df)
    try:
        smoke_test(result)
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
    plot(result)
    write_findings(result)
    print("OK")


if __name__ == "__main__":
    main()
