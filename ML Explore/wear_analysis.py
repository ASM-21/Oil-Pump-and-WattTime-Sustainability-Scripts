#!/usr/bin/env python3
"""
wear_analysis.py
================

Condition-monitoring view of the data: detect degradation across sequential runs of
the same operation. Builds on the drift signal with proper trend tests, changepoint
detection, statistical control limits, and a crude remaining-useful-life proxy.
Points straight at the operation_csvs folder.

For each (operation, program) and each indicator (energy plus every sensor mean), over
the run sequence it reports:
  - Mann-Kendall / Kendall-tau monotonic trend (tau, p, direction)
  - linear slope per run and percent change over the observed runs
  - a CUSUM changepoint (the run where the mean shifts), if any
  - control limits (baseline mean +/- 3 sigma) and out-of-control run count
And for rising wear-type indicators (vibration / temperature / load), an estimated
number of runs until the indicator reaches a failure threshold.

Outputs (into --output, default ./ml/wear):
  wear_trends.csv     operation x program x indicator: tau, p, slope, %change, changepoint, OOC
  rul_estimates.csv    estimated runs-to-threshold for rising wear indicators
  *.png               indicator-vs-run plots with trend line and control limits

Usage
-----
  python wear_analysis.py --input ./operation_csvs
  python wear_analysis.py --input ./operation_csvs --rul-threshold 1.5
"""

from __future__ import annotations

import argparse
import re
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

import features as F

warnings.filterwarnings("ignore")

WEAR_PATTERN = re.compile(r"a_rms|a_peak|crest|temp|_load|vib", re.IGNORECASE)


def run_num(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d+)").iloc[:, 0].astype(float)


