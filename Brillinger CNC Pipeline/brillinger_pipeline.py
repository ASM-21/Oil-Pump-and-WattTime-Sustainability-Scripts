"""
Brillinger CNC energy dataset -> operation-level energy pipeline.

Source: Brillinger et al. (2025), CNC Machining Data Repository, Mendeley Data
V2 (DOI 10.17632/gtvvwmz7r7.2); data descriptor in Data in Brief 61, 111814.

STATUS / READ THIS FIRST
------------------------
The raw JSON schema below was reconstructed from the descriptor and the
integration plan, NOT verified against an actual file in this build. Before you
trust any energy number:

    1. Run  `inspect_json(path)`  on one real .json file.
    2. Reconcile the printed top-level keys / channel names with CHANNEL_MAP.
    3. Confirm the counter field name (CYCLE vs HFProbeCounter) and what it
       indexes (NC line number vs executed-block index).

BOUNDARY NOTE (important for the IN-MaC comparison)
---------------------------------------------------
`power_drives_sum` is the sum of per-axis drive channels. It excludes control
electronics, cooling, and lighting. It is the drive-side total, not a
machine-input total. Your IAMMETER reads true machine input. Do not compare SEC
across the two datasets without explicitly accounting for that gap; baseline
subtraction does not fix it because the drive sum has essentially no constant
auxiliary load to subtract.

Optional deps (auto-detected, all features degrade gracefully without them):
    ijson    -> streaming JSON inspection for large files
    trimesh  -> mesh volume from STL for aggregate SEC
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import ijson  # type: ignore
    _HAVE_IJSON = True
except ImportError:
    _HAVE_IJSON = False

try:
    import trimesh  # type: ignore
    _HAVE_TRIMESH = True
except ImportError:
    _HAVE_TRIMESH = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NOMINAL_DT_S = 0.002          # 500 Hz sampling
SOURCE_HZ = 500
STOCK_DIMS_MM = (125.3, 19.34, 14.52)   # from descriptor, both materials

# Axis ordering per descriptor Section 3.2: X1, Y1, Z1, B1, C1, SP1, MAG1.
# NOTE: the plan's Section 6.1 pseudocode mislabels channel 5 as spindle and 6
# as C; that is corrected here. These keys are the UNVERIFIED default. If the
# JSON keys the power series by axis name ("POWER|X1") or some other scheme,
# override CHANNEL_MAP after inspecting a real file.
DEFAULT_POWER_KEYS = {
    "x": "POWER|1",
    "y": "POWER|2",
    "z": "POWER|3",
    "b": "POWER|4",
    "c": "POWER|5",
    "spindle": "POWER|6",
    "magazine": "POWER|7",
}


@dataclass
class ChannelMap:
    """Maps logical axes to JSON power-series keys and names the counter field.

    Everything is explicit so you can override per dataset version without
    touching parsing logic.
    """
    power: dict = field(default_factory=lambda: dict(DEFAULT_POWER_KEYS))
    counter_key: str = "CYCLE"            # or "HFProbeCounter"
    time_key: Optional[str] = None        # set if the JSON carries a timestamp
    # axes whose power counts toward the drive-side total. Magazine is included
    # only during tool changes in practice, but its idle draw is ~0, so summing
    # it is harmless. Drop "magazine" here if you want axes+spindle only.
    drive_axes: tuple = ("x", "y", "z", "b", "c", "spindle", "magazine")


CHANNEL_MAP = ChannelMap()


# ---------------------------------------------------------------------------
# 1. Schema discovery  (run this on a real file before anything else)
# ---------------------------------------------------------------------------

def inspect_json(path: str | Path, sample: int = 5) -> dict:
    """Print and return a structural summary of one JSON file.

    Uses ijson to peek at top-level keys cheaply when available; otherwise
    falls back to a full load. Reports layout (columnar dict-of-arrays vs
    row-oriented list-of-records), key names, lengths, and a few sample values.
    """
    path = Path(path)
    size_mb = path.stat().st_size / 1e6
    print(f"file: {path.name}  ({size_mb:.1f} MB)")

    summary: dict = {"file": str(path), "size_mb": round(size_mb, 1)}

    if _HAVE_IJSON and size_mb > 50:
        # cheap top-level key enumeration without loading the whole file
        keys = []
        with open(path, "rb") as f:
            parser = ijson.parse(f)
            depth = 0
            for prefix, event, value in parser:
                if event == "map_key" and prefix == "":
                    keys.append(value)
                if event in ("start_array", "start_map"):
                    depth += 1
                elif event in ("end_array", "end_map"):
                    depth -= 1
                # stop once we have left the top-level container
                if depth == 0 and keys:
                    break
        summary["layout"] = "dict (top-level keys, streamed)"
        summary["top_level_keys"] = keys
        print(f"layout: dict   top-level keys: {keys}")
        print("note: streamed peek; load fully to inspect array contents.")
        return summary

    with open(path) as f:
        data = json.load(f)

    if isinstance(data, dict):
        summary["layout"] = "dict (columnar)"
        print("layout: dict (columnar, key -> series)")
        rows = []
        for k, v in data.items():
            n = len(v) if hasattr(v, "__len__") else 1
            head = v[:sample] if isinstance(v, (list, tuple)) else v
            rows.append({"key": k, "type": type(v).__name__, "len": n,
                         "head": head})
        df = pd.DataFrame(rows)
        with pd.option_context("display.max_colwidth", 60,
                               "display.width", 120):
            print(df.to_string(index=False))
        summary["keys"] = list(data.keys())

    elif isinstance(data, list):
        summary["layout"] = "list (row-oriented)"
        print(f"layout: list of {len(data)} records")
        first = data[0] if data else {}
        if isinstance(first, dict):
            print(f"record keys: {list(first.keys())}")
            print(f"first record: {first}")
            summary["record_keys"] = list(first.keys())
        summary["n_records"] = len(data)
    else:
        summary["layout"] = type(data).__name__
        print(f"unexpected top-level type: {type(data).__name__}")

    return summary


# ---------------------------------------------------------------------------
# 2. Power time series
# ---------------------------------------------------------------------------

def load_power_json(path: str | Path,
                    cmap: ChannelMap = CHANNEL_MAP,
                    negative_power: str = "keep") -> pd.DataFrame:
    """Load one JSON file into a tidy power DataFrame.

    Handles both columnar (dict of arrays) and row-oriented (list of records)
    layouts. Output columns: sample, counter, [time_s], power_<axis>...,
    power_drives_sum.

    negative_power policy:
        "keep"  signed sum -> net energy (default; correct for grid accounting
                because regenerated energy offsets draw).
        "clip"  max(P, 0) per channel before summing.
        "abs"   |P| per channel (the plan's choice; overcounts regen, kept as
                an option for comparison only).
    """
    if negative_power not in ("keep", "clip", "abs"):
        raise ValueError("negative_power must be keep|clip|abs")

    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    # normalize to a columnar dict
    if isinstance(data, list):
        data = {k: [rec.get(k) for rec in data] for k in data[0].keys()}
    elif not isinstance(data, dict):
        raise TypeError(f"unsupported JSON top-level type: {type(data).__name__}")

    missing = [k for k in cmap.power.values() if k not in data]
    if missing:
        warnings.warn(
            f"power keys not found in JSON: {missing}. Run inspect_json and fix "
            f"ChannelMap.power. Available keys: {list(data.keys())[:20]}"
        )

    n = max((len(data[k]) for k in cmap.power.values() if k in data), default=0)
    out = {"sample": np.arange(n)}

    if cmap.counter_key in data:
        out["counter"] = np.asarray(data[cmap.counter_key])
    else:
        warnings.warn(f"counter key '{cmap.counter_key}' not found; NC "
                      "alignment will be unavailable.")

    if cmap.time_key and cmap.time_key in data:
        out["time_s"] = np.asarray(data[cmap.time_key], dtype=float)

    def _coerce(key: str) -> np.ndarray:
        arr = np.asarray(data.get(key, np.zeros(n)), dtype=float)
        if negative_power == "clip":
            arr = np.clip(arr, 0, None)
        elif negative_power == "abs":
            arr = np.abs(arr)
        return arr

    for axis, key in cmap.power.items():
        out[f"power_{axis}"] = _coerce(key)

    df = pd.DataFrame(out)
    df["power_drives_sum"] = df[[f"power_{a}" for a in cmap.drive_axes]].sum(axis=1)
    return df


def sample_dt(df: pd.DataFrame, nominal_dt: float = NOMINAL_DT_S,
              max_gap_factor: float = 5.0) -> np.ndarray:
    """Per-sample dt in seconds.

    Uses measured time deltas when a time_s column exists, capping gaps at
    max_gap_factor x nominal so sensor dropouts do not inflate integrated
    energy. Falls back to a constant nominal dt otherwise.
    """
    if "time_s" in df.columns:
        dt = np.diff(df["time_s"].to_numpy(), prepend=df["time_s"].iloc[0] - nominal_dt)
        dt = np.clip(dt, 0, nominal_dt * max_gap_factor)
        return dt
    return np.full(len(df), nominal_dt)


# ---------------------------------------------------------------------------
# 3. NC code (Sinumerik MPF)
# ---------------------------------------------------------------------------

# Sinumerik uses ';' for line comments. Parentheses are function arguments
# (e.g. CYCLE82(...)), NOT comments, so they are preserved.
_WORD = re.compile(r"([A-Z]+)\s*=?\s*([+-]?\d*\.?\d+)?")
_CYCLE = re.compile(r"\bCYCLE\d+\b")
_NBLOCK = re.compile(r"^/?\s*N(\d+)")
_AXIS_WORDS = {"X", "Y", "Z", "A", "B", "C"}


def tokenize_gcode_line(line: str) -> dict:
    """Parse one NC block into address->value plus lists of G/M codes.

    Captures the Sinumerik block number N as 'n_number' (kept separate so it
    can serve as an alignment key), and flags whether the block carries a
    coordinate axis word ('has_axis_word'), which distinguishes a real motion
    block from a pure mode-setting block.
    """
    line = line.split(";", 1)[0].strip()
    if not line:
        return {}

    n_match = _NBLOCK.match(line)
    n_number = int(n_match.group(1)) if n_match else None
    body = line[n_match.end():] if n_match else line

    tokens: dict = {"g_codes": [], "m_codes": [], "cycles": _CYCLE.findall(body),
                    "n_number": n_number, "has_axis_word": False}
    for letter, num in _WORD.findall(body):
        if letter == "G" and num not in (None, ""):
            tokens["g_codes"].append(f"G{int(float(num))}")
        elif letter == "M" and num not in (None, ""):
            tokens["m_codes"].append(f"M{int(float(num))}")
        elif letter in _AXIS_WORDS:
            tokens["has_axis_word"] = True
            if num not in (None, ""):
                tokens[letter] = float(num)
        elif num not in (None, ""):
            tokens[letter] = float(num)
    return tokens


def _norm_motion(code: str) -> str:
    return {"G00": "G0", "G01": "G1", "G02": "G2", "G03": "G3"}.get(code, code)


def parse_mpf(path: str | Path) -> pd.DataFrame:
    """Parse a Sinumerik MPF into a per-block table with modal state.

    Modal state (motion mode, feed F, speed S, tool T, spindle on/off) is
    carried forward across blocks, then each block is classified.
    """
    state = {"motion": None, "F": 0.0, "S": 0.0, "T": None, "spindle_on": False,
             "x": None, "y": None, "z": None, "abs_mode": True}
    blocks = []

    for file_line, raw in enumerate(Path(path).read_text(errors="ignore").splitlines()):
        tok = tokenize_gcode_line(raw)
        if not tok:
            continue

        g_codes = tok.get("g_codes", [])
        m_codes = tok.get("m_codes", [])

        if any(m in ("M3", "M03", "M4", "M04") for m in m_codes):
            state["spindle_on"] = True
        if any(m in ("M5", "M05") for m in m_codes):
            state["spindle_on"] = False

        if "G90" in g_codes:
            state["abs_mode"] = True
        if "G91" in g_codes:
            state["abs_mode"] = False

        for g in g_codes:
            if _norm_motion(g) in {"G0", "G1", "G2", "G3"}:
                state["motion"] = _norm_motion(g)
        if "F" in tok:
            state["F"] = tok["F"]
        if "S" in tok:
            state["S"] = tok["S"]
        if "T" in tok:
            state["T"] = tok["T"]

        # position update: record start, apply axis words, record end
        x0, y0, z0 = state["x"], state["y"], state["z"]

        def _upd(axis_letter, cur):
            if axis_letter in tok:
                v = tok[axis_letter]
                if state["abs_mode"] or cur is None:
                    return v
                return cur + v
            return cur

        state["x"] = _upd("X", state["x"])
        state["y"] = _upd("Y", state["y"])
        state["z"] = _upd("Z", state["z"])

        # first motion seeds position; treat as zero-length so we never sweep
        # a phantom segment from an unknown origin
        if x0 is None and state["x"] is not None:
            x0 = state["x"]
        if y0 is None and state["y"] is not None:
            y0 = state["y"]
        if z0 is None and state["z"] is not None:
            z0 = state["z"]

        tool_change = any(m in ("M6", "M06") for m in m_codes)
        dwell = any(g in ("G4", "G04") for g in g_codes)

        blocks.append({
            "n_number": tok.get("n_number"),
            "file_line": file_line,
            "motion": state["motion"],
            "has_axis_word": tok.get("has_axis_word", False),
            "F": state["F"],
            "S": state["S"],
            "T": state["T"],
            "spindle_on": state["spindle_on"],
            "tool_change": tool_change,
            "dwell": dwell,
            "cycles": ",".join(tok.get("cycles", [])),
            "x0": x0, "y0": y0, "z0": z0,
            "x1": state["x"], "y1": state["y"], "z1": state["z"],
            "I": tok.get("I"), "J": tok.get("J"), "K": tok.get("K"),
            "CR": tok.get("CR"),
        })

    df = pd.DataFrame(blocks).reset_index(drop=True)
    df["block_index"] = np.arange(len(df))
    df["line_number"] = df["file_line"]
    df["operation"] = df.apply(classify_operation, axis=1)
    return df


def classify_operation(block) -> str:
    """Classify an NC block into an energy-relevant operation type.

    A block is treated as a motion (rapid/cutting/positioning) only if it
    carries a coordinate axis word. A block that merely sets a modal motion
    mode or toggles the spindle, with no axis target, is 'other'. This prevents
    pure mode-setting lines from inheriting the modal G-code and being
    miscounted as moves.

    Caveat: this is still commanded-state classification. A G1 feed move in air
    with the spindle on is labeled 'cutting' here; use
    refine_cutting_with_power() to separate true cutting from air moves using
    measured spindle power.
    """
    if block["tool_change"]:
        return "tool_change"
    if block["dwell"]:
        return "dwell"
    if not block.get("has_axis_word", False):
        return "other"
    motion = block["motion"]
    if motion == "G0":
        return "rapid"
    if motion in ("G1", "G2", "G3"):
        if block["spindle_on"] and block["F"] > 0:
            return "cutting"
        return "positioning"
    return "other"


# ---------------------------------------------------------------------------
# 4. Align power to NC and integrate energy
# ---------------------------------------------------------------------------

def align_and_integrate(power_df: pd.DataFrame,
                        nc_df: pd.DataFrame,
                        nc_key: str = "line_number",
                        nominal_dt: float = NOMINAL_DT_S) -> dict:
    """Attach operation labels to power samples and integrate energy.

    The power 'counter' column is merged onto nc_df[nc_key]. Candidates:
    'n_number' (the Sinumerik N block number), 'line_number'/'file_line' (raw
    file position), or 'block_index' (sequential executed block). Verify which
    one the counter encodes against a real file; this is the single most
    error-prone link in the pipeline.

    Returns a dict with the merged frame and energy aggregated by operation and
    by block.
    """
    if "counter" not in power_df.columns:
        raise ValueError("power_df has no 'counter' column; cannot align to NC.")

    pdf = power_df.copy()
    pdf["dt_s"] = sample_dt(pdf, nominal_dt)
    pdf["energy_j"] = pdf["power_drives_sum"] * pdf["dt_s"]

    merge_cols = [c for c in [nc_key, "operation", "S", "F", "T"]
                  if c in nc_df.columns]
    merged = pdf.merge(
        nc_df[merge_cols],
        left_on="counter", right_on=nc_key, how="left",
    )
    unmatched = merged["operation"].isna().mean()
    if unmatched > 0.01:
        warnings.warn(f"{unmatched:.1%} of power samples did not match an NC "
                      f"block on nc_key='{nc_key}'. Check counter semantics.")
    merged["operation"] = merged["operation"].fillna("unmatched")

    by_op = (merged.groupby("operation")["energy_j"]
             .agg(["sum", "count"])
             .rename(columns={"sum": "energy_j", "count": "n_samples"}))
    by_op["share"] = by_op["energy_j"] / by_op["energy_j"].sum()
    by_op["time_s"] = by_op["n_samples"] * nominal_dt

    by_block = merged.groupby("counter")["energy_j"].sum()

    return {"merged": merged, "by_operation": by_op, "by_block": by_block,
            "total_energy_j": float(pdf["energy_j"].sum())}


def refine_cutting_with_power(merged: pd.DataFrame,
                              spindle_col: str = "power_spindle",
                              quantile: float = 0.95) -> pd.DataFrame:
    """Reclassify 'cutting' vs air moves using measured spindle power.

    Estimates an idle-spindle baseline from rapids (spindle on, no cut), sets a
    threshold above it, and relabels feed blocks below threshold as
    'air_move'. Returns a copy with an 'operation_refined' column.
    """
    out = merged.copy()
    if spindle_col not in out.columns:
        warnings.warn(f"{spindle_col} missing; skipping refinement.")
        out["operation_refined"] = out["operation"]
        return out

    idle = out.loc[out["operation"] == "rapid", spindle_col]
    baseline = idle.median() if len(idle) else 0.0
    spread = idle.std() if len(idle) else 0.0
    threshold = baseline + 3 * spread if spread else baseline * 1.1

    out["operation_refined"] = out["operation"]
    feed = out["operation"] == "cutting"
    out.loc[feed & (out[spindle_col] <= threshold), "operation_refined"] = "air_move"
    return out


# ---------------------------------------------------------------------------
# 5. Specific cutting energy
# ---------------------------------------------------------------------------

def stock_volume_mm3(dims_mm: tuple = STOCK_DIMS_MM) -> float:
    return float(np.prod(dims_mm))


def mesh_volume_mm3(stl_path: str | Path) -> float:
    """Solid volume of a part from STL (requires trimesh). Assumes mm units."""
    if not _HAVE_TRIMESH:
        raise ImportError("trimesh not installed; cannot compute mesh volume.")
    mesh = trimesh.load(str(stl_path))
    if not mesh.is_watertight:
        warnings.warn("mesh is not watertight; volume may be unreliable.")
    return float(mesh.volume)


def compute_sec(cutting_energy_j: float,
                volume_removed_mm3: float,
                per_op_energy: Optional[dict] = None,
                per_op_volume: Optional[dict] = None) -> dict:
    """Specific cutting energy in J/mm^3.

    Aggregate SEC = cutting energy / volume removed. Per-operation SEC requires
    per-operation removed volume, which the power data cannot supply on its own
    (needs CAM simulation or depth/width-of-cut extraction from the NC code).
    Provide per_op_volume to get a per-op breakdown.
    """
    result = {}
    if volume_removed_mm3 <= 0:
        warnings.warn("volume_removed_mm3 <= 0; aggregate SEC undefined.")
        result["sec_aggregate"] = float("nan")
    else:
        sec = cutting_energy_j / volume_removed_mm3
        result["sec_aggregate"] = sec
        if not (0.1 <= sec <= 100):
            warnings.warn(f"aggregate SEC {sec:.2f} J/mm^3 outside the plausible "
                          "0.1-100 range; check units and volume.")

    if per_op_energy and per_op_volume:
        result["sec_by_operation"] = {
            op: per_op_energy[op] / per_op_volume[op]
            for op in per_op_volume if per_op_volume.get(op, 0) > 0
        }
    return result


# ---------------------------------------------------------------------------
# 6. Sampling-rate sensitivity (H1)  -- boundary-independent, runs as-is
# ---------------------------------------------------------------------------

def downsample_energy_error(power_df: pd.DataFrame,
                            target_rates_hz=(1, 10, 50, 100, 250),
                            source_hz: int = SOURCE_HZ,
                            method: str = "block_mean") -> pd.DataFrame:
    """Energy error from reducing the power signal to lower rates.

    Two models, because the answer to "is 1 Hz adequate" depends on how the
    low-rate device behaves:

        "block_mean" : average power over each 1/rate interval, then integrate.
            Models an integrating / averaging energy meter (most real meters,
            including typical clamp meters). Lossless for energy by
            construction, so error reflects only edge truncation.
        "decimate"   : take every Nth sample (point sampling). Models a device
            that snapshots instantaneous power. Phase-dependent: a transient
            can be over- or under-counted depending on sample alignment.

    Report whichever matches the meter you are comparing against. For the
    IN-MaC IAMMETER, confirm whether it integrates or snapshots before citing a
    1 Hz adequacy number.
    """
    if method not in ("block_mean", "decimate"):
        raise ValueError("method must be block_mean|decimate")

    power = power_df["power_drives_sum"].to_numpy()
    dt = 1.0 / source_hz
    ref = float(np.sum(power) * dt)

    rows = []
    for rate in target_rates_hz:
        step = max(1, int(round(source_hz / rate)))
        if method == "decimate":
            ds = power[::step]
            est = float(np.sum(ds) * step * dt)
        else:  # block_mean
            n_full = (len(power) // step) * step
            blocks = power[:n_full].reshape(-1, step).mean(axis=1)
            est = float(np.sum(blocks) * step * dt)
            # add the truncated tail as a partial block so energy is conserved
            tail = power[n_full:]
            if len(tail):
                est += float(tail.mean() * len(tail) * dt)
        rows.append({"rate_hz": rate, "decimation": step, "method": method,
                     "energy_j": est, "ref_j": ref,
                     "error_pct": 100.0 * (est - ref) / ref if ref else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def sanity_checks(integ: dict, sec: Optional[dict] = None) -> dict:
    by_op = integ["by_operation"]
    checks = {
        "total_energy_positive": integ["total_energy_j"] > 0,
        "shares_sum_to_one": abs(by_op["share"].sum() - 1.0) < 1e-6,
    }
    if "cutting" in by_op.index:
        checks["cutting_lt_total"] = (
            by_op.loc["cutting", "energy_j"] < integ["total_energy_j"]
        )
    if sec and not np.isnan(sec.get("sec_aggregate", np.nan)):
        checks["sec_in_range"] = 0.1 <= sec["sec_aggregate"] <= 100
    return checks


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli():
    p = argparse.ArgumentParser(description="Brillinger CNC energy pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_ins = sub.add_parser("inspect", help="summarize one JSON file's structure")
    s_ins.add_argument("json")

    s_en = sub.add_parser("energy", help="energy by operation from JSON + MPF")
    s_en.add_argument("json")
    s_en.add_argument("mpf")
    s_en.add_argument("--nc-key", default="n_number",
                      choices=["n_number", "line_number", "file_line", "block_index"])
    s_en.add_argument("--volume", type=float, default=None,
                      help="volume removed (mm^3) for aggregate SEC")

    s_sr = sub.add_parser("sampling", help="sampling-rate energy error (H1)")
    s_sr.add_argument("json")

    args = p.parse_args()

    if args.cmd == "inspect":
        inspect_json(args.json)

    elif args.cmd == "energy":
        power = load_power_json(args.json)
        nc = parse_mpf(args.mpf)
        integ = align_and_integrate(power, nc, nc_key=args.nc_key)
        print("\nenergy by operation:")
        print(integ["by_operation"].to_string())
        print(f"\ntotal drive energy: {integ['total_energy_j']:.1f} J "
              f"({integ['total_energy_j'] / 3600:.4f} Wh)")
        if args.volume:
            cut = integ["by_operation"].loc["cutting", "energy_j"] \
                if "cutting" in integ["by_operation"].index else 0.0
            sec = compute_sec(cut, args.volume)
            print(f"aggregate SEC: {sec['sec_aggregate']:.2f} J/mm^3")
        print("\nsanity:", sanity_checks(integ))

    elif args.cmd == "sampling":
        power = load_power_json(args.json)
        print(downsample_energy_error(power).to_string(index=False))


if __name__ == "__main__":
    _cli()
