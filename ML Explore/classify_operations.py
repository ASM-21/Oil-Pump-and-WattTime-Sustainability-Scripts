#!/usr/bin/env python3
"""
classify_operations.py
======================

Classify which operation is running from the sensors, and compare algorithms, to
answer two questions:

  1. Do different algorithms work better for different operations?
     -> per-operation F1 for every algorithm (results_per_operation_f1.csv).
  2. What do sensors beyond energy buy you?
     -> sensor-group ablation: macro-F1 per group vs all (results_sensor_ablation.csv).

Points straight at the folder of per-operation CSVs from split_operations.py; no
separate feature step. Evaluation uses StratifiedGroupKFold grouped by run
(source_file), so whole runs are held out and scores reflect generalization to
unseen runs rather than memorizing a run.

Outputs (into --output, default ./ml/classify):
  results_algorithms.csv          accuracy / macro-F1 / weighted-F1 per algorithm
  results_per_operation_f1.csv    operation x algorithm F1 grid
  results_sensor_ablation.csv     sensor_group x algorithm macro-F1 grid
  feature_importance_top.csv      top features (RandomForest)
  *.png                           heatmap + ablation plots (if matplotlib present)

Usage
-----
  python classify_operations.py --input ./operation_csvs
  python classify_operations.py --input ./operation_csvs --min-samples 6
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import (
    GroupKFold, StratifiedGroupKFold, StratifiedKFold, cross_val_predict,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

import features as F

warnings.filterwarnings("ignore")


def make_models() -> Dict[str, Pipeline]:
    def pipe(clf):
        return Pipeline([("impute", SimpleImputer(strategy="median")),
                         ("scale", StandardScaler()), ("clf", clf)])
    return {
        "logreg": pipe(LogisticRegression(max_iter=2000)),
        "random_forest": pipe(RandomForestClassifier(n_estimators=300, random_state=0)),
        "grad_boost": pipe(GradientBoostingClassifier(random_state=0)),
        "svm_rbf": pipe(SVC(kernel="rbf", C=10, gamma="scale", random_state=0)),
        "knn": pipe(KNeighborsClassifier(n_neighbors=5)),
    }


def choose_cv(y: pd.Series, groups: pd.Series, max_splits: int = 5):
    n_groups = groups.nunique()
    min_class_groups = (pd.DataFrame({"y": y, "g": groups})
                        .groupby("y")["g"].nunique().min())
    n_splits = int(min(max_splits, n_groups, max(min_class_groups, 2)))
    if min_class_groups >= 2 and n_splits >= 2:
        return StratifiedGroupKFold(n_splits=n_splits), n_splits, "StratifiedGroupKFold (by run)"
    if n_groups >= 2:
        k = min(max_splits, n_groups)
        return GroupKFold(n_splits=k), k, "GroupKFold (by run, unstratified)"
    print("  ! too few runs to group by; using plain StratifiedKFold (optimistic).")
    return StratifiedKFold(n_splits=3, shuffle=True, random_state=0), 3, "StratifiedKFold (NOT grouped)"


def drop_rare_classes(df, label, min_per_class):
    counts = df[label].value_counts()
    keep = counts[counts >= min_per_class].index
    dropped = [c for c in counts.index if c not in keep]
    if dropped:
        print(f"  ! dropping operations with < {min_per_class} passes: {dropped}")
    return df[df[label].isin(keep)].copy()


def evaluate(models, X, y, groups, cv) -> Tuple[pd.DataFrame, pd.DataFrame]:
    labels = sorted(y.unique())
    summary_rows, per_op = [], pd.DataFrame(index=labels)
    for name, model in models.items():
        preds = cross_val_predict(model, X, y, groups=groups, cv=cv)
        summary_rows.append({"algorithm": name,
                             "accuracy": accuracy_score(y, preds),
                             "macro_f1": f1_score(y, preds, average="macro"),
                             "weighted_f1": f1_score(y, preds, average="weighted")})
        rep = classification_report(y, preds, labels=labels, output_dict=True, zero_division=0)
        per_op[name] = [rep[str(l)]["f1-score"] for l in labels]
    summary = pd.DataFrame(summary_rows).sort_values("macro_f1", ascending=False)
    return summary.reset_index(drop=True), per_op


def sensor_ablation(models, table, label, group_col, sensor_groups, cv) -> pd.DataFrame:
    y, groups = table[label], table[group_col]
    blocks: Dict[str, List[str]] = {g: [c for c in cols if c in table.columns]
                                    for g, cols in sensor_groups.items()}
    blocks["all"] = F.feature_columns(table)
    rows = {}
    for gname, cols in blocks.items():
        if not cols:
            continue
        rows[gname] = {}
        for mname, model in models.items():
            preds = cross_val_predict(model, table[cols], y, groups=groups, cv=cv)
            rows[gname][mname] = f1_score(y, preds, average="macro")
    out = pd.DataFrame(rows).T
    order = ["all"] + [g for g in out.index if g != "all"]
    return out.loc[order]


def top_importance(table, label, n=20) -> pd.DataFrame:
    cols = F.feature_columns(table)
    X = SimpleImputer(strategy="median").fit_transform(table[cols])
    rf = RandomForestClassifier(n_estimators=400, random_state=0).fit(X, table[label])
    imp = pd.Series(rf.feature_importances_, index=cols).sort_values(ascending=False)
    return imp.head(n).rename("importance").reset_index().rename(columns={"index": "feature"})


def maybe_plot(per_op, ablation, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(figsize=(1.4 * per_op.shape[1] + 2, 0.5 * per_op.shape[0] + 2))
    im = ax.imshow(per_op.values, aspect="auto", cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(per_op.shape[1])); ax.set_xticklabels(per_op.columns, rotation=45, ha="right")
    ax.set_yticks(range(per_op.shape[0])); ax.set_yticklabels(per_op.index)
    for i in range(per_op.shape[0]):
        for j in range(per_op.shape[1]):
            ax.text(j, i, f"{per_op.values[i,j]:.2f}", ha="center", va="center",
                    color="white" if per_op.values[i,j] < 0.6 else "black", fontsize=8)
    ax.set_title("Per-operation F1 by algorithm"); fig.colorbar(im, ax=ax, label="F1")
    fig.tight_layout(); fig.savefig(out_dir / "per_operation_f1.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(1.1 * ablation.shape[0] + 3, 4))
    x = np.arange(ablation.shape[0]); w = 0.8 / ablation.shape[1]
    for k, alg in enumerate(ablation.columns):
        ax.bar(x + k * w, ablation[alg].values, w, label=alg)
    ax.set_xticks(x + 0.4 - w / 2); ax.set_xticklabels(ablation.index, rotation=20)
    ax.set_ylabel("macro-F1"); ax.set_ylim(0, 1)
    ax.set_title("Operation classification by sensor group"); ax.legend(fontsize=8, ncol=2)
    fig.tight_layout(); fig.savefig(out_dir / "sensor_ablation.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare ML algorithms on operation classification, per operation "
                    "and per sensor group.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml/classify")
    ap.add_argument("--label", default="operation")
    ap.add_argument("--group-col", default="source_file",
                    help="Column defining independent units held out together (the run).")
    ap.add_argument("--min-per-class", type=int, default=4)
    ap.add_argument("--min-samples", type=int, default=0,
                    help="Drop passes shorter than this many samples before modeling.")
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, sensor_groups = F.prepare(args.input, "segment")

    if args.min_samples > 0 and "n_samples" in table:
        before = len(table)
        table = table[table["n_samples"] >= args.min_samples].copy()
        print(f"Length filter: kept {len(table)}/{before} passes (>= {args.min_samples} samples).")

    table = drop_rare_classes(table, args.label, args.min_per_class)
    y, groups = table[args.label], table[args.group_col]
    X = table[F.feature_columns(table)]

    cv, n_splits, cv_name = choose_cv(y, groups)
    print(f"Data: {len(table)} passes, {y.nunique()} operations, {groups.nunique()} runs. "
          f"CV: {cv_name}, {n_splits} folds.\n")

    models = make_models()
    summary, per_op = evaluate(models, X, y, groups, cv)
    ablation = sensor_ablation(models, table, args.label, args.group_col, sensor_groups, cv)
    importance = top_importance(table, args.label)

    summary.to_csv(out_dir / "results_algorithms.csv", index=False)
    per_op.to_csv(out_dir / "results_per_operation_f1.csv")
    ablation.to_csv(out_dir / "results_sensor_ablation.csv")
    importance.to_csv(out_dir / "feature_importance_top.csv", index=False)
    maybe_plot(per_op, ablation, out_dir)

    print("Algorithm ranking (macro-F1):")
    for _, r in summary.iterrows():
        print(f"  {r['algorithm']:15s} acc={r['accuracy']:.3f}  macroF1={r['macro_f1']:.3f}")
    print("\nBest algorithm per operation:")
    winners = per_op.idxmax(axis=1)
    for op in per_op.index:
        print(f"  {op:18s} -> {winners[op]:15s} (F1={per_op.loc[op].max():.3f})")
    print("  => " + ("different operations favor different algorithms."
                     if winners.nunique() > 1 else f"{winners.iloc[0]} wins across the board."))
    print("\nSensor-group ablation (macro-F1, best algorithm per group):")
    for g in ablation.index:
        print(f"  {g:12s} {ablation.loc[g].max():.3f}  (via {ablation.loc[g].idxmax()})")
    if "energy" in ablation.index and "all" in ablation.index:
        e, a = ablation.loc["energy"].max(), ablation.loc["all"].max()
        print(f"  => energy alone {e:.3f} vs all sensors {a:.3f} (+{a-e:.3f} from non-energy).")
    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
