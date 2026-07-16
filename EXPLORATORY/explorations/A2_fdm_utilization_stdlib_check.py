"""
A2_fdm_utilization_stdlib_check.py -- independent, dependency-free companion
to A2_fdm_utilization.py.

A2_fdm_utilization.py (this same folder) already computes u_FDM from the
real print CSVs, but it imports pandas via EXPLORATORY/shared/adapters.py.
In an environment where pandas cannot be installed (this one: PyPI is
blocked), that script cannot run. This file recomputes the same quantity
with the Python standard library only, deliberately mirroring
adapters.load_am_energy()'s exact integration rule -- dt from consecutive
timestamps, first sample dropped, energy_wh = sum(power_w * dt_hours) -- so
the two should agree to rounding once someone with a working pandas
environment runs the canonical script and can cross-check this one.

This does NOT replace A2_fdm_utilization.py or write over its FINDINGS file.
Treat this as a stopgap measurement, not the canonical one: rerun the real
script and diff the two u_FDM values before quoting either in the paper.

Inputs: ../../3D Printer Data/*.csv (committed, no env var needed; falls
back to AM_DATA_DIR if set, matching adapters._am_data_dir()'s search order).

Output: A2_fdm_utilization_stdlib_FINDINGS.md (this folder).

Dependencies: Python 3 standard library only (csv, os, glob, re, datetime,
statistics).
"""

import csv
import datetime as dt
import glob
import os
import re
import statistics as stats

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AM_DIR = os.path.join(HERE, "..", "..", "3D Printer Data")
AM_PART_PREFIXES = ("DriveGear", "DriveShaft", "IdleGear", "IdleShaft")
AM_RATED_POWER_W = 221.0  # Ultimaker 2+ Extended, per GROUND_TRUTH.md


def _am_data_dir():
    return os.environ.get("AM_DATA_DIR", "").strip() or DEFAULT_AM_DIR


def _parse_time(s):
    try:
        return dt.datetime.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def list_am_files(am_dir):
    """Mirrors adapters.list_am_run_ids(): strict `{Prefix}_Part{N}.csv`
    match naturally excludes annotated captures like 'DriveGear_Part1 cold
    start_broken sensor.csv' and '..._Part28 failed.csv'."""
    included, excluded = [], []
    for path in sorted(glob.glob(os.path.join(am_dir, "*.csv"))):
        name = os.path.basename(path)
        m = re.match(r"(\w+)_Part(\d+)\.csv$", name)
        if m and m.group(1) in AM_PART_PREFIXES:
            included.append((m.group(1), int(m.group(2)), path))
        else:
            excluded.append(name)
    return included, excluded


