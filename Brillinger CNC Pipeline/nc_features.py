"""
nc_features.py — structural metrics of an NC program.

Turns a parsed program into a structural fingerprint: how much cutting vs air,
how many tools and tool changes, path lengths, depth layering, feed and speed
ranges. Pair these with energy to ask whether program structure predicts
energy, which is the seed of a feature-energy model.

Distances use 3D endpoint (chord) length per block. Arc length is therefore
slightly underestimated, which is fine for a complexity proxy; use the Z-map if
you need exact swept geometry.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

import brillinger_pipeline as bp
from config import DatasetConfig

log = logging.getLogger("nc_features")

_ARC = {"G2", "G3"}
_LINE = {"G0", "G1"}


def _seg_len(df: pd.DataFrame) -> np.ndarray:
    cols = ["x0", "y0", "z0", "x1", "y1", "z1"]
    if not all(c in df.columns for c in cols):
        return np.zeros(len(df))
    d = df[cols].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        L = np.sqrt((d[:, 3] - d[:, 0])**2 + (d[:, 4] - d[:, 1])**2
                    + (d[:, 5] - d[:, 2])**2)
    return np.nan_to_num(L, nan=0.0)


def nc_complexity(nc_df: pd.DataFrame, z_tol: float = 0.05) -> pd.Series:
    """Structural metrics for one parsed NC program (from bp.parse_mpf)."""
    df = nc_df.copy()
    df["seg_len"] = _seg_len(df)
    op = df["operation"]

    cutting = df[op == "cutting"]
    rapid = df[op == "rapid"]
    cut_dist = float(cutting["seg_len"].sum())
    rapid_dist = float(rapid["seg_len"].sum())
    total_dist = float(df["seg_len"].sum())

    # distinct cutting depths (2.5D layering proxy)
    if len(cutting):
        z = np.round(cutting["z1"].dropna().to_numpy() / z_tol) * z_tol
        n_z = int(len(np.unique(z)))
    else:
        n_z = 0

    feeds = cutting["F"][cutting["F"] > 0]
    speeds = df.loc[df["spindle_on"], "S"]
    speeds = speeds[speeds > 0]

    m = {
        "n_blocks": len(df),
        "n_cutting_blocks": int((op == "cutting").sum()),
        "n_rapid_blocks": int((op == "rapid").sum()),
        "n_tool_changes": int(df["tool_change"].sum()),
        "n_tools": int(df["T"].dropna().nunique()),
        "n_arcs": int(df["motion"].isin(_ARC).sum()),
        "n_linear_moves": int(df["motion"].isin(_LINE).sum()),
        "n_drill_cycles": int((df["cycles"].fillna("") != "").sum()),
        "cutting_distance_mm": cut_dist,
        "rapid_distance_mm": rapid_dist,
        "total_distance_mm": total_dist,
        "air_fraction": rapid_dist / total_dist if total_dist else np.nan,
        "n_z_levels": n_z,
        "feed_min": float(feeds.min()) if len(feeds) else np.nan,
        "feed_max": float(feeds.max()) if len(feeds) else np.nan,
        "feed_mean": float(feeds.mean()) if len(feeds) else np.nan,
        "speed_min": float(speeds.min()) if len(speeds) else np.nan,
        "speed_max": float(speeds.max()) if len(speeds) else np.nan,
        "speed_mean": float(speeds.mean()) if len(speeds) else np.nan,
    }
    return pd.Series(m)


def corpus_nc_complexity(manifest: pd.DataFrame, cfg: DatasetConfig,
                         max_parts: Optional[int] = None) -> pd.DataFrame:
    """NC complexity metrics for every complete experiment, one row each."""
    complete = manifest[manifest["complete"]] if "complete" in manifest else manifest
    if max_parts:
        complete = complete.head(max_parts)
    rows = []
    for _, row in complete.iterrows():
        try:
            nc = bp.parse_mpf(row["nc_path"])
            s = nc_complexity(nc)
            s["experiment"] = row["experiment"]
            rows.append(s)
        except Exception as exc:  # noqa: BLE001
            log.warning("nc_complexity failed on %s: %s", row["experiment"], exc)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("experiment").reset_index()
