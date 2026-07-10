"""
A2 FDM UTILIZATION -- compute u_FDM from measured prints instead of the
spec sheet.

The estimation-ladder contrast (CNC u about 0.10 vs FDM u about 0.90) has so
far used the Ultimaker's quoted numbers (rated ~221 W, measured draw ~200 W,
GROUND_TRUTH.md). Per the verify-quoted-numbers rule, this script computes
the FDM utilization factor from the actual print CSVs:

    u_FDM = (duration-weighted mean power across prints) / 221 W

Always validates the AM loader against synthetic AM fixtures first (known
truth, exact adapter integration rule). Then, if AM_DATA_DIR points at the
real FDM CSVs ({Prefix}_Part{N}.csv), computes the measured table and checks
it against the quoted ~200 W and u ~0.9.

Run from the repo root:
    python EXPLORATORY/explorations/A2_fdm_utilization.py

Outputs: explorations/outputs/A2_fdm_utilization.csv and
explorations/A2_fdm_utilization_FINDINGS.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure, df_to_md
from EXPLORATORY.shared import fixtures
from EXPLORATORY.shared import adapters

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()


def validate_loader_on_fixtures() -> None:
    """The AM loader must reproduce fixture truth EXACTLY (same dt rule)."""
    saved = os.environ.get("AM_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            truth = pd.DataFrame(fixtures.generate_am_fixture_dataset(tmp, n_runs=2))
            os.environ["AM_DATA_DIR"] = tmp
            table = adapters.load_am_energy()
            merged = truth.merge(table, on=["part", "run_id"],
                                 suffixes=("_truth", "_load"))
            require(len(merged) == len(truth), "AM loader lost fixture prints")
            rel = ((merged["energy_wh_load"] - merged["energy_wh_truth"]).abs()
                   / merged["energy_wh_truth"])
            require(bool((rel < 1e-6).all()),
                    f"AM loader energy deviates from truth: worst {rel.max():.2e}")
            # Utilization on the fixture: plateau 200 W of a 221 W machine,
            # dragged down slightly by ramp and cooldown.
            u_fix = float(merged["energy_wh_load"].sum() * 3600.0
                          / merged["duration_s_load"].sum()
                          / adapters.AM_RATED_POWER_W)
            require(0.75 < u_fix < 0.95, f"fixture u_FDM {u_fix:.2f} out of range")
            log.cross_check("fixture u_FDM (loader vs truth path)",
                            u_fix,
                            float(truth["energy_wh"].sum() * 3600.0
                                  / truth["duration_s"].sum()
                                  / adapters.AM_RATED_POWER_W),
                            rel_tol=1e-6)
    finally:
        if saved is None:
            os.environ.pop("AM_DATA_DIR", None)
        else:
            os.environ["AM_DATA_DIR"] = saved


def measured_table() -> pd.DataFrame | None:
    if not os.environ.get("AM_DATA_DIR"):
        return None
    try:
        table = adapters.load_am_energy()
    except adapters.DataNotInRepo as e:
        gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with gap.open("a") as f:
            f.write(f"- A2_fdm_utilization (real-data pass): {e}\n")
        return None
    return table


def main() -> None:
    validate_loader_on_fixtures()

    table = measured_table()
    if table is not None:
        p_mean = float(table["energy_wh"].sum() * 3600.0
                       / table["duration_s"].sum())
        u_fdm = p_mean / adapters.AM_RATED_POWER_W
        log.check_against_expected("FDM mean operating power (W)", p_mean, 200.0,
                                   note="quoted 'measured draw ~200 W'")
        log.check_against_expected("FDM utilization u", u_fdm, 0.90, rel_tol=0.10,
                                   note="quoted u ~0.9 from spec-sheet argument")
        per_part = table.groupby("part").agg(
            n_prints=("run_id", "nunique"),
            mean_power_w=("mean_power_w", "mean"),
            total_energy_wh=("energy_wh", "sum"),
        ).reset_index()
        per_part.to_csv(OUT / "A2_fdm_utilization.csv", index=False)
        measured_text = (
            f"Measured across {len(table)} prints: duration-weighted mean power "
            f"{p_mean:.1f} W, u_FDM = {u_fdm:.3f} (rated basis "
            f"{adapters.AM_RATED_POWER_W:.0f} W).\n\n" + df_to_md(per_part)
        )
    else:
        measured_text = (
            "_AM_DATA_DIR not set or no files found; u_FDM stays a spec-sheet "
            "number (~0.90) until the FDM CSVs are supplied. Loader is fixture "
            "verified and ready._"
        )

    require(not log.any_disagreements(),
            "a cross-check disagreed; see the table before quoting u_FDM")

    findings = Path(__file__).parent / "A2_fdm_utilization_FINDINGS.md"
    findings.write_text(
        "# A2: FDM utilization from data\n\n"
        "u_FDM anchors the high end of the utilization landscape (the CNC "
        "anchors the low end at u about 0.10). This script replaces the "
        "spec-sheet argument with measurement.\n\n"
        "## Measured\n\n" + measured_text + "\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK A2_fdm_utilization")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
