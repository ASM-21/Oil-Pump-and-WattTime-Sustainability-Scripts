#!/usr/bin/env python3
"""
features.py
===========

Shared feature library. The analysis scripts (classify_operations.py,
estimate_energy.py, quality_check.py) all import this and point straight at the
folder of per-(program, operation) CSVs produced by split_operations.py. There is
no separate "build features" step to run.

Main entry point:
    table, groups = prepare(input_dir, granularity="segment")

segment granularity -> one row per operation pass, every numeric channel summarized
(mean, std, min, max, range, median, slope, auc), plus per-pass energy targets:
    energy_kwh_meter   forward-kWh meter delta over the pass (ground-truth energy)
    energy_wh_integral active-power integral over the pass, in Wh
sample granularity  -> one row per 1 Hz reading with elapsed_s added.

You can also run this file directly to dump a features CSV for inspection, but the
analysis scripts do not require it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

META_COLUMNS = [
    "program", "run", "source_file", "operation",
    "segment_id", "sample_index", "Time",
]

# Per-pass regression targets (never used as model inputs).
TARGET_COLUMNS = ["energy_kwh_meter", "energy_wh_integral"]

# Descriptive pass-level columns (kept, but tagged so callers can opt out).
DURATION_COLUMNS = ["n_samples", "duration_s"]

SENSOR_GROUP_PATTERNS: Dict[str, str] = {
    "energy":    r"power|voltage|current|kwh|frequency|power factor",
    "spindle":   r"spindle",
    "axis":      r"axis|position|feed|rapid|_load",
    "vibration": r"v_rms|a_rms|a_peak|crest",
    "thermal":   r"temp",
    "state":     r"block_number|part_count|machine_mode|override|runtime|time$",
}

STAT_FUNCS = ["mean", "std", "min", "max", "range", "median", "slope", "auc"]

# numpy 2.x renamed trapz -> trapezoid; support both.
_trapz = np.trapezoid if hasattr(np, "trapezoid") else np.trapz


# --- loading ----------------------------------------------------------------

def load_all(input_dir: str) -> pd.DataFrame:
    """Concatenate every per-operation CSV under input_dir (skips manifest)."""
    paths = sorted(Path(input_dir).rglob("*.csv"))
    paths = [p for p in paths if p.name != "manifest.csv"]
    if not paths:
        raise FileNotFoundError(f"No operation CSVs found under {input_dir}")
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    missing = {"operation", "segment_id", "source_file", "sample_index"} - set(df.columns)
    if missing:
        raise ValueError(f"Input CSVs missing columns {missing}. "
                         f"Did these come from split_operations.py?")
    return df


def find_numeric_channels(df: pd.DataFrame) -> List[str]:
    skip = set(META_COLUMNS) | {"elapsed_s"}
    channels = []
    for col in df.columns:
        if col in skip:
            continue
        if pd.to_numeric(df[col], errors="coerce").notna().any():
            channels.append(col)
    return channels


def add_elapsed(df: pd.DataFrame) -> pd.DataFrame:
    """Per-pass elapsed seconds from the start of each (source_file, segment_id)."""
    df = df.copy()
    grp = df.groupby(["source_file", "segment_id"])["sample_index"]
    df["elapsed_s"] = df["sample_index"] - grp.transform("min")
    return df


# --- energy channel detection ----------------------------------------------

def _match(channels: List[str], must_all: List[str], must_not: Optional[List[str]] = None):
    must_not = must_not or []
    for ch in channels:
        low = ch.lower()
        if all(t in low for t in must_all) and not any(t in low for t in must_not):
            return ch
    return None


def find_energy_channels(channels: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Locate the active-power and forward-kWh channels by name."""
    power = _match(channels, ["active", "power"]) or _match(channels, ["power"], ["factor"])
    fwd_kwh = _match(channels, ["forward", "kwh"]) or _match(channels, ["kwh"], ["reverse"])
    return power, fwd_kwh


# --- segment aggregation ----------------------------------------------------

def _slope(y: np.ndarray, x: np.ndarray) -> float:
    if len(y) < 2 or np.ptp(x) == 0:
        return 0.0
    return float(np.polyfit(x, y, 1)[0])


