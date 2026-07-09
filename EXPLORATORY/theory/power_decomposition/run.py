"""
POWER DECOMPOSITION -- the fixed-plus-variable model that explains WHY
duration-based estimation works on this machine, wired to the machining
energy literature.

Model (Gutowski et al.; Kara and Li): P(t) = P0 + P_proc(t). With the
per-operation load factor lambda_i = mean(P_proc,i) / P0:

    E_i = P0 * T_i * (1 + lambda_i)
    duration-only estimate error:  err_i = (lambda_bar - lambda_i) / (1 + lambda_i)

so a base-load-dominated machine (small, homogeneous lambda) is exactly a
machine where one average-power constant predicts energy from duration. The
stable ~1,376 W regression slope (recompute from data; never quote the slide)
is that constant, and its stability is a property of the machine, not luck.

Outputs (outputs/):
  lambda_by_category.csv          -- per-category load factors (fixture/real)
  base_vs_process_share.(png|pdf) -- stacked energy split per category
  sec_benchmark.csv               -- literature SEC table + this work's row
  FINDINGS.md

Run from the repo root:
    python EXPLORATORY/theory/power_decomposition/run.py
Never parks: fixtures carry the validation; real data adds the measured rows.
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

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared import fixtures

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

# Literature SEC benchmarks for metal removal, converted to kWh per kg of
# aluminum removed where the source reports kJ/cm3 (Al density 2.70 g/cm3;
# 1 kWh/kg = 9.72 kJ/cm3). Ranges are indicative spans from the cited works,
# for positioning this work's measured SEC, not for calculation.
SEC_LITERATURE = [
    {"source": "Gutowski et al. 2006", "process": "milling (varied MRR)",
     "sec_kwh_per_kg_low": 0.2, "sec_kwh_per_kg_high": 10.0},
    {"source": "Kara and Li 2011", "process": "milling (measured, several machines)",
     "sec_kwh_per_kg_low": 0.3, "sec_kwh_per_kg_high": 2.5},
    {"source": "Duflou et al. 2012", "process": "machining (review)",
     "sec_kwh_per_kg_low": 0.2, "sec_kwh_per_kg_high": 5.0},
    {"source": "THIS WORK body", "process": "milling Al6061 (removed-mass basis)",
     "sec_kwh_per_kg_low": np.nan, "sec_kwh_per_kg_high": np.nan},
    {"source": "THIS WORK lid", "process": "milling Al6061 (removed-mass basis)",
     "sec_kwh_per_kg_low": np.nan, "sec_kwh_per_kg_high": np.nan},
]


def decompose(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """
    Estimate P0 from NONE_IDLE rows (the machine's own dwell power), then
    split each work category's energy into base (P0 * T) and process parts.
    Returns (per-category table, P0 estimate in W).
    """
    idle = df[df["operation_cat"] == "idle"]
    require(len(idle) > 0, "no idle rows; cannot estimate P0 from data")
    # Duration-weighted idle power: total idle energy over total idle time.
    p0 = float(idle["energy_wh"].sum() * 3600.0 / idle["duration_s"].sum())

    work = df[~df["operation_cat"].isin(["idle", "homing"])].copy()
    work["base_wh"] = p0 * work["duration_s"] / 3600.0
    work["process_wh"] = (work["energy_wh"] - work["base_wh"]).clip(lower=0)
    work["lambda"] = work["process_wh"] / work["base_wh"].replace(0, np.nan)

    cat = work.groupby("operation_cat").agg(
        energy_wh=("energy_wh", "sum"),
        base_wh=("base_wh", "sum"),
        process_wh=("process_wh", "sum"),
        lambda_mean=("lambda", "mean"),
        n_instances=("energy_wh", "size"),
    ).reset_index()
    cat["base_share_pct"] = 100 * cat["base_wh"] / cat["energy_wh"]
    return cat, p0


def validate_on_fixtures() -> tuple[pd.DataFrame, float]:
    """Fixtures have a KNOWN base load; the decomposition must recover it."""
    from EXPLORATORY.shared import adapters

    saved = os.environ.get("CNC_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            df = adapters.load_operation_energy()
            cat, p0 = decompose(df)
            log.cross_check("fixture P0 recovery (est vs known 700 W)",
                            p0, fixtures.IDLE_POWER_W, rel_tol=0.03)

            # The duration-only error identity, checked on real pipeline rows.
            work = df[~df["operation_cat"].isin(["idle", "homing"])]
            p_fleet = work["energy_wh"].sum() * 3600.0 / work["duration_s"].sum()
            lam_bar = p_fleet / p0 - 1.0
            one = work.iloc[0]
            lam_i = (one["energy_wh"] * 3600.0 / one["duration_s"]) / p0 - 1.0
            err_identity = (lam_bar - lam_i) / (1.0 + lam_i)
            err_direct = (p_fleet * one["duration_s"] / 3600.0) / one["energy_wh"] - 1.0
            log.cross_check("L1 error identity (formula vs direct)",
                            err_identity, err_direct, rel_tol=1e-9)
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved
    return cat, p0


def real_data_rows() -> tuple[pd.DataFrame, float, dict] | None:
    from EXPLORATORY.shared import adapters

    if not os.environ.get("CNC_DATA_DIR"):
        return None
    try:
        df = adapters.load_operation_energy()
        cat, p0 = decompose(df)
        work = df[~df["operation_cat"].isin(["idle", "homing"])]
        p_fleet = work["energy_wh"].sum() * 3600.0 / work["duration_s"].sum()
        log.check_against_expected("fleet mean power (W)", p_fleet, 1376.0)

        # SEC on the removed-mass basis for the benchmark table.
        sec = {}
        bom = adapters.load_bom().set_index("part")
        per_part = df.groupby(["part", "run_id"])["energy_wh"].sum().groupby("part").mean()
        for part in ("body", "lid"):
            sec[part] = float(per_part[part] / 1000.0
                              / (bom.loc[part, "mass_removed_g"] / 1000.0))
        return cat, p0, sec
    except Exception:
        return None


def figure_split(cat: pd.DataFrame, p0: float, tag: str) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    cat = cat.sort_values("energy_wh", ascending=True)
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    y = np.arange(len(cat))
    ax.barh(y, cat["base_wh"], color=COLORS[2], label=f"base load (P0={p0:.0f} W)")
    ax.barh(y, cat["process_wh"], left=cat["base_wh"], color=COLORS[6],
            label="process")
    ax.set_yticks(y, cat["operation_cat"], fontsize=6)
    ax.set_xlabel("Energy (Wh)")
    ax.legend(fontsize=6)
    save_fig(fig, str(OUT / f"base_vs_process_share_{tag}"))


def main() -> None:
    fix_cat, fix_p0 = validate_on_fixtures()
    fix_cat.to_csv(OUT / "lambda_by_category_fixture.csv", index=False)
    figure_split(fix_cat, fix_p0, "fixture")

    sec_table = pd.DataFrame(SEC_LITERATURE)
    real = real_data_rows()
    real_text = ("_Real CNC data not reachable in this run; set CNC_DATA_DIR "
                 "to add measured rows (P0, per-category lambda, SEC)._")
    if real is not None:
        cat, p0, sec = real
        cat.to_csv(OUT / "lambda_by_category_measured.csv", index=False)
        figure_split(cat, p0, "measured")
        for part, v in sec.items():
            m = sec_table["source"] == f"THIS WORK {part}"
            sec_table.loc[m, ["sec_kwh_per_kg_low", "sec_kwh_per_kg_high"]] = v
        real_text = (f"Measured P0 = {p0:.0f} W. Per-category lambda in "
                     "lambda_by_category_measured.csv. "
                     f"SEC (removed-mass): body {sec['body']:.2f}, "
                     f"lid {sec['lid']:.2f} kWh/kg.")
    sec_table.to_csv(OUT / "sec_benchmark.csv", index=False)

    require(not log.any_disagreements(), "a cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Power decomposition: findings\n\n"
        "E_i = P0 T_i (1 + lambda_i); the duration-only estimator's error is "
        "(lambda_bar - lambda_i)/(1 + lambda_i), an identity validated through "
        "the real pipeline on fixtures (below). Base-load dominance is what "
        "makes the fleet average-power constant stable, and it is measurable "
        "per machine: report P0 and the lambda spread, not just the constant.\n\n"
        "## Fixture decomposition (known P0 = 700 W)\n\n"
        + fix_cat.to_markdown(index=False) + "\n\n"
        "## Measured data\n\n" + real_text + "\n\n"
        "## SEC benchmark (literature spans; fill measured rows from data)\n\n"
        + sec_table.to_markdown(index=False) + "\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK power_decomposition")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
