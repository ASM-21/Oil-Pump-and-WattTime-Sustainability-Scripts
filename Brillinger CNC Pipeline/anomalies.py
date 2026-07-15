"""
anomalies.py — outlier and drift detection for exploration hygiene.

Flags operations and parts that stand out, plus trends across the corpus. Uses
robust statistics (median / MAD) so a couple of extreme values do not set the
thresholds. Critically, it refuses to flag outliers in groups too small to
support the statistic (real datasets here are small), marking them
insufficient_n instead of inventing anomalies.

This is distributional anomaly detection, distinct from operations.data_quality,
which checks per-record validity (negative marginal energy, missing volume).
Run both.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

import brillinger_pipeline as bp
import operations as ops
import signals as sig
from config import DatasetConfig

log = logging.getLogger("anomalies")

_MIN_GROUP = 5          # below this, robust z is unreliable; do not flag
_Z_THRESH = 3.5         # robust-z outlier threshold (Iglewicz-Hoaglin)


def _robust_z(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if not np.isfinite(x).any():          # all-NaN: nothing to assess
        return np.full_like(x, np.nan)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    if mad == 0 or np.isnan(mad):
        return np.full_like(x, np.nan)
    return 0.6745 * (x - med) / mad


def operation_outliers(store: ops.OperationStore, metric: str = "sec_marginal",
                       by: str = "operation_type", z_thresh: float = _Z_THRESH,
                       min_group: int = _MIN_GROUP) -> dict:
    """Operations whose metric is a robust-z outlier within their group.

    Returns flagged rows and a per-group note (including groups skipped for
    insufficient n), so a small dataset yields honest "cannot assess" rather
    than spurious flags.
    """
    df = store.to_frame()
    df = df[df[metric].notna()]
    flags, notes = [], []
    for grp, g in df.groupby(by):
        if len(g) < min_group:
            notes.append({by: grp, "n": len(g), "status": "insufficient_n"})
            continue
        z = _robust_z(g[metric].to_numpy())
        g = g.assign(robust_z=z)
        hit = g[np.abs(g["robust_z"]) > z_thresh]
        for _, r in hit.iterrows():
            flags.append({"uuid": r["uuid"], "source": r["source"], by: grp,
                          metric: r[metric], "robust_z": round(r["robust_z"], 2),
                          "reason": f"{metric}_outlier_within_{by}"})
        notes.append({by: grp, "n": len(g), "status": "assessed"})
    return {"flags": pd.DataFrame(flags), "group_notes": pd.DataFrame(notes)}


def experiment_outliers(per_experiment: pd.DataFrame,
                        metrics=("energy_j", "cutting_sec"),
                        by: str = "material", z_thresh: float = _Z_THRESH,
                        min_group: int = _MIN_GROUP) -> dict:
    """Parts whose energy or SEC is a robust-z outlier within their material."""
    flags, notes = [], []
    for grp, g in per_experiment.groupby(by):
        assessed = len(g) >= min_group
        notes.append({by: grp, "n": len(g),
                      "status": "assessed" if assessed else "insufficient_n"})
        if not assessed:
            continue
        for metric in metrics:
            if metric not in g:
                continue
            z = _robust_z(g[metric].to_numpy())
            for (_, r), zz in zip(g.iterrows(), z):
                if np.isfinite(zz) and abs(zz) > z_thresh:
                    flags.append({"experiment": r["experiment"], by: grp,
                                  "metric": metric, "value": r[metric],
                                  "robust_z": round(zz, 2)})
    return {"flags": pd.DataFrame(flags), "group_notes": pd.DataFrame(notes)}


def drift_scan(per_experiment: pd.DataFrame, order_col: Optional[str] = None,
               metrics=("energy_j", "cutting_sec"), rho_thresh: float = 0.5) -> pd.DataFrame:
    """Trend of a metric across the corpus, e.g. rising energy from tool wear.

    Uses order_col if given (a real time or sequence key); otherwise falls back
    to row order as a PROXY and says so. A |Spearman rho| above rho_thresh is
    flagged as possible drift worth inspecting, not a conclusion.
    """
    df = per_experiment.copy()
    proxy = order_col is None or order_col not in df.columns
    if proxy:
        df = df.reset_index(drop=True)
        df["_order"] = np.arange(len(df))
        order = "_order"
        log.warning("drift_scan: no order_col; using row order as a PROXY. "
                    "Real drift needs a timestamp or run-sequence key.")
    else:
        order = order_col
        df = df.sort_values(order)

    rows = []
    for metric in metrics:
        if metric not in df:
            continue
        pair = df[[order, metric]].dropna()
        if len(pair) < 4 or pair[metric].nunique() < 3:
            rows.append({"metric": metric, "rho": np.nan, "n": len(pair),
                         "order_is_proxy": proxy, "flag": "insufficient_n"})
            continue
        rho = pair[order].corr(pair[metric], method="spearman")
        rows.append({"metric": metric, "rho": round(rho, 3), "n": len(pair),
                     "order_is_proxy": proxy,
                     "flag": "possible_drift" if abs(rho) > rho_thresh else "no_trend"})
    return pd.DataFrame(rows)


def signal_anomalies(manifest: pd.DataFrame, cfg: DatasetConfig,
                     nc_key: str = "n_number", sat_tol: float = 1e-3,
                     min_match: float = 0.99, sat_frac: float = 0.5,
                     max_parts: Optional[int] = None) -> pd.DataFrame:
    """Per-part signal health flags: low NC-alignment match rate, sensor
    saturation (power pinned at its max), and dropout gaps.

    Low match rate is the most important and most reliable flag: it means the
    counter is not lining up with the NC program, which invalidates
    per-operation attribution for that part. Saturation is a COARSE advisory
    only: a genuinely constant-power operation can put many samples near the max
    without any clipping, so treat a saturation flag as "inspect", not "bad",
    and confirm against the sensor's known range.
    """
    cmap = sig._cmap(cfg)
    complete = manifest[manifest["complete"]] if "complete" in manifest else manifest
    if max_parts:
        complete = complete.head(max_parts)

    rows = []
    for _, row in complete.iterrows():
        try:
            power = bp.load_power_json(row["energy_path"], cmap=cmap)
            nc = bp.parse_mpf(row["nc_path"])
            p = power["power_drives_sum"].to_numpy()

            # alignment match rate
            match = np.nan
            if "counter" in power.columns and nc_key in nc.columns:
                merged = power.merge(nc[[nc_key]], left_on="counter",
                                     right_on=nc_key, how="left", indicator=True)
                match = float((merged["_merge"] == "both").mean())

            # saturation: fraction of samples within sat_tol of the max
            pmax = p.max() if len(p) else np.nan
            sat = float((np.abs(p - pmax) <= sat_tol * max(abs(pmax), 1)).mean()) if len(p) else np.nan

            reasons = []
            if np.isfinite(match) and match < min_match:
                reasons.append(f"low_nc_match({match:.2f})")
            if np.isfinite(sat) and sat > sat_frac:
                reasons.append(f"advisory_possible_clipping({sat:.2f})")

            if reasons:
                rows.append({"experiment": row["experiment"],
                             "nc_match_rate": round(match, 3) if np.isfinite(match) else np.nan,
                             "saturation_frac": round(sat, 3) if np.isfinite(sat) else np.nan,
                             "reasons": ", ".join(reasons)})
        except Exception as exc:  # noqa: BLE001
            rows.append({"experiment": row["experiment"], "nc_match_rate": np.nan,
                         "saturation_frac": np.nan, "reasons": f"load_error: {exc}"})
    return pd.DataFrame(rows)


def run_all(store: ops.OperationStore, per_experiment: pd.DataFrame,
            manifest: pd.DataFrame, cfg: DatasetConfig, **kw) -> dict:
    """Convenience: run every anomaly check and return the flag tables."""
    return {
        "operation_outliers": operation_outliers(store),
        "experiment_outliers": experiment_outliers(per_experiment),
        "drift": drift_scan(per_experiment, order_col=kw.get("order_col")),
        "signal_anomalies": signal_anomalies(manifest, cfg,
                                             max_parts=kw.get("max_parts")),
        "data_quality": ops.data_quality(store),
    }
