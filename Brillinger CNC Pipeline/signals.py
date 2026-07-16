"""
signals.py — signal-level analyses on the per-axis power data.

These exploit what the Brillinger dataset has and a single total meter does not:
a per-axis power breakdown. They answer questions the IN-MaC data structurally
cannot, which is exactly the point of bringing this dataset in.

  label_samples          attach operation type + a time axis to every power
                         sample (substrate for timelines and per-axis energy)
  axis_energy_breakdown  energy per drive axis per operation (where, mechanically,
                         the energy goes: spindle vs feed drives vs rotary)
  corpus_sampling_sweep  run the 1 Hz adequacy test across every part and both
                         meter models, aggregated to a corpus-level answer
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import brillinger_pipeline as bp
from config import DatasetConfig

log = logging.getLogger("signals")


def _cmap(cfg: DatasetConfig) -> bp.ChannelMap:
    return bp.ChannelMap(power=dict(cfg.channel_power_keys),
                         counter_key=cfg.counter_key, time_key=cfg.time_key,
                         drive_axes=cfg.drive_axes)


def label_samples(power_df: pd.DataFrame, nc_df: pd.DataFrame,
                  cfg: DatasetConfig, nc_key: str = "n_number") -> pd.DataFrame:
    """Attach operation type and a time axis to each power sample.

    Time uses the measured timestamp if present, else a cumulative nominal dt.
    The result is the substrate for the power timeline plot and per-axis energy.
    """
    pdf = power_df.copy()
    pdf["dt_s"] = bp.sample_dt(pdf, cfg.nominal_dt_s)
    if "time_s" in pdf.columns:
        pdf["t_s"] = pdf["time_s"] - pdf["time_s"].iloc[0]
    else:
        pdf["t_s"] = pdf["dt_s"].cumsum() - pdf["dt_s"].iloc[0]
    if "counter" in pdf.columns and nc_key in nc_df.columns:
        merged = pdf.merge(nc_df[[nc_key, "operation"]], left_on="counter",
                           right_on=nc_key, how="left")
        merged["operation"] = merged["operation"].fillna("unmatched")
    else:
        merged = pdf
        merged["operation"] = "unknown"
    return merged


def axis_energy_breakdown(power_df: pd.DataFrame, nc_df: pd.DataFrame,
                          cfg: DatasetConfig, nc_key: str = "n_number") -> pd.DataFrame:
    """Energy (J) per drive axis per operation, with per-axis shares.

    Uses signed power so regenerated energy nets out (consistent with net energy
    accounting). energy_total_j is the drive-axes sum and excludes
    control/cooling, same boundary caveat as elsewhere.
    """
    merged = label_samples(power_df, nc_df, cfg, nc_key)
    axes = [a for a in cfg.drive_axes if f"power_{a}" in merged.columns]
    rows = []
    for op, g in merged.groupby("operation"):
        row = {"operation": op}
        tot = 0.0
        for a in axes:
            e = float((g[f"power_{a}"] * g["dt_s"]).sum())
            row[f"energy_{a}_j"] = e
            tot += e
        row["energy_total_j"] = tot
        rows.append(row)
    df = pd.DataFrame(rows).set_index("operation")
    for a in axes:
        df[f"share_{a}"] = np.where(df["energy_total_j"] != 0,
                                    df[f"energy_{a}_j"] / df["energy_total_j"], np.nan)
    # a tidy summed-over-operations view too
    df.loc["__all__"] = df.sum(numeric_only=True)
    tot_all = df.loc["__all__", "energy_total_j"]
    for a in axes:
        df.loc["__all__", f"share_{a}"] = (df.loc["__all__", f"energy_{a}_j"] / tot_all
                                           if tot_all else np.nan)
    return df


def corpus_sampling_sweep(manifest: pd.DataFrame, cfg: DatasetConfig, *,
                          rates=(1, 10, 50, 100, 250),
                          methods=("block_mean", "decimate"),
                          max_parts: Optional[int] = None) -> dict:
    """Run the sampling-rate energy-error test across the corpus.

    For every complete experiment and each meter model, downsample the power
    signal to each rate and measure energy error vs full rate. Aggregates to a
    corpus answer: if block_mean error stays near zero at 1 Hz but decimate does
    not, the H1 verdict is "1 Hz is adequate only if the meter integrates."
    """
    cmap = _cmap(cfg)
    complete = manifest[manifest["complete"]] if "complete" in manifest else manifest
    if max_parts:
        complete = complete.head(max_parts)

    frames = []
    for _, row in complete.iterrows():
        try:
            power = bp.load_power_json(row["energy_path"], cmap=cmap)
            for m in methods:
                err = bp.downsample_energy_error(
                    power, target_rates_hz=rates, source_hz=int(cfg.sampling_hz),
                    method=m)
                err["experiment"] = row["experiment"]
                frames.append(err)
        except Exception as exc:  # noqa: BLE001
            log.warning("sampling sweep failed on %s: %s", row["experiment"], exc)

    if not frames:
        return {"per_part": pd.DataFrame(), "summary": pd.DataFrame()}

    per_part = pd.concat(frames, ignore_index=True)
    g = per_part.groupby(["method", "rate_hz"])["error_pct"]
    summary = pd.DataFrame({
        "mean_error_pct": g.mean(),
        "worst_abs_error_pct": g.apply(lambda s: s.abs().max()),
    }).reset_index()
    return {"per_part": per_part, "summary": summary}
