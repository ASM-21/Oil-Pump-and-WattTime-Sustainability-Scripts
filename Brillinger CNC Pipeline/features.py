"""
features.py — assemble a per-experiment feature table and correlate it with
energy.

Joins NC structural metrics, part geometry, and the corpus energy results into
one row per experiment, with energy and SEC as targets. That table is the
exploration artifact for "does structure predict energy," and it is directly
regression-ready for a feature-energy model.

Correlations here are exploratory: the number of experiments is small, so treat
them as direction-finding, not estimates. Spearman is the default because it is
robust to nonlinearity and outliers.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# columns that are identifiers or targets, not predictive features
_NON_FEATURE = {
    "experiment", "material", "machine",
    "energy_j", "cutting_energy_j", "cutting_volume_mm3", "cutting_sec",
    "volume_mm3", "n_ops",
}


def build_feature_table(per_experiment: pd.DataFrame,
                        nc_complexity: Optional[pd.DataFrame] = None,
                        geometry: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """One row per experiment: energy/SEC targets plus NC and geometry features.

    per_experiment comes from dataset_explorer.corpus_run; nc_complexity from
    nc_features.corpus_nc_complexity; geometry from geometry.corpus_geometry.
    Any of the feature frames may be omitted.
    """
    table = per_experiment.copy()
    for extra in (nc_complexity, geometry):
        if extra is not None and not extra.empty:
            table = table.merge(extra, on="experiment", how="left",
                                suffixes=("", "_geom"))
    return table


def feature_columns(table: pd.DataFrame) -> list[str]:
    num = table.select_dtypes(include="number").columns
    return [c for c in num if c not in _NON_FEATURE]


def feature_correlations(table: pd.DataFrame, target: str = "energy_j",
                         method: str = "spearman",
                         min_unique: int = 3) -> pd.DataFrame:
    """Correlation of each feature with the target.

    Skips features that are constant or nearly so (fewer than min_unique
    distinct values), which cannot correlate. Returns a frame sorted by absolute
    correlation, with the sample size used.
    """
    if target not in table.columns:
        raise ValueError(f"target '{target}' not in table.")
    feats = [c for c in feature_columns(table) if c != target]
    rows = []
    for c in feats:
        pair = table[[c, target]].dropna()
        if pair[c].nunique() < min_unique or len(pair) < 3:
            continue
        rho = pair[c].corr(pair[target], method=method)
        rows.append({"feature": c, "correlation": rho, "n": len(pair)})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["abs"] = out["correlation"].abs()
        out = out.sort_values("abs", ascending=False).drop(columns="abs").reset_index(drop=True)
    return out


def correlation_matrix(table: pd.DataFrame, method: str = "spearman") -> pd.DataFrame:
    """Full feature+target correlation matrix for the exploratory heatmap."""
    cols = feature_columns(table) + [c for c in ("energy_j", "cutting_sec")
                                     if c in table.columns]
    sub = table[cols].dropna(axis=1, how="all")
    keep = [c for c in sub.columns if sub[c].nunique() >= 3]
    return sub[keep].corr(method=method)