def cusum_changepoint(x: np.ndarray, k_sigma=0.5, h_sigma=4.0) -> Optional[int]:
    """Tabular CUSUM; returns index of first out-of-control point or None."""
    if len(x) < 4:
        return None
    base = x[: max(2, len(x) // 2)]
    mu, sd = base.mean(), (x.std() or 1.0)
    k, h = k_sigma * sd, h_sigma * sd
    sp = sm = 0.0
    for i, v in enumerate(x):
        sp = max(0.0, sp + (v - mu) - k)
        sm = min(0.0, sm + (v - mu) + k)
        if sp > h or sm < -h:
            return i
    return None


def control_limits(x: np.ndarray):
    base = x[: max(2, len(x) // 2)]
    mu, sd = base.mean(), base.std(ddof=1) if len(base) > 1 else 0.0
    ucl, lcl = mu + 3 * sd, mu - 3 * sd
    ooc = int(np.sum((x > ucl) | (x < lcl)))
    return mu, ucl, lcl, ooc


def indicator_columns(table: pd.DataFrame, energy_col: str) -> List[str]:
    return [energy_col] + [c for c in table.columns if c.endswith("__mean")]


def analyze(table, indicators) -> pd.DataFrame:
    rows = []
    tmp = table.assign(_rn=run_num(table["run"]))
    for (op, prog), g in tmp.groupby(["operation", "program"]):
        g = g.dropna(subset=["_rn"]).sort_values("_rn")
        # collapse to one value per run (mean if multiple passes per run)
        for ind in indicators:
            s = g.groupby("_rn")[ind].mean().dropna()
            if s.size < 4:
                continue
            runs = s.index.values.astype(float)
            vals = s.values.astype(float)
            tau, p = stats.kendalltau(runs, vals)
            slope = float(np.polyfit(runs, vals, 1)[0]) if np.ptp(runs) > 0 else 0.0
            base = vals[: max(2, len(vals) // 2)].mean()
            pct = 100 * slope * (runs.max() - runs.min()) / base if base else np.nan
            cp = cusum_changepoint(vals)
            mu, ucl, lcl, ooc = control_limits(vals)
            trend = ("rising" if (tau > 0 and p < 0.05)
                     else "falling" if (tau < 0 and p < 0.05) else "none")
            rows.append({
                "operation": op, "program": prog, "indicator": ind, "n_runs": int(s.size),
                "tau": round(float(tau), 3) if tau == tau else np.nan,
                "p": float(p) if p == p else np.nan,
                "slope_per_run": slope, "pct_change": round(float(pct), 1) if pct == pct else np.nan,
                "changepoint_run": float(runs[cp]) if cp is not None else np.nan,
                "n_out_of_control": ooc, "trend": trend,
            })
    return pd.DataFrame(rows)


def rul_estimates(trends: pd.DataFrame, table, threshold_mult: float) -> pd.DataFrame:
    rows = []
    tmp = table.assign(_rn=run_num(table["run"]))
    wear = trends[(trends["trend"] == "rising")
                  & (trends["indicator"].str.contains(WEAR_PATTERN))]
    for _, r in wear.iterrows():
        g = tmp[(tmp["operation"] == r["operation"]) & (tmp["program"] == r["program"])]
        s = g.groupby("_rn")[r["indicator"]].mean().dropna().sort_index()
        if s.size < 4 or r["slope_per_run"] <= 0:
            continue
        baseline = s.values[: max(2, len(s) // 2)].mean()
        current = s.values[-1]
        target = baseline * threshold_mult
        if current >= target:
            runs_left = 0.0
        else:
            runs_left = (target - current) / r["slope_per_run"]
        rows.append({
            "operation": r["operation"], "program": r["program"], "indicator": r["indicator"],
            "current": round(float(current), 2), "baseline": round(float(baseline), 2),
            "threshold": round(float(target), 2),
            "runs_to_threshold": round(float(runs_left), 1),
        })
    return pd.DataFrame(rows).sort_values("runs_to_threshold") if rows else pd.DataFrame()


def maybe_plot(trends, table, out_dir, top=4):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    tmp = table.assign(_rn=run_num(table["run"]))
    sig = trends[trends["trend"] != "none"].copy()
    sig["abs_tau"] = sig["tau"].abs()
    sig = sig.sort_values("abs_tau", ascending=False).head(top)
    if sig.empty:
        return
    n = len(sig)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 3.4), squeeze=False)
    for ax, (_, r) in zip(axes[0], sig.iterrows()):
        g = tmp[(tmp["operation"] == r["operation"]) & (tmp["program"] == r["program"])]
        s = g.groupby("_rn")[r["indicator"]].mean().dropna().sort_index()
        x, y = s.index.values, s.values
        ax.plot(x, y, "o-", color="#4C78A8")
        if np.ptp(x) > 0:
            fit = np.poly1d(np.polyfit(x, y, 1))
            ax.plot(x, fit(x), "--", color="#E45756", lw=1)
        mu, ucl, lcl, _ = control_limits(y)
        ax.axhline(ucl, ls=":", color="grey", lw=0.8); ax.axhline(lcl, ls=":", color="grey", lw=0.8)
        ax.set_title(f"{r['operation']}/{r['program']}\n{r['indicator']}", fontsize=8)
        ax.set_xlabel("run")
    fig.suptitle("Degradation trends with control limits", y=1.02)
    fig.tight_layout(); fig.savefig(out_dir / "wear_trends.png", dpi=130, bbox_inches="tight"); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Tool-wear / degradation analysis across runs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/wear")
    ap.add_argument("--rul-threshold", type=float, default=1.5,
                    help="Failure threshold as a multiple of baseline for the RUL proxy.")
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    ecol = "energy_kwh_meter" if "energy_kwh_meter" in table else "energy_wh_integral"

    trends = analyze(table, indicator_columns(table, ecol))
    if trends.empty:
        print("Not enough runs per operation to assess trends (need >= 4).")
        return 1
    rul = rul_estimates(trends, table, args.rul_threshold)

    trends.sort_values(["operation", "program", "indicator"]).to_csv(
        out_dir / "wear_trends.csv", index=False)
    if not rul.empty:
        rul.to_csv(out_dir / "rul_estimates.csv", index=False)
    maybe_plot(trends, table, out_dir)

    # ---- console summary -------------------------------------------------
    rising = trends[trends["trend"] == "rising"].sort_values("tau", ascending=False)
    falling = trends[trends["trend"] == "falling"].sort_values("tau")
    print(f"Significant degradation (rising) trends: {len(rising)}; "
          f"falling: {len(falling)} (of {len(trends)} series).\n")
    if not rising.empty:
        print("Top rising trends (possible wear):")
        for _, r in rising.head(8).iterrows():
            print(f"  {r['operation']:14s} {r['program']:8s} {r['indicator']:28s} "
                  f"tau={r['tau']:+.2f}  +{r['pct_change']:.0f}% over {int(r['n_runs'])} runs")

    cps = trends.dropna(subset=["changepoint_run"])
    if not cps.empty:
        print(f"\nChangepoints detected (CUSUM) in {len(cps)} series, e.g.:")
        for _, r in cps.head(5).iterrows():
            print(f"  {r['operation']}/{r['program']} {r['indicator']}: shift near run "
                  f"{int(r['changepoint_run'])}")

    if not rul.empty:
        print(f"\nRemaining-useful-life proxy (runs until {args.rul_threshold}x baseline):")
        for _, r in rul.head(8).iterrows():
            print(f"  {r['operation']:14s} {r['program']:8s} {r['indicator']:24s} "
                  f"~{r['runs_to_threshold']:.0f} runs (now {r['current']}, limit {r['threshold']})")
    else:
        print("\nNo rising wear indicators with a usable RUL extrapolation.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
