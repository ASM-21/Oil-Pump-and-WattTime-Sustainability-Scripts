#!/usr/bin/env python3
"""
quality_check.py
================

Data-quality gate for the per-operation CSV folder, run before you trust any model.
Points straight at the folder from split_operations.py.

It answers: which operations have too few or too short passes to model reliably,
which sensor channels are dead or constant, and which individual passes look
anomalous (possible sensor faults or mis-splits). The last one uses an
IsolationForest per operation, so "something in the ML" flags passes that do not
look like their peers.

Why it matters: short passes make std/slope/auc features unreliable, and operations
with few passes give unstable cross-validation. estimate_energy.py and
classify_operations.py drop or warn on these; this script tells you the thresholds
to set and why.

Outputs (into --output, default ./ml/quality):
  quality_report.csv         per-operation: passes, runs, length stats, flags
  flagged_short_passes.csv    individual passes below --min-samples
  channel_quality.csv         per-channel missing / constant / zero rates
  outlier_passes.csv          IsolationForest anomaly flags per operation

Usage
-----
  python quality_check.py --input ./operation_csvs
  python quality_check.py --input ./operation_csvs --min-samples 6 --min-passes 6
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import List

_HERE = Path(__file__).resolve().parent

import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

import features as F

warnings.filterwarnings("ignore")


def per_operation_report(table: pd.DataFrame, raw: pd.DataFrame,
                         min_samples: int, min_passes: int) -> pd.DataFrame:
    rows = []
    for op, g in table.groupby("operation"):
        sizes = g["n_samples"]
        durs = g["duration_s"]
        n_short = int((sizes < min_samples).sum())
        flags = []
        if len(g) < min_passes:
            flags.append("few_passes")
        if sizes.median() < min_samples:
            flags.append("short_passes")
        if n_short > 0 and "short_passes" not in flags:
            flags.append("some_short_passes")
        if (sizes <= 1).any():
            flags.append("single_sample_pass")
        rows.append({
            "operation": op,
            "n_passes": len(g),
            "n_runs": g["source_file"].nunique(),
            "samples_min": int(sizes.min()),
            "samples_median": float(sizes.median()),
            "samples_max": int(sizes.max()),
            "duration_median_s": round(float(durs.median()), 2),
            "total_samples": int(sizes.sum()),
            "n_short_passes": n_short,
            "flags": ",".join(flags) if flags else "ok",
        })
    out = pd.DataFrame(rows).sort_values("n_passes")
    return out


def flag_short_passes(table: pd.DataFrame, min_samples: int) -> pd.DataFrame:
    short = table[table["n_samples"] < min_samples]
    cols = ["operation", "program", "run", "source_file", "segment_id",
            "n_samples", "duration_s"]
    return short[[c for c in cols if c in short.columns]].sort_values("n_samples")


def channel_quality(raw: pd.DataFrame) -> pd.DataFrame:
    channels = F.find_numeric_channels(raw)
    rows = []
    n = len(raw)
    for ch in channels:
        s = pd.to_numeric(raw[ch], errors="coerce")
        nun = int(s.nunique(dropna=True))
        miss = float(s.isna().mean())
        zero = float((s == 0).mean())
        flag = []
        if miss > 0.20:
            flag.append("mostly_missing")
        if nun <= 1:
            flag.append("constant")
        if zero > 0.95:
            flag.append("mostly_zero")
        rows.append({
            "channel": ch, "missing_rate": round(miss, 3),
            "zero_rate": round(zero, 3), "n_unique": nun,
            "flag": ",".join(flag) if flag else "ok",
        })
    return pd.DataFrame(rows).sort_values("missing_rate", ascending=False)


def detect_outliers(table: pd.DataFrame, feature_cols: List[str],
                    min_for_if: int, contamination) -> pd.DataFrame:
    """IsolationForest per operation: flag passes unlike their peers."""
    rows = []
    for op, g in table.groupby("operation"):
        if len(g) < min_for_if:
            continue
        X = SimpleImputer(strategy="median").fit_transform(g[feature_cols])
        X = StandardScaler().fit_transform(X)
        iso = IsolationForest(contamination=contamination, random_state=0)
        pred = iso.fit_predict(X)            # -1 outlier, 1 inlier
        score = iso.score_samples(X)          # lower = more anomalous
        sub = g.copy()
        sub["anomaly_score"] = score
        sub["is_outlier"] = (pred == -1)
        keep = ["operation", "source_file", "run", "segment_id", "n_samples",
                "anomaly_score", "is_outlier"]
        rows.append(sub[[c for c in keep if c in sub.columns]])
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["is_outlier", "anomaly_score"], ascending=[False, True])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Quality check the per-operation CSV folder before modeling.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--input", default=str(_HERE / "operation_csvs"))
    ap.add_argument("--output", default=str(_HERE / "ml/quality"))
    ap.add_argument("--min-samples", type=int, default=6,
                    help="Passes below this many samples are flagged as too short.")
    ap.add_argument("--min-passes", type=int, default=6,
                    help="Operations below this many passes are flagged as sparse.")
    ap.add_argument("--min-for-outlier", type=int, default=8,
                    help="Minimum passes before running IsolationForest on an operation.")
    ap.add_argument("--contamination", default="0.05",
                    help="IsolationForest contamination ('auto' or a float like 0.05).")
    args = ap.parse_args()

    contam = args.contamination
    if contam != "auto":
        contam = float(contam)

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)

    raw = F.add_elapsed(F.load_all(args.input))
    table, groups = F.prepare(args.input, "segment")
    feat_cols = F.feature_columns(table)

    report = per_operation_report(table, raw, args.min_samples, args.min_passes)
    short = flag_short_passes(table, args.min_samples)
    chan = channel_quality(raw)
    outliers = detect_outliers(table, feat_cols, args.min_for_outlier, contam)

    report.to_csv(out_dir / "quality_report.csv", index=False)
    short.to_csv(out_dir / "flagged_short_passes.csv", index=False)
    chan.to_csv(out_dir / "channel_quality.csv", index=False)
    if not outliers.empty:
        outliers.to_csv(out_dir / "outlier_passes.csv", index=False)

    # ---- console summary -------------------------------------------------
    print("Per-operation quality:")
    for _, r in report.iterrows():
        print(f"  {r['operation']:18s} passes={r['n_passes']:3d} runs={r['n_runs']:3d} "
              f"samples(min/med/max)={r['samples_min']}/{r['samples_median']:.0f}/{r['samples_max']}"
              f"  [{r['flags']}]")

    imbalance = report["n_passes"].max() / max(report["n_passes"].min(), 1)
    print(f"\nClass imbalance (max/min passes): {imbalance:.1f}x")

    flagged_ops = report[report["flags"] != "ok"]["operation"].tolist()
    if flagged_ops:
        print(f"Operations needing care: {flagged_ops}")
    if not short.empty:
        print(f"Short passes (< {args.min_samples} samples): {len(short)} "
              f"across {short['operation'].nunique()} operations.")

    bad_chan = chan[chan["flag"] != "ok"]
    if not bad_chan.empty:
        print("\nChannels flagged:")
        for _, r in bad_chan.iterrows():
            print(f"  {r['channel']:28s} {r['flag']} "
                  f"(missing {r['missing_rate']:.0%}, {r['n_unique']} unique)")
    else:
        print("\nNo channel quality issues.")

    if not outliers.empty:
        n_out = int(outliers["is_outlier"].sum())
        print(f"\nAnomalous passes flagged by IsolationForest: {n_out}")
        for _, r in outliers[outliers["is_outlier"]].head(8).iterrows():
            print(f"  {r['operation']:18s} {r['source_file']} seg {r['segment_id']} "
                  f"(score {r['anomaly_score']:.3f}, {r['n_samples']} samples)")
    else:
        print("\nNot enough passes per operation for outlier detection.")

    # ---- recommendations -------------------------------------------------
    print("\nRecommendations:")
    if flagged_ops:
        print(f"  - Treat {flagged_ops} as low-confidence; gather more runs or report "
              f"them with wider error bars.")
    print(f"  - For modeling, filter short passes: add --min-samples {args.min_samples} "
          f"to estimate_energy.py / classify_operations.py.")
    if imbalance >= 3:
        print("  - Imbalance is high; prefer macro-F1 (classify) and per-operation "
              "metrics (energy) over pooled accuracy.")
    print(f"\nWrote reports to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
