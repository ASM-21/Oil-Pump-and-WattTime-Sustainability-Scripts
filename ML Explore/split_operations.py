#!/usr/bin/env python3
"""
split_operations.py
===================

Take a directory of long-format CNC monitoring CSVs (Dataname / Value / Time,
~70 channels per 1 Hz sample) and produce one wide CSV per (program, operation)
pair, with all runs of the same program concatenated. Built for downstream ML on
specific operations: every channel is kept (not just power), and identity columns
(run, source_file, segment_id) are preserved so runs/passes can still be split in
pandas later.

What it does, per source file:
  1. Pivot long -> wide (one row per timestamp, every Dataname becomes a column).
  2. Tag each row with the active operation (processKindId) and a segment_id that
     increments on every operation change (so individual passes are recoverable).
  3. Drop idle rows where processKindId == NONE (toggle with --keep-idle).
  4. Parse program + run from the filename (e.g. AL6061_body01_p1 -> program
     "body_p1", run "01").

Then across all files it groups by (program, operation) and writes:
  <output>/<program>/<operation>.csv
plus a manifest CSV and a discovered_operations.json you can fill in with readable
operation names and re-run for nicer filenames.

Usage
-----
  python split_operations.py --input ./data --output ./operation_csvs
  python split_operations.py --input ./data --names operation_names.json
  python split_operations.py            # uses defaults: input=., output=./operation_csvs

Operation-name mapping (optional)
---------------------------------
Pass --names pointing at a JSON file mapping processKindId UUID -> readable name:
  { "1f8e...": "drilling", "9a02...": "cavity_milling" }
Any UUID not in the map is written out with its raw UUID as the filename, and is
also listed in discovered_operations.json so you can name it and re-run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np


# --- Configuration defaults (override via CLI) ------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = str(_SCRIPT_DIR.parent / "Al6061")
DEFAULT_OUTPUT_DIR = str(_SCRIPT_DIR / "operation_csvs")
DEFAULT_PATTERN = "*.csv"

# The channel whose value identifies the active operation.
OPERATION_CHANNEL = "processKindId"
# Value that marks "no operation active" (idle / between operations).
IDLE_VALUE = "NONE"

# Channels kept as raw strings (never coerced to numeric). Everything else is
# coerced to numeric where possible; values that will not parse become NaN.
TEXT_CHANNELS = {
    "processKindId",
    "partKindId",
    "featureId",
    "Program_Name_Running",
    "Controller_Mode",
    "EStop_State",
}

# Identity / bookkeeping columns this script adds. Placed first in each output.
META_COLUMNS = [
    "program",
    "run",
    "source_file",
    "operation",
    "segment_id",
    "sample_index",
    "Time",
]


# --- Filename parsing -------------------------------------------------------

DEFAULT_PART_TYPES = "body,lid"


def build_filename_re(part_types: str) -> "re.Pattern":
    """Compile the filename pattern for the given comma-separated part keywords."""
    parts = "|".join(re.escape(p.strip()) for p in part_types.split(",") if p.strip())
    parts = parts or "part"
    return re.compile(
        rf"(?P<part>{parts})\s*(?P<instance>\d+)?[ _-]*p(?P<program>\d+)"
        rf"(?:[ _-]*run[ _-]*(?P<run>\d+))?",
        re.IGNORECASE,
    )


def parse_filename(stem: str, regex: "re.Pattern") -> Dict[str, object]:
    """
    Derive (program, run, source_file, matched) from a file stem.

    program: e.g. "body_p1", "lid_p2" (part type + program number).
    run:     trial identifier (the instance number, plus _runN if present).
    source_file: always the full stem, so grouping is never ambiguous even when
                 the pattern does not match.
    matched: whether the pattern matched (False means the fallback was used).
    """
    m = regex.search(stem)
    if not m:
        # Fallback: cannot parse, so treat the whole stem as its own program and
        # run. No data is dropped; it just will not group with sibling runs.
        return {"program": stem, "run": stem, "source_file": stem, "matched": False}

    part = m.group("part").lower()
    program_num = m.group("program")
    instance = m.group("instance")
    explicit_run = m.group("run")

    program = f"{part}_p{program_num}"
    if explicit_run and instance:
        run = f"{instance}_run{explicit_run}"
    elif explicit_run:
        run = f"run{explicit_run}"
    elif instance:
        run = instance
    else:
        run = "0"

    return {"program": program, "run": run, "source_file": stem, "matched": True}


# --- Long -> wide -----------------------------------------------------------

def normalize_long(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize column names to Dataname / Value / Time (case/whitespace tolerant)
    and strip surrounding whitespace from the key string fields.
    """
    rename = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key == "dataname":
            rename[col] = "Dataname"
        elif key == "value":
            rename[col] = "Value"
        elif key == "time":
            rename[col] = "Time"
    df = df.rename(columns=rename)

    missing = {"Dataname", "Value", "Time"} - set(df.columns)
    if missing:
        raise ValueError(
            f"Expected long-format columns Dataname/Value/Time, missing {missing}. "
            f"Found: {list(df.columns)}"
        )

    df = df[["Dataname", "Value", "Time"]].copy()
    df["Dataname"] = df["Dataname"].astype(str).str.strip()
    df["Value"] = df["Value"].astype(str).str.strip()
    df["Time"] = df["Time"].astype(str).str.strip()
    return df