def summarize_segment(g: pd.DataFrame, channels: List[str]) -> Dict[str, float]:
    x = g["elapsed_s"].to_numpy(dtype=float)
    feats: Dict[str, float] = {
        "n_samples": float(len(g)),
        "duration_s": float(x.max() - x.min()) if len(g) else 0.0,
    }
    for ch in channels:
        y = pd.to_numeric(g[ch], errors="coerce").to_numpy(dtype=float)
        valid = ~np.isnan(y)
        yv, xv = y[valid], x[valid]
        if yv.size == 0:
            vals = {s: np.nan for s in STAT_FUNCS}
        else:
            vals = {
                "mean": float(np.mean(yv)), "std": float(np.std(yv)),
                "min": float(np.min(yv)), "max": float(np.max(yv)),
                "range": float(np.ptp(yv)), "median": float(np.median(yv)),
                "slope": _slope(yv, xv),
                "auc": float(_trapz(yv, xv)) if xv.size > 1 else 0.0,
            }
        for s, v in vals.items():
            feats[f"{ch}__{s}"] = v
    return feats


def build_segment_table(df: pd.DataFrame, channels: List[str]) -> pd.DataFrame:
    keys = ["program", "run", "source_file", "segment_id", "operation"]
    rows = [{**dict(zip(keys, kv)), **summarize_segment(g, channels)}
            for kv, g in df.groupby(keys, sort=False)]
    table = pd.DataFrame(rows)

    # Energy targets derived from the aggregated columns.
    power_ch, fwd_ch = find_energy_channels(channels)
    if fwd_ch and f"{fwd_ch}__max" in table:
        table["energy_kwh_meter"] = table[f"{fwd_ch}__max"] - table[f"{fwd_ch}__min"]
    if power_ch and f"{power_ch}__auc" in table:
        # auc is W*s (power in W, elapsed in s) -> Wh.
        table["energy_wh_integral"] = table[f"{power_ch}__auc"] / 3600.0
    return table


def build_sample_table(df: pd.DataFrame, channels: List[str]) -> pd.DataFrame:
    keep = [c for c in META_COLUMNS if c in df.columns] + ["elapsed_s"] + channels
    out = df[keep].copy()
    for ch in channels:
        out[ch] = pd.to_numeric(out[ch], errors="coerce")
    return out


def assign_groups(feature_cols: List[str], channels: List[str]) -> Dict[str, List[str]]:
    compiled = {g: re.compile(p, re.IGNORECASE) for g, p in SENSOR_GROUP_PATTERNS.items()}
    groups: Dict[str, List[str]] = {g: [] for g in SENSOR_GROUP_PATTERNS}
    for col in feature_cols:
        base = col.split("__")[0]
        if base not in channels and col not in channels:
            continue
        for g, rx in compiled.items():
            if rx.search(base):
                groups[g].append(col)
    return {g: cols for g, cols in groups.items() if cols}


# --- public entry point -----------------------------------------------------

def feature_columns(table: pd.DataFrame, include_duration: bool = True) -> List[str]:
    """Model-input columns: everything except meta + targets (+ optionally duration)."""
    drop = set(META_COLUMNS) | set(TARGET_COLUMNS)
    if not include_duration:
        drop |= set(DURATION_COLUMNS)
    return [c for c in table.columns if c not in drop]


def prepare(input_dir: str, granularity: str = "segment"
            ) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """Load the CSV folder and return (feature table, sensor-group map)."""
    df = add_elapsed(load_all(input_dir))
    channels = find_numeric_channels(df)
    if granularity == "segment":
        table = build_segment_table(df, channels)
        cols = feature_columns(table)
    else:
        table = build_sample_table(df, channels)
        cols = channels + ["elapsed_s"]
    groups = assign_groups(cols, channels)
    return table, groups


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Optional: dump a feature table from the per-operation CSV folder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--input", default="operation_csvs")
    ap.add_argument("--output", default="ml")
    ap.add_argument("--granularity", choices=["segment", "sample"], default="segment")
    args = ap.parse_args()

    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    table, groups = prepare(args.input, args.granularity)
    table.to_csv(out / f"features_{args.granularity}.csv", index=False)
    with (out / "feature_groups.json").open("w") as f:
        json.dump(groups, f, indent=2)
    print(f"Wrote {out}/features_{args.granularity}.csv "
          f"({table.shape[0]} rows x {table.shape[1]} cols)")
    print("Sensor groups:", {g: len(c) for g, c in groups.items()})
    if "energy_kwh_meter" in table or "energy_wh_integral" in table:
        tgt = [t for t in TARGET_COLUMNS if t in table]
        print("Energy targets available:", tgt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
