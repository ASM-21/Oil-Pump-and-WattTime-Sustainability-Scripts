#!/usr/bin/env python3
"""
energy_breakdown.py
===================

Attribute energy across operations and programs: where does the energy actually go.
Computes per-operation energy share within each program, a Pareto of energy by
operation, specific energy (energy per second), per-run energy distribution, and
idle overhead if idle was retained. Points straight at the operation_csvs folder.

Idle note: split_operations.py drops idle (processKindId == NONE) by default. To
include idle overhead here, regenerate with `split_operations.py --keep-idle`; this
script reports it automatically if an 'idle' operation is present.

Outputs (into --output, default ./ml/energy_breakdown):
  energy_by_program_operation.csv  program x operation: total energy, share, passes
  energy_pareto.csv                operations ranked by total energy, cumulative share
  specific_energy_by_operation.csv energy per pass and per second, by operation
  energy_per_run.csv               total energy per run (part), with operation count
  *.png                            stacked energy-by-program bar + Pareto curve

Usage
-----
  python energy_breakdown.py --input ./operation_csvs
  python energy_breakdown.py --input ./operation_csvs --target wh_integral
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

import features as F

warnings.filterwarnings("ignore")

UNITS = {"energy_kwh_meter": "kWh", "energy_wh_integral": "Wh"}


def pick_energy(table: pd.DataFrame, choice: str) -> str:
    have = [t for t in F.TARGET_COLUMNS if t in table.columns]
    if not have:
        raise ValueError("No energy target found (need forward-kWh or active-power channel).")
    if choice == "kwh_meter" and "energy_kwh_meter" in have:
        return "energy_kwh_meter"
    if choice == "wh_integral" and "energy_wh_integral" in have:
        return "energy_wh_integral"
    return "energy_kwh_meter" if "energy_kwh_meter" in have else have[0]


def by_program_operation(table, ecol) -> pd.DataFrame:
    g = (table.groupby(["program", "operation"])
         .agg(total_energy=(ecol, "sum"),
              mean_energy=(ecol, "mean"),
              passes=(ecol, "size"))
         .reset_index())
    prog_tot = g.groupby("program")["total_energy"].transform("sum")
    g["share_pct"] = 100 * g["total_energy"] / prog_tot
    return g.sort_values(["program", "total_energy"], ascending=[True, False])


def pareto(table, ecol) -> pd.DataFrame:
    g = (table.groupby("operation")[ecol].sum().sort_values(ascending=False)
         .rename("total_energy").reset_index())
    g["share_pct"] = 100 * g["total_energy"] / g["total_energy"].sum()
    g["cumulative_pct"] = g["share_pct"].cumsum()
    return g


def specific_energy(table, ecol) -> pd.DataFrame:
    t = table.copy()
    t["energy_per_s"] = t[ecol] / t["duration_s"].replace(0, np.nan)
    g = (t.groupby("operation")
         .agg(energy_per_pass=(ecol, "mean"),
              energy_per_s=("energy_per_s", "mean"),
              mean_duration_s=("duration_s", "mean"),
              passes=(ecol, "size"))
         .reset_index().sort_values("energy_per_s", ascending=False))
    return g


def per_run(table, ecol) -> pd.DataFrame:
    g = (table.groupby(["program", "source_file"])
         .agg(total_energy=(ecol, "sum"),
              operations=("operation", "nunique"),
              passes=(ecol, "size"))
         .reset_index().sort_values("total_energy", ascending=False))
    return g


def maybe_plot(bpo, par, ecol, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    unit = UNITS.get(ecol, "")
    pivot = bpo.pivot(index="program", columns="operation", values="total_energy").fillna(0)
    fig, ax = plt.subplots(figsize=(7, 4))
    bottom = np.zeros(len(pivot))
    for op in pivot.columns:
        ax.bar(pivot.index, pivot[op].values, bottom=bottom, label=op)
        bottom += pivot[op].values
    ax.set_ylabel(f"energy ({unit})"); ax.set_title("Energy by program, split by operation")
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout(); fig.savefig(out_dir / "energy_by_program.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(par["operation"], par["share_pct"], color="#4C78A8")
    ax2 = ax.twinx()
    ax2.plot(par["operation"], par["cumulative_pct"], color="#E45756", marker="o")
    ax2.axhline(80, ls="--", color="grey", lw=1)
    ax.set_ylabel("share (%)"); ax2.set_ylabel("cumulative (%)")
    ax.set_title("Energy Pareto by operation")
    plt.setp(ax.get_xticklabels(), rotation=20)
    fig.tight_layout(); fig.savefig(out_dir / "energy_pareto.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Energy attribution across operations and programs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/energy_breakdown")
    ap.add_argument("--target", choices=["auto", "kwh_meter", "wh_integral"], default="auto")
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    ecol = pick_energy(table, args.target)
    unit = UNITS.get(ecol, "")

    bpo = by_program_operation(table, ecol)
    par = pareto(table, ecol)
    spec = specific_energy(table, ecol)
    runs = per_run(table, ecol)

    bpo.to_csv(out_dir / "energy_by_program_operation.csv", index=False)
    par.to_csv(out_dir / "energy_pareto.csv", index=False)
    spec.to_csv(out_dir / "specific_energy_by_operation.csv", index=False)
    runs.to_csv(out_dir / "energy_per_run.csv", index=False)
    maybe_plot(bpo, par, ecol, out_dir)

    # ---- console summary -------------------------------------------------
    total = table[ecol].sum()
    print(f"Total measured energy across all passes: {total:.4f} {unit} "
          f"({ecol})\n")

    print("Energy Pareto by operation:")
    for _, r in par.iterrows():
        print(f"  {r['operation']:18s} {r['total_energy']:.4f} {unit}  "
              f"{r['share_pct']:5.1f}%  (cum {r['cumulative_pct']:5.1f}%)")
    n80 = int((par["cumulative_pct"] <= 80).sum()) + 1
    print(f"  => {n80} operation(s) account for ~80% of energy.")

    if "idle" in set(table["operation"]):
        idle_e = table[table["operation"] == "idle"][ecol].sum()
        print(f"\nIdle overhead: {idle_e:.4f} {unit} ({100*idle_e/total:.1f}% of total).")
    else:
        print("\nIdle not present (run split_operations.py --keep-idle to capture overhead).")

    print("\nSpecific energy (energy per second of operation):")
    for _, r in spec.iterrows():
        print(f"  {r['operation']:18s} {r['energy_per_s']:.6f} {unit}/s  "
              f"({r['energy_per_pass']:.4f} {unit}/pass, {r['mean_duration_s']:.1f}s avg)")

    print("\nEnergy per run (part) summary:")
    print(f"  mean {runs['total_energy'].mean():.4f} {unit}, "
          f"range {runs['total_energy'].min():.4f}-{runs['total_energy'].max():.4f} {unit} "
          f"across {len(runs)} runs.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
