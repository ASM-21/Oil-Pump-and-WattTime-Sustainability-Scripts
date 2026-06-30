#!/usr/bin/env python3
"""
variability_analysis.py
=======================

Quantify run-to-run variability and reproducibility per operation. Answers: which
operations repeat consistently and which are noisy, how much of the spread in
energy (and other metrics) is explained by operation identity, whether operations
differ significantly, and whether any operation drifts across sequential runs
(an early tool-wear signal). Points straight at the operation_csvs folder.

Outputs (into --output, default ./ml/variability):
  variability_by_operation.csv   operation x metric: mean, std, CV, n
  variance_explained.csv          per metric: one-way ANOVA eta^2, p; Levene p; Kruskal p
  drift_by_operation.csv          per operation: Spearman(energy, run order), p
  *.png                           energy CV bar + energy-by-operation box (if matplotlib)

Usage
-----
  python variability_analysis.py --input ./operation_csvs
"""

from __future__ import annotations

import argparse
import re
import warnings
from pathlib import Path
from typing import Dict, List

_HERE = Path(__file__).resolve().parent

import numpy as np
import pandas as pd
from scipy import stats

import features as F

warnings.filterwarnings("ignore")


def run_order(series: pd.Series) -> pd.Series:
    """Numeric run order pulled from the run label (e.g. '02' or 'body02' -> 2)."""
    def num(v):
        m = re.search(r"\d+", str(v))
        return int(m.group()) if m else np.nan
    return series.map(num)


def pick_metrics(table: pd.DataFrame) -> List[str]:
    """Energy + duration + every channel's mean as the metrics to profile."""
    metrics = []
    if "energy_kwh_meter" in table:
        metrics.append("energy_kwh_meter")
    elif "energy_wh_integral" in table:
        metrics.append("energy_wh_integral")
    if "duration_s" in table:
        metrics.append("duration_s")
    metrics += [c for c in table.columns if c.endswith("__mean")]
    return metrics


