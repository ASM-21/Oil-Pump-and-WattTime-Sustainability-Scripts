#!/usr/bin/env python3
"""
time_series_analysis.py
=======================

Sample-level (1 Hz) analysis of operation passes, complementing the per-pass
aggregate scripts. Points straight at the operation_csvs folder. Three parts:

  1. Power signatures: the characteristic shape of each operation over normalized
     pass time (mean +/- envelope), so you can see the ramp / cut / retract profile.
  2. Phase segmentation: splits each pass into ramp-up / steady / ramp-down by power
     level and reports phase durations and energy shares per operation.
  3. Early prediction: using only the first X% of a pass, how well can you identify
     the operation (macro-F1) and predict its full energy (R2). The "how soon can we
     tell" curve, relevant to real-time monitoring.

Early prediction is a forecasting task, so it uses all channels including power
(observing partial power to predict the eventual operation/energy is not circular).

Outputs (into --output, default ./ml/timeseries):
  power_signatures.csv     operation x phase_frac x channel: mean, std
  phase_segmentation.csv   operation: mean ramp/steady/retract durations + energy shares
  early_prediction.csv     fraction x task: score (macro-F1 for operation, R2 for energy)
  *.png                    signatures, early-prediction curves, phase composition

Usage
-----
  python time_series_analysis.py --input ./operation_csvs
  python time_series_analysis.py --input ./operation_csvs --grid 30 --min-samples 4
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import f1_score, r2_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, cross_val_predict

import features as F

warnings.filterwarnings("ignore")

_trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


# --- part 1: power signatures ----------------------------------------------

def resample_pass(elapsed: np.ndarray, values: np.ndarray, grid: int) -> np.ndarray:
    """Interpolate a pass onto a common 0..1 normalized-time grid."""
    span = elapsed.max() - elapsed.min()
    frac = (elapsed - elapsed.min()) / span if span > 0 else np.zeros_like(elapsed)
    xs = np.linspace(0, 1, grid)
    return np.interp(xs, frac, values)


def power_signatures(sample, channels, grid, min_samples) -> pd.DataFrame:
    xs = np.linspace(0, 1, grid)
    rows = []
    for op, og in sample.groupby("operation"):
        for ch in channels:
            stacked = []
            for _, g in og.groupby(["source_file", "segment_id"]):
                g = g.sort_values("elapsed_s")
                if len(g) < min_samples:
                    continue
                y = pd.to_numeric(g[ch], errors="coerce").to_numpy(dtype=float)
                e = g["elapsed_s"].to_numpy(dtype=float)
                if np.isnan(y).all():
                    continue
                stacked.append(resample_pass(e, np.nan_to_num(y, nan=np.nanmean(y)), grid))
            if not stacked:
                continue
            arr = np.vstack(stacked)
            for k, xf in enumerate(xs):
                rows.append({"operation": op, "channel": ch, "phase_frac": round(float(xf), 3),
                             "mean": float(arr[:, k].mean()), "std": float(arr[:, k].std()),
                             "n_passes": arr.shape[0]})
    return pd.DataFrame(rows)


# --- part 2: phase segmentation --------------------------------------------

def segment_phases(elapsed: np.ndarray, power: np.ndarray) -> Dict[str, float]:
    t, p = elapsed, power
    dur = t.max() - t.min()
    rng = p.max() - p.min()
    if dur <= 0 or rng < 1e-9:
        return {"ramp_up_s": 0.0, "steady_s": float(dur), "ramp_down_s": 0.0,
                "e_ramp_up": 0.0, "e_steady": 0.0, "e_ramp_down": 0.0}
    thr = p.min() + 0.5 * rng
    above = np.where(p >= thr)[0]
    s0, s1 = (above[0], above[-1]) if above.size else (len(p) // 2, len(p) // 2)

    def energy(a, b):
        if b <= a:
            return 0.0
        return float(_trapz(p[a:b + 1], t[a:b + 1]) / 3600.0 / 1000.0)

    return {
        "ramp_up_s": float(t[s0] - t[0]),
        "steady_s": float(t[s1] - t[s0]),
        "ramp_down_s": float(t[-1] - t[s1]),
        "e_ramp_up": energy(0, s0),
        "e_steady": energy(s0, s1),
        "e_ramp_down": energy(s1, len(p) - 1),
    }


def phase_table(sample, power_ch, min_samples) -> pd.DataFrame:
    recs = []
    for (op, sf, seg), g in sample.groupby(["operation", "source_file", "segment_id"]):
        g = g.sort_values("elapsed_s")
        if len(g) < min_samples:
            continue
        ph = segment_phases(g["elapsed_s"].to_numpy(float),
                            pd.to_numeric(g[power_ch], errors="coerce").to_numpy(float))
        ph["operation"] = op
        recs.append(ph)
    df = pd.DataFrame(recs)
    if df.empty:
        return df
    agg = df.groupby("operation").mean(numeric_only=True)
    tot_t = agg[["ramp_up_s", "steady_s", "ramp_down_s"]].sum(axis=1)
    tot_e = agg[["e_ramp_up", "e_steady", "e_ramp_down"]].sum(axis=1)
    for ph in ("ramp_up", "steady", "ramp_down"):
        agg[f"{ph}_time_pct"] = 100 * agg[f"{ph}_s"] / tot_t
        agg[f"{ph}_energy_pct"] = 100 * agg[f"e_{ph}"] / tot_e.replace(0, np.nan)
    return agg.reset_index()


# --- part 3: early prediction ----------------------------------------------

def early_features(g: pd.DataFrame, channels: List[str]) -> Dict[str, float]:
    x = g["elapsed_s"].to_numpy(float)
    feats = {"obs_duration_s": float(x.max() - x.min()), "n_obs": float(len(g))}
    for ch in channels:
        y = pd.to_numeric(g[ch], errors="coerce").to_numpy(float)
        valid = ~np.isnan(y)
        yv, xv = y[valid], x[valid]
        if yv.size == 0:
            for s in ("mean", "std", "min", "max", "range", "slope", "last"):
                feats[f"{ch}__{s}"] = np.nan
            continue
        slope = float(np.polyfit(xv, yv, 1)[0]) if (yv.size > 1 and np.ptp(xv) > 0) else 0.0
        feats[f"{ch}__mean"] = float(yv.mean()); feats[f"{ch}__std"] = float(yv.std())
        feats[f"{ch}__min"] = float(yv.min()); feats[f"{ch}__max"] = float(yv.max())
        feats[f"{ch}__range"] = float(np.ptp(yv)); feats[f"{ch}__slope"] = slope
        feats[f"{ch}__last"] = float(yv[-1])
    return feats


def build_early_matrix(sample, channels, fraction):
    rows, keys = [], []
    for (sf, seg), g in sample.groupby(["source_file", "segment_id"]):
        g = g.sort_values("elapsed_s")
        dur = g["elapsed_s"].max()
        cut = g[g["elapsed_s"] <= fraction * dur] if dur > 0 else g
        if len(cut) < 2:
            continue
        rows.append(early_features(cut, channels))
        keys.append((sf, seg))
    return pd.DataFrame(rows), keys


def grouped_scores(X, y_op, y_en, groups, min_class):
    """Macro-F1 (operation) and R2 (energy) via run-grouped CV on the same matrix."""
    Xi = SimpleImputer(strategy="median").fit_transform(X)
    out = {}
    # classification
    vc = y_op.value_counts()
    keep = y_op.isin(vc[vc >= min_class].index).values
    if keep.sum() > 0 and y_op[keep].nunique() > 1:
        yk, gk, Xk = y_op[keep], groups[keep], Xi[keep]
        min_cg = (pd.DataFrame({"y": yk.values, "g": gk.values})
                  .groupby("y")["g"].nunique().min())
        n = int(min(5, gk.nunique(), max(min_cg, 2)))
        try:
            pred = cross_val_predict(RandomForestClassifier(n_estimators=200, random_state=0),
                                     Xk, yk, groups=gk, cv=StratifiedGroupKFold(n_splits=n))
            out["operation_macro_f1"] = f1_score(yk, pred, average="macro")
        except Exception:
            out["operation_macro_f1"] = np.nan
    else:
        out["operation_macro_f1"] = np.nan
    # regression
    n = int(min(5, groups.nunique()))
    try:
        pred = cross_val_predict(RandomForestRegressor(n_estimators=200, random_state=0),
                                 Xi, y_en, groups=groups, cv=GroupKFold(n_splits=n))
        out["energy_r2"] = r2_score(y_en, pred)
    except Exception:
        out["energy_r2"] = np.nan
    return out


def early_prediction(sample, channels, fractions, lookup, min_class) -> pd.DataFrame:
    rows = []
    for f in fractions:
        X, keys = build_early_matrix(sample, channels, f)
        if X.empty:
            continue
        meta = pd.DataFrame([lookup[k] for k in keys])
        scores = grouped_scores(X, meta["operation"], meta["energy"], meta["group"], min_class)
        rows.append({"fraction": round(f, 2), **scores,
                     "n_passes": len(keys)})
    return pd.DataFrame(rows)


# --- plotting ---------------------------------------------------------------

def maybe_plot(sig, phases, early, power_ch, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    # Power signatures (mean + envelope) per operation.
    ps = sig[sig["channel"] == power_ch]
    if not ps.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        for op, g in ps.groupby("operation"):
            g = g.sort_values("phase_frac")
            ax.plot(g["phase_frac"], g["mean"], label=op, lw=1.6)
            ax.fill_between(g["phase_frac"], g["mean"] - g["std"], g["mean"] + g["std"], alpha=0.12)
        ax.set_xlabel("normalized pass time"); ax.set_ylabel(power_ch)
        ax.set_title("Power signatures by operation"); ax.legend(fontsize=8)
        fig.tight_layout(); fig.savefig(out_dir / "power_signatures.png", dpi=130); plt.close(fig)

    # Early prediction curves.
    if not early.empty:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(early["fraction"] * 100, early["operation_macro_f1"], marker="o", label="operation macro-F1")
        ax.plot(early["fraction"] * 100, early["energy_r2"], marker="s", label="energy R2")
        ax.set_xlabel("% of pass observed"); ax.set_ylabel("score"); ax.set_ylim(0, 1.02)
        ax.set_title("Early prediction: how soon can we tell?"); ax.legend()
        fig.tight_layout(); fig.savefig(out_dir / "early_prediction.png", dpi=130); plt.close(fig)

    # Phase time composition.
    if not phases.empty and "ramp_up_time_pct" in phases:
        fig, ax = plt.subplots(figsize=(8, 4))
        bottom = np.zeros(len(phases))
        for ph in ("ramp_up", "steady", "ramp_down"):
            ax.bar(phases["operation"], phases[f"{ph}_time_pct"], bottom=bottom, label=ph)
            bottom += phases[f"{ph}_time_pct"].values
        ax.set_ylabel("% of pass time"); ax.set_title("Phase composition by operation")
        ax.legend(fontsize=8); plt.setp(ax.get_xticklabels(), rotation=20)
        fig.tight_layout(); fig.savefig(out_dir / "phase_composition.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sample-level signatures, phase segmentation, and early prediction.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/timeseries")
    ap.add_argument("--grid", type=int, default=25, help="Points in the normalized-time grid.")
    ap.add_argument("--min-samples", type=int, default=4,
                    help="Skip passes shorter than this for signatures/phases.")
    ap.add_argument("--min-per-class", type=int, default=4)
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)

    sample, _ = F.prepare(args.input, "sample")
    seg, _ = F.prepare(args.input, "segment")
    channels = [c for c in F.find_numeric_channels(sample) if c != "elapsed_s"]
    power_ch, _ = F.find_energy_channels(channels)
    if power_ch is None:
        power_ch = channels[0]
    ecol = "energy_kwh_meter" if "energy_kwh_meter" in seg else "energy_wh_integral"

    # per-pass lookup: (source_file, segment_id) -> operation, group, full energy
    lookup = {(r["source_file"], r["segment_id"]):
              {"operation": r["operation"], "group": r["source_file"], "energy": r[ecol]}
              for _, r in seg.iterrows()}

    sig = power_signatures(sample, channels, args.grid, args.min_samples)
    phases = phase_table(sample, power_ch, args.min_samples)
    fractions = [round(x, 2) for x in np.arange(0.1, 1.01, 0.1)]
    early = early_prediction(sample, channels, fractions, lookup, args.min_per_class)

    sig.to_csv(out_dir / "power_signatures.csv", index=False)
    phases.to_csv(out_dir / "phase_segmentation.csv", index=False)
    early.to_csv(out_dir / "early_prediction.csv", index=False)
    maybe_plot(sig, phases, early, power_ch, out_dir)

    # ---- console summary -------------------------------------------------
    print(f"Sample-level analysis. Power channel: {power_ch}. "
          f"Channels: {len(channels)}. Passes: "
          f"{sample.groupby(['source_file','segment_id']).ngroups}.\n")

    if not phases.empty and "steady_time_pct" in phases:
        print("Phase composition (mean % of pass time):")
        for _, r in phases.iterrows():
            print(f"  {r['operation']:18s} ramp-up {r['ramp_up_time_pct']:4.0f}%  "
                  f"steady {r['steady_time_pct']:4.0f}%  ramp-down {r['ramp_down_time_pct']:4.0f}%")

    if not early.empty:
        full = early.iloc[-1]
        print(f"\nEarly prediction (full pass: operation F1={full['operation_macro_f1']:.2f}, "
              f"energy R2={full['energy_r2']:.2f}):")
        for _, r in early.iterrows():
            print(f"  first {int(r['fraction']*100):3d}%  operationF1={r['operation_macro_f1']:.2f}  "
                  f"energyR2={r['energy_r2']:.2f}")
        # earliest fraction reaching 90% of full-pass score
        for task, col in (("operation", "operation_macro_f1"), ("energy", "energy_r2")):
            tgt = 0.9 * full[col]
            hit = early[early[col] >= tgt]
            if not hit.empty and full[col] > 0:
                print(f"  => {task}: 90% of full skill reached after "
                      f"{int(hit.iloc[0]['fraction']*100)}% of the pass.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
