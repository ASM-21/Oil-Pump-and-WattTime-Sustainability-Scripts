#!/usr/bin/env python3
"""
sensor_study.py
===============

Work out which sensors actually matter and how few you could instrument with.
For both tasks (identify the operation, estimate energy) it ranks channels by
mutual information, finds redundant channels, and greedily builds a minimal sensor
set, reporting how performance grows as sensors are added. Points straight at the
operation_csvs folder.

This is the practical "if I could only keep N sensors, which ones" question, useful
for instrumenting a real line cheaply.

Outputs (into --output, default ./ml/sensor_study):
  mutual_info_operation.csv     channel -> MI with operation label
  mutual_info_energy.csv        channel -> MI with energy (energy sensors excluded)
  sensor_redundancy.csv         highly correlated channel pairs (|r| > threshold)
  minimal_set_operation.csv     greedy add order: k sensors -> macro-F1
  minimal_set_energy.csv        greedy add order: k sensors -> R2
  *.png                         MI bars + score-vs-#sensors curves (if matplotlib)

Usage
-----
  python sensor_study.py --input ./operation_csvs
  python sensor_study.py --input ./operation_csvs --corr-threshold 0.95
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
from sklearn.impute import SimpleImputer
from sklearn.metrics import f1_score, r2_score
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler

import features as F

warnings.filterwarnings("ignore")


def channels_to_features(feature_cols: List[str]) -> Dict[str, List[str]]:
    """Map each channel to its aggregate feature columns (channel = name before __)."""
    out: Dict[str, List[str]] = {}
    for c in feature_cols:
        base = c.split("__")[0]
        out.setdefault(base, []).append(c)
    return out


def mi_by_channel(table, feature_cols, target, discrete: bool) -> pd.DataFrame:
    X = SimpleImputer(strategy="median").fit_transform(table[feature_cols])
    y = table[target]
    fn = mutual_info_classif if discrete else mutual_info_regression
    mi = fn(X, y, random_state=0)
    s = pd.Series(mi, index=feature_cols)
    ch_map = channels_to_features(feature_cols)
    rows = [{"channel": ch, "mutual_info": float(s[cols].sum()),
             "mi_per_feature": float(s[cols].mean())}
            for ch, cols in ch_map.items()]
    return pd.DataFrame(rows).sort_values("mutual_info", ascending=False)


def redundancy(table, feature_cols, threshold) -> pd.DataFrame:
    """Highly correlated channel-mean pairs (redundant instrumentation)."""
    means = [c for c in feature_cols if c.endswith("__mean")]
    if len(means) < 2:
        return pd.DataFrame()
    corr = table[means].corr().abs()
    rows = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if r >= threshold:
                rows.append({"channel_a": cols[i].replace("__mean", ""),
                             "channel_b": cols[j].replace("__mean", ""),
                             "abs_corr": round(float(r), 3)})
    return pd.DataFrame(rows).sort_values("abs_corr", ascending=False)


def _cv_score(table, cols, target, group_col, discrete) -> float:
    y, groups = table[target], table[group_col]
    X = table[cols]
    n_groups = groups.nunique()
    if discrete:
        min_cg = (pd.DataFrame({"y": y, "g": groups}).groupby("y")["g"].nunique().min())
        n_splits = int(min(5, n_groups, max(min_cg, 2)))
        cv = StratifiedGroupKFold(n_splits=n_splits)
        model_imp = SimpleImputer(strategy="median")
        clf = RandomForestClassifier(n_estimators=200, random_state=0)
        Xi = model_imp.fit_transform(X)
        pred = cross_val_predict(clf, Xi, y, groups=groups, cv=cv)
        return f1_score(y, pred, average="macro")
    else:
        n_splits = int(min(5, n_groups))
        cv = GroupKFold(n_splits=n_splits)
        Xi = SimpleImputer(strategy="median").fit_transform(X)
        reg = RandomForestRegressor(n_estimators=200, random_state=0)
        pred = cross_val_predict(reg, Xi, y, groups=groups, cv=cv)
        return r2_score(y, pred)


def greedy_minimal_set(table, channel_map, target, group_col, discrete, max_k
                       ) -> pd.DataFrame:
    """Forward selection over whole channels; record score as each is added."""
    remaining = list(channel_map.keys())
    selected: List[str] = []
    rows = []
    while remaining and len(selected) < max_k:
        best_ch, best_score = None, -np.inf
        for ch in remaining:
            cols = sum([channel_map[c] for c in selected + [ch]], [])
            score = _cv_score(table, cols, target, group_col, discrete)
            if score > best_score:
                best_ch, best_score = ch, score
        selected.append(best_ch)
        remaining.remove(best_ch)
        rows.append({"k": len(selected), "added_channel": best_ch,
                     "score": round(float(best_score), 4),
                     "selected": ", ".join(selected)})
    return pd.DataFrame(rows)


def report_minimal(df: pd.DataFrame, label: str, full_score: float):
    if df.empty:
        return
    target95 = 0.95 * full_score
    hit = df[df["score"] >= target95]
    print(f"\nMinimal sensor set for {label} (full set score {full_score:.3f}):")
    for _, r in df.iterrows():
        mark = " <- reaches 95%" if (not hit.empty and r["k"] == hit.iloc[0]["k"]) else ""
        print(f"  {int(r['k'])} sensor(s): {r['score']:.3f}  (+{r['added_channel']}){mark}")
    if not hit.empty:
        k = int(hit.iloc[0]["k"])
        chs = hit.iloc[0]["selected"]
        print(f"  => {k} sensor(s) recover 95% of full performance: {chs}")


def maybe_plot(mi_op, mi_en, min_op, min_en, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, mi, title in ((axes[0], mi_op, "MI with operation"),
                          (axes[1], mi_en, "MI with energy")):
        top = mi.head(10)
        ax.barh(top["channel"][::-1], top["mutual_info"][::-1], color="#4C78A8")
        ax.set_title(title)
    fig.tight_layout(); fig.savefig(out_dir / "mutual_info.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    if not min_op.empty:
        ax.plot(min_op["k"], min_op["score"], marker="o", label="operation (macro-F1)")
    if not min_en.empty:
        ax.plot(min_en["k"], min_en["score"], marker="s", label="energy (R2)")
    ax.set_xlabel("number of sensors"); ax.set_ylabel("score")
    ax.set_title("Performance vs sensor count (greedy)"); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "score_vs_sensors.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sensor importance, redundancy, and minimal sensor set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/sensor_study")
    ap.add_argument("--corr-threshold", type=float, default=0.95)
    ap.add_argument("--min-per-class", type=int, default=4)
    ap.add_argument("--max-sensors", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, groups = F.prepare(args.input, "segment")

    # Drop rare operations so classification CV is valid.
    counts = table["operation"].value_counts()
    table = table[table["operation"].isin(counts[counts >= args.min_per_class].index)].copy()

    all_feats = F.feature_columns(table)
    energy_feats = set(groups.get("energy", []))
    energy_excl = [c for c in all_feats if c not in energy_feats]   # predictors for energy
    ecol = "energy_kwh_meter" if "energy_kwh_meter" in table else "energy_wh_integral"

    # Mutual information.
    mi_op = mi_by_channel(table, all_feats, "operation", discrete=True)
    mi_en = mi_by_channel(table, energy_excl, ecol, discrete=False)
    red = redundancy(table, all_feats, args.corr_threshold)

    # Greedy minimal sensor sets.
    chmap_op = channels_to_features(all_feats)
    chmap_en = channels_to_features(energy_excl)
    full_op = _cv_score(table, all_feats, "operation", "source_file", True)
    full_en = _cv_score(table, energy_excl, ecol, "source_file", False)
    min_op = greedy_minimal_set(table, chmap_op, "operation", "source_file", True, args.max_sensors)
    min_en = greedy_minimal_set(table, chmap_en, ecol, "source_file", False, args.max_sensors)

    mi_op.to_csv(out_dir / "mutual_info_operation.csv", index=False)
    mi_en.to_csv(out_dir / "mutual_info_energy.csv", index=False)
    red.to_csv(out_dir / "sensor_redundancy.csv", index=False)
    min_op.to_csv(out_dir / "minimal_set_operation.csv", index=False)
    min_en.to_csv(out_dir / "minimal_set_energy.csv", index=False)
    maybe_plot(mi_op, mi_en, min_op, min_en, out_dir)

    # ---- console summary -------------------------------------------------
    print("Top channels by mutual information with OPERATION:")
    for _, r in mi_op.head(6).iterrows():
        print(f"  {r['channel']:26s} MI={r['mutual_info']:.3f}")
    print("\nTop channels by mutual information with ENERGY (energy sensors excluded):")
    for _, r in mi_en.head(6).iterrows():
        print(f"  {r['channel']:26s} MI={r['mutual_info']:.3f}")

    if not red.empty:
        print(f"\nRedundant channel pairs (|corr| >= {args.corr_threshold}):")
        for _, r in red.head(8).iterrows():
            print(f"  {r['channel_a']} ~ {r['channel_b']} (r={r['abs_corr']})")
    else:
        print(f"\nNo channel pairs above |corr| {args.corr_threshold}.")

    report_minimal(min_op, "operation classification", full_op)
    report_minimal(min_en, "energy estimation", full_en)

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