def _block_ids(datanames: np.ndarray) -> np.ndarray:
    """Start a new sample whenever a Dataname repeats. Robust, sequential scan."""
    seen: set = set()
    sid = 0
    ids = np.empty(len(datanames), dtype=np.int64)
    for i, name in enumerate(datanames):
        if name in seen:
            sid += 1
            seen = {name}
        else:
            seen.add(name)
        ids[i] = sid
    return ids


def compute_sample_ids(df_long: pd.DataFrame, method: str = "auto") -> Tuple[np.ndarray, str]:
    """
    Assign each row to a 1 Hz sample. Returns (ids, method_used).

    'time'   : factorize the Time column in first-appearance order. Fast (vectorized)
               and robust to occasional missing channels. Valid only when each Time is
               unique to one sample, which is checked by confirming the codes are
               non-decreasing (each Time value is contiguous in the file).
    'blocks' : start a new sample whenever a Dataname repeats. Robust to the Time
               format and to missing channels, but a Python scan (slower on huge files).
    'auto'   : use 'time' when it validates, else fall back to 'blocks'.
    """
    if method in ("auto", "time"):
        codes, _ = pd.factorize(df_long["Time"], sort=False)
        contiguous = bool(codes.size > 0 and np.all(np.diff(codes) >= 0))
        n_unique = int(codes.max() + 1) if codes.size else 0
        # Reject if Time looks unique-per-row (would make every row its own sample).
        # A real sample holds ~n_channels rows, so expect far fewer unique Times.
        n_channels = max(df_long["Dataname"].nunique(), 1)
        expected = len(df_long) / n_channels
        plausible = n_unique <= 1.5 * expected if method == "auto" else True
        if contiguous and n_unique > 1 and plausible:
            return codes.astype(np.int64), "time"
        if method == "time":
            print("  ! Time is not unique/contiguous per sample; using block detection.",
                  file=sys.stderr)
    return _block_ids(df_long["Dataname"].to_numpy()), "blocks"


def long_to_wide(df_long: pd.DataFrame, method: str = "auto") -> Tuple[pd.DataFrame, str]:
    """Pivot a normalized long frame to wide: one row per sample, channels as columns."""
    df_long = df_long.copy()
    ids, used = compute_sample_ids(df_long, method)
    df_long["__sample__"] = ids

    wide = df_long.pivot_table(
        index="__sample__",
        columns="Dataname",
        values="Value",
        aggfunc="first",
    )
    wide.columns.name = None

    # One representative Time per sample (first occurrence in the block).
    times = df_long.groupby("__sample__")["Time"].first()
    wide.insert(0, "Time", times)

    wide = wide.sort_index()
    wide["sample_index"] = wide.index  # original tick index within this file
    wide = wide.reset_index(drop=True)
    return wide, used


# --- Tagging ----------------------------------------------------------------

def tag_wide(
    wide: pd.DataFrame,
    meta: Dict[str, str],
    keep_idle: bool,
) -> pd.DataFrame:
    """Add operation / program / run / segment_id columns and drop idle rows."""
    if OPERATION_CHANNEL not in wide.columns:
        raise ValueError(
            f"Operation channel '{OPERATION_CHANNEL}' not found after pivot. "
            f"Columns present: {list(wide.columns)[:15]}..."
        )

    wide = wide.copy()
    op = wide[OPERATION_CHANNEL].astype(str).str.strip()

    # segment_id increments on every operation change, computed BEFORE dropping
    # idle so each contiguous pass keeps a stable id even across idle gaps.
    wide["segment_id"] = (op != op.shift()).cumsum()

    wide["program"] = meta["program"]
    wide["run"] = meta["run"]
    wide["source_file"] = meta["source_file"]
    wide["operation_uuid"] = op

    if not keep_idle:
        wide = wide[op != IDLE_VALUE].copy()

    return wide


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce every non-text, non-meta column to numeric; unparseable -> NaN."""
    protected = set(META_COLUMNS) | TEXT_CHANNELS | {"operation_uuid"}
    df = df.copy()
    for col in df.columns:
        if col in protected:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# --- Naming helpers ---------------------------------------------------------

def slugify(text: str) -> str:
    """Filesystem-safe slug: lowercase, non-alphanumeric -> underscore."""
    text = str(text).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def load_name_map(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"  ! name map '{path}' not found, using raw UUIDs", file=sys.stderr)
        return {}
    with p.open() as f:
        raw = json.load(f)
    return {str(k).strip(): str(v).strip() for k, v in raw.items()}


def operation_label(uuid: str, name_map: Dict[str, str]) -> str:
    """Readable name if mapped, else the raw UUID. Used for the filename."""
    return name_map.get(uuid, uuid)


# --- Output ordering --------------------------------------------------------

def order_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Meta columns first, then channels alphabetically. Drop helper columns."""
    df = df.drop(columns=["operation_uuid"], errors="ignore")
    meta = [c for c in META_COLUMNS if c in df.columns]
    channels = sorted(c for c in df.columns if c not in meta)
    return df[meta + channels]


