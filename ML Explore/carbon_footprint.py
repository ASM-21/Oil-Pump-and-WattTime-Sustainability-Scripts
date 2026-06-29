#!/usr/bin/env python3
"""
carbon_footprint.py
===================

Turn measured energy into a carbon footprint and bridge to LCA. Computes operational
(electricity) carbon per pass / operation / part, and, if you supply material carbon,
the material-vs-manufacturing split and a per-part carbon passport. Points straight at
the operation_csvs folder. This is the total-footprint complement to carbon_scheduling.py
(which handles the temporal, marginal side).

Operational carbon = energy (kWh) x emission factor (kg CO2e/kWh). Set the factor with
--emission-factor (default 0.40, a generic grid average) or per-region as you like.

Material carbon (embodied) is optional: pass a single value per part with
--material-carbon, or a CSV mapping program -> material carbon (kg) with --material-csv.
When provided, the script reports the material-vs-manufacturing split (the typical
finding that material dominates the product footprint).

Outputs (into --output, default ./ml/carbon):
  carbon_by_operation.csv   per program x operation: energy, operational carbon, share
  carbon_pareto.csv         operations ranked by carbon, cumulative share
  carbon_passport.csv       per part (program/run): energy, op carbon, material, total, % mfg
  material_vs_manufacturing.csv  split summary (only if material carbon supplied)
  *.png                     carbon by operation; material-vs-manufacturing split

Usage
-----
  python carbon_footprint.py --input ./operation_csvs --emission-factor 0.42
  python carbon_footprint.py --input ./operation_csvs --material-carbon 12.5
  python carbon_footprint.py --input ./operation_csvs --material-csv material.csv
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

import features as F

warnings.filterwarnings("ignore")


def energy_kwh_column(table: pd.DataFrame) -> str:
    if "energy_kwh_meter" in table:
        return "energy_kwh_meter"
    if "energy_wh_integral" in table:
        table["energy_kwh_meter"] = table["energy_wh_integral"] / 1000.0
        return "energy_kwh_meter"
    raise ValueError("No energy target found in the data.")


def load_material(args, programs) -> Optional[Dict[str, float]]:
    if args.material_csv:
        m = pd.read_csv(args.material_csv)
        cols = {c.lower(): c for c in m.columns}
        pcol = cols.get("program")
        ccol = cols.get("material_carbon") or cols.get("carbon") or cols.get("kg")
        if not pcol or not ccol:
            raise ValueError("material CSV needs columns 'program' and 'material_carbon'.")
        return {str(r[pcol]): float(r[ccol]) for _, r in m.iterrows()}
    if args.material_carbon is not None:
        return {p: float(args.material_carbon) for p in programs}
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Carbon footprint and material-vs-manufacturing LCA bridge.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/carbon")
    ap.add_argument("--emission-factor", type=float, default=0.40,
                    help="Grid emission factor in kg CO2e per kWh.")
    ap.add_argument("--material-carbon", type=float, default=None,
                    help="Embodied material carbon per part (kg), applied to all parts.")
    ap.add_argument("--material-csv", default=None,
                    help="CSV mapping program -> material_carbon (kg).")
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    ekwh = energy_kwh_column(table)
    ef = args.emission_factor
    table = table.copy()
    table["op_carbon_kg"] = table[ekwh] * ef

    # By program x operation.
    bpo = (table.groupby(["program", "operation"])
           .agg(energy_kwh=(ekwh, "sum"), op_carbon_kg=("op_carbon_kg", "sum"),
                passes=(ekwh, "size")).reset_index())
    prog_tot = bpo.groupby("program")["op_carbon_kg"].transform("sum")
    bpo["share_pct"] = 100 * bpo["op_carbon_kg"] / prog_tot
    bpo = bpo.sort_values(["program", "op_carbon_kg"], ascending=[True, False])

    # Pareto across operations.
    par = (table.groupby("operation")["op_carbon_kg"].sum()
           .sort_values(ascending=False).rename("op_carbon_kg").reset_index())
    par["share_pct"] = 100 * par["op_carbon_kg"] / par["op_carbon_kg"].sum()
    par["cumulative_pct"] = par["share_pct"].cumsum()

    # Per part (program/run) passport.
    parts = (table.groupby(["program", "source_file"])
             .agg(energy_kwh=(ekwh, "sum"), op_carbon_kg=("op_carbon_kg", "sum"),
                  operations=("operation", "nunique")).reset_index())

    material = load_material(args, parts["program"].unique())
    if material is not None:
        parts["material_carbon_kg"] = parts["program"].map(material).fillna(0.0)
        parts["total_carbon_kg"] = parts["op_carbon_kg"] + parts["material_carbon_kg"]
        parts["pct_manufacturing"] = 100 * parts["op_carbon_kg"] / parts["total_carbon_kg"]
    parts = parts.sort_values("op_carbon_kg", ascending=False)

    bpo.to_csv(out_dir / "carbon_by_operation.csv", index=False)
    par.to_csv(out_dir / "carbon_pareto.csv", index=False)
    parts.to_csv(out_dir / "carbon_passport.csv", index=False)

    mvm = None
    if material is not None:
        mvm = pd.DataFrame([{
            "total_material_kg": parts["material_carbon_kg"].sum(),
            "total_manufacturing_kg": parts["op_carbon_kg"].sum(),
            "pct_material": 100 * parts["material_carbon_kg"].sum()
                            / parts["total_carbon_kg"].sum(),
            "pct_manufacturing": 100 * parts["op_carbon_kg"].sum()
                                 / parts["total_carbon_kg"].sum(),
        }])
        mvm.to_csv(out_dir / "material_vs_manufacturing.csv", index=False)

    # plots
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(par["operation"], par["op_carbon_kg"], color="#4C78A8")
        ax.set_ylabel("operational carbon (kg CO2e)")
        ax.set_title("Carbon by operation"); plt.setp(ax.get_xticklabels(), rotation=20)
        fig.tight_layout(); fig.savefig(out_dir / "carbon_by_operation.png", dpi=130); plt.close(fig)
        if mvm is not None:
            fig, ax = plt.subplots(figsize=(5, 5))
            ax.pie([mvm["pct_material"][0], mvm["pct_manufacturing"][0]],
                   labels=["material", "manufacturing"], autopct="%1.1f%%",
                   colors=["#54A24B", "#E45756"])
            ax.set_title("Material vs manufacturing carbon")
            fig.tight_layout(); fig.savefig(out_dir / "material_vs_manufacturing.png", dpi=130); plt.close(fig)
    except Exception:
        pass

    # ---- console summary -------------------------------------------------
    total_op = table["op_carbon_kg"].sum()
    print(f"Emission factor: {ef} kg CO2e/kWh. "
          f"Total operational carbon: {total_op:.4f} kg CO2e "
          f"from {table[ekwh].sum():.4f} kWh.\n")
    print("Carbon Pareto by operation:")
    for _, r in par.iterrows():
        print(f"  {r['operation']:18s} {r['op_carbon_kg']:.4f} kg  "
              f"{r['share_pct']:5.1f}%  (cum {r['cumulative_pct']:5.1f}%)")

    if mvm is not None:
        print(f"\nMaterial vs manufacturing split (material carbon supplied):")
        print(f"  material:      {mvm['pct_material'][0]:.1f}%  "
              f"({mvm['total_material_kg'][0]:.2f} kg)")
        print(f"  manufacturing: {mvm['pct_manufacturing'][0]:.1f}%  "
              f"({mvm['total_manufacturing_kg'][0]:.4f} kg)")
        print("  => material dominates the product footprint." 
              if mvm["pct_material"][0] > 50 else
              "  => manufacturing electricity dominates here.")
    else:
        print("\nNo material carbon supplied; pass --material-carbon or --material-csv "
              "to get the material-vs-manufacturing split and carbon passport.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