def variability_table(table: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
    rows = []
    for op, g in table.groupby("operation"):
        for m in metrics:
            vals = pd.to_numeric(g[m], errors="coerce").dropna()
            if vals.empty:
                continue
            mean = vals.mean()
            std = vals.std(ddof=1) if len(vals) > 1 else 0.0
            rows.append({
                "operation": op, "metric": m, "n": len(vals),
                "mean": float(mean), "std": float(std),
                "cv": float(std / mean) if mean else np.nan,
            })
    return pd.DataFrame(rows)


def variance_explained(table: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
    """For each metric: how much variance is between operations, and do they differ."""
    rows = []
    for m in metrics:
        groups = [pd.to_numeric(g[m], errors="coerce").dropna().values
                  for _, g in table.groupby("operation")]
        groups = [a for a in groups if len(a) > 1]
        if len(groups) < 2:
            continue
        allv = np.concatenate(groups)
        grand = allv.mean()
        ss_between = sum(len(a) * (a.mean() - grand) ** 2 for a in groups)
        ss_total = ((allv - grand) ** 2).sum()
        eta2 = ss_between / ss_total if ss_total else np.nan
        try:
            f_p = stats.f_oneway(*groups).pvalue
        except Exception:
            f_p = np.nan
        try:
            lev_p = stats.levene(*groups).pvalue   # equal spread across operations?
        except Exception:
            lev_p = np.nan
        try:
            kw_p = stats.kruskal(*groups).pvalue   # non-parametric difference
        except Exception:
            kw_p = np.nan
        rows.append({"metric": m, "eta_squared": round(float(eta2), 4),
                     "anova_p": f_p, "levene_p": lev_p, "kruskal_p": kw_p})
    return pd.DataFrame(rows).sort_values("eta_squared", ascending=False)


def drift_table(table: pd.DataFrame, energy_col: str) -> pd.DataFrame:
    """
    Spearman correlation of energy with run order, per (operation, program).
    Run numbers reset per program (body01_p1 and body01_p2 are different parts), so
    drift is only meaningful within a single program's run sequence.
    """
    rows = []
    tmp = table.assign(_run_order=run_order(table["run"]))
    for (op, prog), g in tmp.groupby(["operation", "program"]):
        gg = g.dropna(subset=["_run_order", energy_col])
        if gg["_run_order"].nunique() < 4:
            continue
        r, p = stats.spearmanr(gg["_run_order"], pd.to_numeric(gg[energy_col]))
        rows.append({"operation": op, "program": prog,
                     "spearman_r": round(float(r), 3), "p": float(p),
                     "n_runs": gg["_run_order"].nunique(),
                     "note": "drift" if p < 0.05 else ""})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("spearman_r", key=lambda s: s.abs(), ascending=False)


def maybe_plot(var_tab, table, energy_col, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    cv = (var_tab[var_tab["metric"] == energy_col]
          .sort_values("cv"))
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(cv) + 1.5))
    ax.barh(cv["operation"], cv["cv"], color="#4C78A8")
    ax.set_xlabel("energy CV (lower = more reproducible)")
    ax.set_title("Run-to-run energy variability by operation")
    fig.tight_layout(); fig.savefig(out_dir / "energy_cv_by_operation.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ops = sorted(table["operation"].unique())
    ax.boxplot([pd.to_numeric(table[table["operation"] == o][energy_col]).dropna()
                for o in ops], labels=ops)
    ax.set_ylabel(energy_col); ax.set_title("Energy distribution by operation")
    plt.setp(ax.get_xticklabels(), rotation=20)
    fig.tight_layout(); fig.savefig(out_dir / "energy_box_by_operation.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run-to-run variability and reproducibility per operation.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default=str(_HERE / "operation_csvs"))
    ap.add_argument("--output", default=str(_HERE / "ml/variability"))
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    energy_col = "energy_kwh_meter" if "energy_kwh_meter" in table else "energy_wh_integral"

    metrics = pick_metrics(table)
    var_tab = variability_table(table, metrics)
    var_exp = variance_explained(table, metrics)
    drift = drift_table(table, energy_col)

    var_tab.to_csv(out_dir / "variability_by_operation.csv", index=False)
    var_exp.to_csv(out_dir / "variance_explained.csv", index=False)
    drift.to_csv(out_dir / "drift_by_operation.csv", index=False)
    maybe_plot(var_tab, table, energy_col, out_dir)

    # ---- console summary -------------------------------------------------
    energy_cv = (var_tab[var_tab["metric"] == energy_col]
                 .sort_values("cv")[["operation", "cv", "n"]])
    print(f"Energy reproducibility by operation ({energy_col}, CV = std/mean):")
    for _, r in energy_cv.iterrows():
        print(f"  {r['operation']:18s} CV={r['cv']:.3f}  (n={int(r['n'])})")
    if len(energy_cv) > 1:
        print(f"  Most reproducible: {energy_cv.iloc[0]['operation']}; "
              f"noisiest: {energy_cv.iloc[-1]['operation']}.")

    print("\nVariance explained by operation identity (eta^2, top metrics):")
    for _, r in var_exp.head(6).iterrows():
        sig = "diff" if (r["kruskal_p"] is not None and r["kruskal_p"] < 0.05) else "n.s."
        print(f"  {r['metric']:28s} eta^2={r['eta_squared']:.3f}  ({sig} across operations)")

    levene_sig = var_exp[(var_exp["levene_p"].notna()) & (var_exp["levene_p"] < 0.05)]
    if not levene_sig.empty:
        print(f"\nMetrics where spread differs significantly across operations "
              f"(variability is systematic): {list(levene_sig['metric'].head(5))}")

    drifting = drift[drift["note"] == "drift"] if not drift.empty else drift
    if not drift.empty and not drifting.empty:
        print("\nOperations with significant energy drift across runs (possible wear):")
        for _, r in drifting.iterrows():
            direction = "rising" if r["spearman_r"] > 0 else "falling"
            print(f"  {r['operation']:18s} in {r['program']:8s} "
                  f"Spearman r={r['spearman_r']:+.2f} ({direction}, {int(r['n_runs'])} runs)")
    else:
        print("\nNo significant within-program energy drift detected.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