# --- Main pipeline ----------------------------------------------------------

def clean_output(out_path: Path) -> None:
    """
    Remove previously generated content so a re-run (e.g. with a different
    --names map) does not leave orphan CSVs behind. Only touches files this
    script creates: *.csv anywhere under the output dir, plus the manifest and
    discovered-operations files. Then prunes empty subdirectories.
    """
    if not out_path.exists():
        return
    for f in out_path.rglob("*.csv"):
        f.unlink()
    for name in ("manifest.csv", "discovered_operations.json"):
        p = out_path / name
        if p.exists():
            p.unlink()
    for d in sorted(out_path.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


def inspect_files(files, regex, pivot_method) -> int:
    """Dry run: report schema, sample detection, operations, and filename parsing
    for each file without writing anything. Use before a real run to catch surprises."""
    print(f"DRY RUN: inspecting {len(files)} file(s), nothing will be written.\n")
    unmatched = []
    all_ops = set()
    for fp in files:
        try:
            df_long = normalize_long(pd.read_csv(fp))
        except Exception as exc:  # noqa: BLE001
            print(f"  {fp.name}: ERROR - {exc}")
            continue
        meta = parse_filename(fp.stem, regex)
        ids, used = compute_sample_ids(df_long, pivot_method)
        n_samples = int(ids.max() + 1) if len(ids) else 0
        n_channels = df_long["Dataname"].nunique()
        ops = (df_long.loc[df_long["Dataname"] == OPERATION_CHANNEL, "Value"]
               .unique().tolist() if OPERATION_CHANNEL in set(df_long["Dataname"]) else [])
        active = [o for o in ops if o != IDLE_VALUE]
        all_ops.update(active)
        if not meta["matched"]:
            unmatched.append(fp.name)
        flag = "" if meta["matched"] else "  [FILENAME NOT PARSED -> own program]"
        op_note = f"{len(active)} operation(s)" if OPERATION_CHANNEL in set(df_long["Dataname"]) \
            else f"NO '{OPERATION_CHANNEL}' CHANNEL"
        print(f"  {fp.name:32s} program={str(meta['program'])[:12]:12s} "
              f"samples={n_samples:5d} channels={n_channels:3d} pivot={used:6s} {op_note}{flag}")

    print(f"\nSummary: {len(all_ops)} distinct operation UUID(s) across files.")
    if unmatched:
        print(f"  {len(unmatched)} file(s) did not match the filename pattern: "
              f"{unmatched[:5]}{' ...' if len(unmatched) > 5 else ''}")
        print("  Set --part-types to your part keywords (e.g. --part-types body,lid,bracket).")
    else:
        print("  All filenames parsed.")
    print("\nIf this looks right, re-run without --dry-run.")
    return 0


def process(
    input_dir: str,
    output_dir: str,
    pattern: str,
    names_path: Optional[str],
    keep_idle: bool,
    part_types: str = DEFAULT_PART_TYPES,
    pivot_method: str = "auto",
    dry_run: bool = False,
) -> int:
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    if not in_path.is_dir():
        print(f"Input directory not found: {in_path}", file=sys.stderr)
        return 1

    files = sorted(in_path.glob(pattern))
    if not files:
        print(f"No files matching '{pattern}' in {in_path}", file=sys.stderr)
        return 1

    regex = build_filename_re(part_types)

    if dry_run:
        return inspect_files(files, regex, pivot_method)

    clean_output(out_path)
    name_map = load_name_map(names_path)
    tagged_frames: List[pd.DataFrame] = []
    methods_used: Dict[str, int] = {}
    unmatched: List[str] = []

    print(f"Found {len(files)} file(s) matching '{pattern}'\n")
    for fp in files:
        meta = parse_filename(fp.stem, regex)
        if not meta["matched"]:
            unmatched.append(fp.name)
        try:
            df_long = normalize_long(pd.read_csv(fp))
            wide, used = long_to_wide(df_long, pivot_method)
            methods_used[used] = methods_used.get(used, 0) + 1
            tagged = tag_wide(wide, meta, keep_idle)
            tagged = coerce_numeric(tagged)
        except Exception as exc:  # noqa: BLE001 - report and continue per file
            print(f"  ! skipped {fp.name}: {exc}", file=sys.stderr)
            continue

        n_ops = tagged["operation_uuid"].nunique()
        print(f"  {fp.name:35s} -> program={str(meta['program']):8s} "
              f"run={str(meta['run']):8s} rows={len(tagged):5d} ops={n_ops}")
        tagged_frames.append(tagged)

    if not tagged_frames:
        print("\nNothing processed.", file=sys.stderr)
        return 1

    combined = pd.concat(tagged_frames, ignore_index=True)

    # Collect every operation UUID seen, for the discovered-operations file.
    all_uuids = sorted(u for u in combined["operation_uuid"].unique()
                       if u != IDLE_VALUE)

    out_path.mkdir(parents=True, exist_ok=True)
    manifest_rows: List[Dict] = []

    grouped = combined.groupby(["program", "operation_uuid"], sort=True)
    for (program, uuid), group in grouped:
        if uuid == IDLE_VALUE:
            label = "idle"
        else:
            label = operation_label(uuid, name_map)

        group = group.copy()
        group["operation"] = label
        group = group.sort_values(["source_file", "sample_index"])
        group = order_columns(group)

        prog_dir = out_path / slugify(program)
        prog_dir.mkdir(parents=True, exist_ok=True)
        out_file = prog_dir / f"{slugify(label)}.csv"
        group.to_csv(out_file, index=False)

        manifest_rows.append({
            "program": program,
            "operation": label,
            "operation_uuid": uuid,
            "rows": len(group),
            "runs": group["run"].nunique(),
            "segments": group["segment_id"].nunique(),
            "source_files": group["source_file"].nunique(),
            "output": str(out_file.relative_to(out_path)),
        })

    # Manifest.
    manifest = pd.DataFrame(manifest_rows).sort_values(["program", "operation"])
    manifest_file = out_path / "manifest.csv"
    manifest.to_csv(manifest_file, index=False)

    # Discovered operations: merge known names, placeholder = UUID for unknowns.
    discovered = {u: name_map.get(u, u) for u in all_uuids}
    disc_file = out_path / "discovered_operations.json"
    with disc_file.open("w") as f:
        json.dump(discovered, f, indent=2)

    # Summary.
    unnamed = [u for u in all_uuids if u not in name_map]
    print(f"\nWrote {len(manifest_rows)} CSV(s) to {out_path}/")
    print(f"  programs:   {manifest['program'].nunique()}")
    print(f"  operations: {len(all_uuids)} unique"
          + (f" ({len(unnamed)} unnamed)" if unnamed else ""))
    print(f"  pivot:      {', '.join(f'{k}={v}' for k, v in methods_used.items())}")
    print(f"  manifest:   {manifest_file}")
    if unmatched:
        print(f"  warning: {len(unmatched)} file(s) did not match the filename pattern "
              f"and became their own program. Set --part-types if needed. "
              f"First few: {unmatched[:3]}")
    if unnamed:
        print(f"  note: {len(unnamed)} operation(s) have no readable name. Fill in "
              f"{disc_file.name} and re-run with --names for nicer filenames.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Split long-format CNC CSVs into per (program, operation) wide "
                    "CSVs for ML.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--input", default=DEFAULT_INPUT_DIR,
                   help="Directory containing the source CSVs.")
    p.add_argument("--output", default=DEFAULT_OUTPUT_DIR,
                   help="Directory to write per-operation CSVs into.")
    p.add_argument("--pattern", default=DEFAULT_PATTERN,
                   help="Glob for selecting source files.")
    p.add_argument("--names", default=None,
                   help="JSON mapping processKindId UUID -> readable operation name.")
    p.add_argument("--keep-idle", action="store_true",
                   help="Keep idle rows (processKindId == NONE) as an 'idle' operation.")
    p.add_argument("--part-types", default=DEFAULT_PART_TYPES,
                   help="Comma-separated part keywords for filename parsing (e.g. body,lid).")
    p.add_argument("--pivot", default="auto", choices=["auto", "time", "blocks"],
                   help="Sample detection: time (fast), blocks (robust), or auto.")
    p.add_argument("--dry-run", action="store_true",
                   help="Inspect files and report schema/operations without writing.")
    return p


def main() -> int:
    args = build_parser().parse_args()
    return process(
        input_dir=args.input,
        output_dir=args.output,
        pattern=args.pattern,
        names_path=args.names,
        keep_idle=args.keep_idle,
        part_types=args.part_types,
        pivot_method=args.pivot,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
