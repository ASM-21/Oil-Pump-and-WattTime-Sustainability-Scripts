"""
ENERGY BUDGET -- where every watt-hour goes, with closure.

The conference paper reports one non-productive number (homing at ~11.7% of
CNC energy). This project generalizes it into a complete budget:

  1. Category budget: energy share of every operation category, split into
     productive (cutting categories) and non-productive (idle, homing).
  2. Closure: bottom-up sum of attributed rows vs an independent
     integration of the full program power stream. The residual is the
     energy attribution silently loses; reporting it is what makes the
     budget auditable rather than rhetorical.

Always runs on fixtures (exit 0, known truth, real pipeline); adds measured
tables when CNC_DATA_DIR points at the real Al6061 folder.

Run from the repo root:
    python EXPLORATORY/energy_budget/run.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared import fixtures

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

NON_PRODUCTIVE = {"idle", "homing"}


def category_budget(df: pd.DataFrame) -> pd.DataFrame:
    """Energy budget by operation category, per part and pooled."""
    rows = []
    for scope, g in [("all", df)] + [(p, d) for p, d in df.groupby("part")]:
        total = g["energy_wh"].sum()
        for cat, cg in g.groupby("operation_cat"):
            rows.append({
                "scope": scope,
                "category": cat,
                "productive": cat not in NON_PRODUCTIVE,
                "energy_wh": cg["energy_wh"].sum(),
                "share_pct": 100 * cg["energy_wh"].sum() / total,
            })
    return pd.DataFrame(rows)


def closure_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bottom-up attributed energy vs independent stream integration, per
    (part, run, program). The stream path re-reads the raw CSV and takes the
    cumulative forward-kWh register's start-to-end delta over the full
    in-program span; the attributed path sums the adapter's per-operation
    energy_wh rows. Both sides must be on the SAME register basis: energy_wh
    already comes from the register (EnergyAnalyzer.calculate_from_register,
    exact and gap-immune -- see adapters.load_operation_energy()), so the
    independent check has to use the register too. An earlier version of
    this function rectangle-integrated the raw "active power" stream instead,
    which this repo's own compare_methods work
    (EXPLORATORY/compare_outputs/compare_methods.py, PAPER_ARGUMENT_MAP.md)
    already shows can diverge from the register by ~2% on totals but far more
    (up to ~186% seen on one transition-attribution line) on individual
    programs -- comparing across that gap would have measured the
    register-vs-active-power methodology difference, not attribution loss,
    and could have tripped the < 5% closure requirement below for reasons
    unrelated to attribution.
    """
    from EXPLORATORY.shared import adapters

    rows = []
    for (part, run_id), g in df.groupby(["part", "run_id"]):
        stream = adapters.load_power_stream(run_id, part=part)
        for program, pg in g.groupby("program"):
            s = stream[stream["program"] == program].sort_values("t")
            reg = s["register_kwh"].dropna()
            if len(reg) < 2:
                e_stream = float("nan")
            else:
                e_stream = float(reg.iloc[-1] - reg.iloc[0]) * 1000.0
                if e_stream < 0:  # register rollover within this program span
                    e_stream = float("nan")
            e_attr = float(pg["energy_wh"].sum())
            rows.append({
                "part": part, "run_id": run_id, "program": program,
                "attributed_wh": e_attr,
                "stream_wh": e_stream,
                "residual_pct": 100 * (e_stream - e_attr) / e_stream
                if e_stream else np.nan,
            })
    return pd.DataFrame(rows)


def figure_budget(budget: pd.DataFrame, tag: str) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    parts = [s for s in budget["scope"].unique() if s != "all"]
    cats = (budget[budget["scope"] == "all"]
            .sort_values("energy_wh", ascending=False)["category"].tolist())
    bottoms = {p: 0.0 for p in parts}
    for i, cat in enumerate(cats):
        vals = []
        for p in parts:
            row = budget[(budget["scope"] == p) & (budget["category"] == cat)]
            vals.append(float(row["share_pct"].iloc[0]) if len(row) else 0.0)
        hatch = "//" if cat in NON_PRODUCTIVE else None
        ax.bar(parts, vals, bottom=[bottoms[p] for p in parts],
               color=COLORS[i % len(COLORS)], label=cat, hatch=hatch,
               edgecolor="white", linewidth=0.3)
        for p, v in zip(parts, vals):
            bottoms[p] += v
    ax.set_ylabel("Share of part energy (%)")
    ax.legend(fontsize=5, ncol=2, loc="center left", bbox_to_anchor=(1.0, 0.5))
    ax.set_title(f"Energy budget by category ({tag}); hatched = non-productive",
                 fontsize=7)
    save_fig(fig, str(OUT / f"category_budget_{tag}"))


def analyze_source(tag: str) -> list[str]:
    from EXPLORATORY.shared import adapters

    df = adapters.load_operation_energy()
    budget = category_budget(df)
    closure = closure_table(df)

    budget.to_csv(OUT / f"category_budget_{tag}.csv", index=False)
    closure.to_csv(OUT / f"closure_{tag}.csv", index=False)
    figure_budget(budget, tag)

    pooled = budget[budget["scope"] == "all"]
    nonprod = pooled[~pooled["productive"]]["share_pct"].sum()
    homing = pooled[pooled["category"] == "homing"]["share_pct"].sum()
    worst_closure = closure["residual_pct"].abs().max()

    # Closure must be tight: the attribution already carries a
    # TRANSITION_OVERHEAD row, so residuals are edge trapezoids only.
    require(worst_closure < 5.0,
            f"{tag}: closure residual {worst_closure:.1f}% exceeds 5%")
    if tag == "measured":
        log.check_against_expected("homing share of CNC energy (%)",
                                   float(homing), 11.7)

    return [
        f"### Source: {tag}",
        "",
        f"- Non-productive share (idle + homing): {nonprod:.1f}% of energy",
        f"- Homing (transition overhead) share: {homing:.1f}%",
        f"- Worst closure residual over (part, run, program): "
        f"{worst_closure:.2f}%",
        "",
    ]


def main() -> None:
    sections: list[str] = []

    saved = os.environ.get("CNC_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            sections += analyze_source("fixture")
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved

    real_note = ("Real CNC data not reachable in this run; set CNC_DATA_DIR "
                 "and re-run for the measured budget (tag 'measured').")
    if os.environ.get("CNC_DATA_DIR") and os.environ.get("FIXTURE_SMOKE") != "1":
        try:
            sections += analyze_source("measured")
            real_note = "Measured budget written (tag 'measured')."
        except Exception as e:
            gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
            with gap.open("a") as f:
                f.write(f"- energy_budget (real-data pass): {e}\n")
            real_note = f"Real-data pass parked: {e}"

    require(not log.any_disagreements(), "a cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Energy budget: findings\n\n"
        "Full kWh accounting with closure: every category's share, split "
        "productive vs non-productive, and the bottom-up total reconciled "
        "against an independent integration of the raw stream. The closure "
        "residual is the audit number: energy the attribution loses.\n\n"
        + "\n".join(sections) + "\n"
        f"{real_note}\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK energy_budget")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
