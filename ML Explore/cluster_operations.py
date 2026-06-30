#!/usr/bin/env python3
"""
cluster_operations.py
=====================

Unsupervised view of the data: cluster passes from their sensor features without using
the operation labels, then check whether the clusters recover the operations and whether
sub-modes hide inside any single operation. Points straight at the operation_csvs folder.

What it does:
  - PCA to a 2D projection (plus variance explained) and KMeans over a range of k,
    choosing k by silhouette.
  - Agreement with the true operations: Adjusted Rand Index and normalized mutual info
    (high = sensor signatures separate operations on their own).
  - Sub-mode search: cluster each operation's own passes (k = 2..3) and flag operations
    whose passes split cleanly, which can indicate distinct regimes within one operation.

Outputs (into --output, default ./ml/clustering):
  cluster_quality.csv      k -> silhouette, ARI vs operations, NMI vs operations
  cluster_assignments.csv   pass -> operation, cluster, PCA coordinates
  submodes.csv              operation -> best internal k and its silhouette
  *.png                     2D projection colored by operation and by cluster, silhouette vs k

Usage
-----
  python cluster_operations.py --input ./operation_csvs
  python cluster_operations.py --input ./operation_csvs --max-k 8
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

_HERE = Path(__file__).resolve().parent

import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    adjusted_rand_score, normalized_mutual_info_score, silhouette_score,
)
from sklearn.preprocessing import StandardScaler

import features as F

warnings.filterwarnings("ignore")


def prep_matrix(table):
    cols = F.feature_columns(table)
    X = SimpleImputer(strategy="median").fit_transform(table[cols])
    X = StandardScaler().fit_transform(X)
    return X


def sweep_k(X, labels_true, max_k):
    rows = []
    upper = min(max_k, len(X) - 1)
    for k in range(2, max(upper + 1, 3)):
        km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
        sil = silhouette_score(X, km.labels_) if k < len(X) else np.nan
        rows.append({"k": k, "silhouette": round(float(sil), 3),
                     "ari_vs_operation": round(float(adjusted_rand_score(labels_true, km.labels_)), 3),
                     "nmi_vs_operation": round(float(normalized_mutual_info_score(labels_true, km.labels_)), 3)})
    return pd.DataFrame(rows)


def submodes(table, max_internal=3, min_passes=8):
    rows = []
    cols = F.feature_columns(table)
    for op, g in table.groupby("operation"):
        if len(g) < min_passes:
            continue
        X = SimpleImputer(strategy="median").fit_transform(g[cols])
        X = StandardScaler().fit_transform(X)
        best_k, best_sil = 1, 0.0
        for k in range(2, min(max_internal, len(g) - 1) + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
            sil = silhouette_score(X, km.labels_)
            if sil > best_sil:
                best_k, best_sil = k, sil
        rows.append({"operation": op, "n_passes": len(g),
                     "best_internal_k": best_k, "silhouette": round(float(best_sil), 3),
                     "likely_submodes": bool(best_sil >= 0.5 and best_k > 1)})
    return pd.DataFrame(rows).sort_values("silhouette", ascending=False)


def maybe_plot(coords, labels_true, best_labels, quality, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, lab, title in ((axes[0], labels_true, "PCA colored by operation"),
                           (axes[1], best_labels, "PCA colored by KMeans cluster")):
        for val in pd.unique(lab):
            m = lab == val
            ax.scatter(coords[m, 0], coords[m, 1], s=22, alpha=0.8, label=str(val))
        ax.set_xlabel("PC1"); ax.set_ylabel("PC2"); ax.set_title(title)
        ax.legend(fontsize=7, markerscale=0.8)
    fig.tight_layout(); fig.savefig(out_dir / "pca_projection.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(quality["k"], quality["silhouette"], "o-", label="silhouette")
    ax.plot(quality["k"], quality["ari_vs_operation"], "s-", label="ARI vs operation")
    ax.set_xlabel("k (clusters)"); ax.set_ylabel("score")
    ax.set_title("Cluster quality vs k"); ax.legend()
    fig.tight_layout(); fig.savefig(out_dir / "cluster_quality.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Unsupervised clustering and sub-mode discovery.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default=str(_HERE / "operation_csvs"))
    ap.add_argument("--output", default=str(_HERE / "ml/clustering"))
    ap.add_argument("--max-k", type=int, default=8)
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    labels_true = table["operation"].values

    X = prep_matrix(table)
    pca = PCA(n_components=min(10, X.shape[1]))
    coords_full = pca.fit_transform(X)
    coords = coords_full[:, :2]
    var2 = float(pca.explained_variance_ratio_[:2].sum())

    quality = sweep_k(X, labels_true, args.max_k)
    best_row = quality.loc[quality["silhouette"].idxmax()]
    best_k = int(best_row["k"])
    best_labels = KMeans(n_clusters=best_k, n_init=10, random_state=0).fit_predict(X)
    subs = submodes(table)

    assign = table[["program", "run", "source_file", "segment_id", "operation"]].copy()
    assign["cluster"] = best_labels
    assign["pc1"], assign["pc2"] = coords[:, 0], coords[:, 1]

    quality.to_csv(out_dir / "cluster_quality.csv", index=False)
    assign.to_csv(out_dir / "cluster_assignments.csv", index=False)
    subs.to_csv(out_dir / "submodes.csv", index=False)
    maybe_plot(coords, labels_true, best_labels, quality, out_dir)

    # ---- console summary -------------------------------------------------
    print(f"Passes: {len(table)}, features: {len(F.feature_columns(table))}, "
          f"true operations: {table['operation'].nunique()}.")
    print(f"PCA: first 2 components explain {var2:.0%} of variance.\n")
    print(f"Best KMeans k by silhouette: {best_k} "
          f"(silhouette {best_row['silhouette']}); this is the most natural grouping.")
    # Fair label-recovery check: cluster at the true number of operations.
    n_ops = table["operation"].nunique()
    at_true = quality[quality["k"] == n_ops]
    if not at_true.empty:
        ari = float(at_true.iloc[0]["ari_vs_operation"])
        nmi = float(at_true.iloc[0]["nmi_vs_operation"])
        print(f"At k={n_ops} (the true operation count): ARI={ari:.3f}, NMI={nmi:.3f}.")
    else:
        ari = float(best_row["ari_vs_operation"]); nmi = float(best_row["nmi_vs_operation"])
        print(f"Agreement with operations at k={best_k}: ARI={ari:.3f}, NMI={nmi:.3f}.")
    if ari >= 0.7:
        print("  => sensor signatures separate the operations well on their own.")
    elif ari >= 0.4:
        print("  => sensor signatures partly recover the operations.")
    else:
        print("  => clusters do not align with operations; structure is driven by "
              "something else (e.g. run-to-run drift or a dominant axis).")

    flagged = subs[subs["likely_submodes"]]
    if not flagged.empty:
        print("\nOperations with likely sub-modes (clean internal split):")
        for _, r in flagged.iterrows():
            print(f"  {r['operation']:18s} {int(r['best_internal_k'])} modes "
                  f"(silhouette {r['silhouette']}, n={int(r['n_passes'])})")
    else:
        print("\nNo strong sub-mode structure within individual operations.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