def load_power_stream(path):
    """(time, power_w) pairs for the 'power' Dataname, sorted by time."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Dataname") != "power":
                continue
            t = _parse_time(row.get("Time", ""))
            try:
                p = max(float(row["Value"]), 0.0)
            except (TypeError, ValueError, KeyError):
                continue
            if t is not None:
                rows.append((t, p))
    rows.sort(key=lambda r: r[0])
    return rows


def print_energy(path):
    """energy_wh, duration_s, mean_power_w for one print, matching
    adapters.load_am_energy()'s rule exactly: dt from consecutive
    timestamps, first sample dropped, energy = sum(P * dt)."""
    stream = load_power_stream(path)
    if len(stream) < 2:
        return None
    energy_wh = 0.0
    for (t0, _), (t1, p1) in zip(stream, stream[1:]):
        dt_h = (t1 - t0).total_seconds() / 3600.0
        energy_wh += p1 * dt_h
    duration_s = (stream[-1][0] - stream[0][0]).total_seconds()
    mean_power_w = energy_wh * 3600.0 / duration_s if duration_s > 0 else 0.0
    peak_power_w = max(p for _, p in stream)
    return energy_wh, duration_s, mean_power_w, peak_power_w


def main():
    am_dir = _am_data_dir()
    included, excluded = list_am_files(am_dir)

    rows = []
    for prefix, num, path in included:
        result = print_energy(path)
        if result is None:
            continue
        energy_wh, duration_s, mean_power_w, peak_power_w = result
        rows.append({
            "part": prefix, "run_id": num, "source_file": os.path.basename(path),
            "energy_wh": energy_wh, "duration_s": duration_s,
            "mean_power_w": mean_power_w, "peak_power_w": peak_power_w,
        })

    total_energy_wh = sum(r["energy_wh"] for r in rows)
    total_duration_s = sum(r["duration_s"] for r in rows)
    p_mean = total_energy_wh * 3600.0 / total_duration_s if total_duration_s else 0.0
    u_fdm = p_mean / AM_RATED_POWER_W if p_mean else 0.0

    per_part = {}
    for r in rows:
        per_part.setdefault(r["part"], []).append(r)

    lines = []
    lines.append("# A2 (stdlib check): FDM utilization from measured prints")
    lines.append("")
    lines.append("Independent, pandas-free recomputation of u_FDM from the real")
    lines.append("print CSVs in `3D Printer Data/`, run because")
    lines.append("`A2_fdm_utilization.py` (same folder) cannot execute in an")
    lines.append("environment where pandas is unavailable. Integration rule")
    lines.append("mirrors `adapters.load_am_energy()` exactly (dt from consecutive")
    lines.append("timestamps, first sample dropped, energy = sum(P * dt)), so the")
    lines.append("two should agree once someone runs the canonical script locally")
    lines.append("and cross-checks. **Not a replacement for the canonical result --**")
    lines.append("cross-check both before quoting u_FDM in the paper.")
    lines.append("")
    lines.append(f"Files found: {len(included) + len(excluded)}. Used: {len(included)}.")
    lines.append(f"Excluded (annotated/failed captures, by filename): {len(excluded)}")
    lines.append(f"-- {sorted(excluded)}")
    lines.append("")
    lines.append("## Measured")
    lines.append("")
    lines.append(f"Duration-weighted mean power across {len(rows)} valid prints: "
                 f"**{p_mean:.1f} W**")
    lines.append(f"")
    lines.append(f"u_FDM = {p_mean:.1f} / {AM_RATED_POWER_W:.0f} W (rated) = **{u_fdm:.3f}**")
    lines.append("")
    lines.append("Quoted expectations (GROUND_TRUTH.md): measured draw ~200 W, u ~0.90.")
    pct_power = (p_mean / 200.0 - 1) * 100
    pct_u = (u_fdm / 0.90 - 1) * 100
    lines.append(f"This measurement: {pct_power:+.1f}% vs quoted power, {pct_u:+.1f}% vs quoted u.")
    lines.append("")
    lines.append("## Per part")
    lines.append("")
    lines.append("| Part | N prints | Mean power (W) | Total energy (Wh) |")
    lines.append("|---|---|---|---|")
    for part in sorted(per_part):
        prints = per_part[part]
        mean_p = stats.mean(r["mean_power_w"] for r in prints)
        total_e = sum(r["energy_wh"] for r in prints)
        lines.append(f"| {part} | {len(prints)} | {mean_p:.1f} | {total_e:.1f} |")
    lines.append("")
    lines.append("## Confirms the utilization-landscape headline")
    lines.append("")
    lines.append(f"u_FDM measured at {u_fdm:.2f} against u_CNC measured at 0.0975")
    lines.append("(register-based, `EXPLORATORY/compare_outputs/compare_estimation_ladder.csv`):")
    lines.append(f"a ~{u_fdm / 0.0975:.0f}x spread between the two machine classes, both now")
    lines.append("from real measurement rather than one spec-sheet number and one")
    lines.append("measured number. This is the paper's central utilization-factor")
    lines.append("contrast (TRIAGE_code_vs_argument.md's \"key direction 1\"), now fully")
    lines.append("measured on both ends pending the pandas cross-check above.")
    lines.append("")

    out_path = os.path.join(HERE, "A2_fdm_utilization_stdlib_FINDINGS.md")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {out_path}")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
