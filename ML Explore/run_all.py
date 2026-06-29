#!/usr/bin/env python3
"""
run_all.py
==========

Run the whole toolkit end to end with one command: prep the CSV folder (optional),
run every analysis, then build the HTML report. Each step is a normal script call, so
anything you can do by hand you can do here.

Examples
--------
  # From raw long-format files: split, analyze everything, report
  python run_all.py --data ./data --names operation_names.json

  # From an existing operation_csvs folder
  python run_all.py --input ./operation_csvs

  # Skip the slow ones
  python run_all.py --input ./operation_csvs --skip sensor_study,scheduling

Notes
-----
- Analyses run against the CSV folder and write into <output-root>/<name>.
- A failing step is reported and skipped; the rest still run.
- Pass material carbon to the footprint step with --material-carbon.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import List

HERE = Path(__file__).resolve().parent

# name -> (script, [extra args])
ANALYSES = [
    ("quality", "quality_check.py", []),
    ("classify", "classify_operations.py", []),
    ("energy", "estimate_energy.py", []),
    ("variability", "variability_analysis.py", []),
    ("energy_breakdown", "energy_breakdown.py", []),
    ("sensor_study", "sensor_study.py", []),
    ("scheduling", "carbon_scheduling.py", []),
    ("timeseries", "time_series_analysis.py", []),
    ("wear", "wear_analysis.py", []),
    ("clustering", "cluster_operations.py", []),
    ("carbon", "carbon_footprint.py", []),
]


def run(cmd: List[str]) -> bool:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    t0 = time.time()
    res = subprocess.run(cmd)
    dt = time.time() - t0
    ok = res.returncode == 0
    print(f"  [{'ok' if ok else 'FAILED'} in {dt:.1f}s]")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the full operation-analysis pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--data", default=None,
                    help="Raw long-format CSV folder. If given, runs split_operations first.")
    ap.add_argument("--input", default="operation_csvs",
                    help="Per-operation CSV folder (created here if --data is given).")
    ap.add_argument("--output-root", default="ml", help="Where each step writes its outputs.")
    ap.add_argument("--names", default=None, help="processKindId -> name JSON (for split).")
    ap.add_argument("--keep-idle", action="store_true", help="Pass --keep-idle to split.")
    ap.add_argument("--material-carbon", type=float, default=None,
                    help="Material carbon per part (kg) for the footprint step.")
    ap.add_argument("--min-samples", type=int, default=0,
                    help="Pass --min-samples to the modeling steps.")
    ap.add_argument("--skip", default="", help="Comma-separated step names to skip.")
    ap.add_argument("--report-only", action="store_true",
                    help="Just rebuild the report from existing outputs.")
    args = ap.parse_args()

    py = sys.executable
    root = Path(args.output_root)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    results = {}

    if args.report_only:
        run([py, str(HERE / "generate_report.py"), "--input", str(root),
             "--output", str(root / "report.html")])
        return 0

    # 1. prep
    csv_dir = args.input
    if args.data:
        cmd = [py, str(HERE / "split_operations.py"), "--input", args.data,
               "--output", csv_dir]
        if args.names:
            cmd += ["--names", args.names]
        if args.keep_idle:
            cmd += ["--keep-idle"]
        if not run(cmd):
            print("\nsplit_operations failed; cannot continue.")
            return 1

    if not Path(csv_dir).exists():
        print(f"\nCSV folder {csv_dir} not found. Provide --data to build it.")
        return 1

    # 2. analyses
    for name, script, extra in ANALYSES:
        if name in skip:
            print(f"\n(skipping {name})")
            continue
        cmd = [py, str(HERE / script), "--input", csv_dir,
               "--output", str(root / name)] + extra
        if args.min_samples and name in {"classify", "energy"}:
            cmd += ["--min-samples", str(args.min_samples)]
        if name == "carbon" and args.material_carbon is not None:
            cmd += ["--material-carbon", str(args.material_carbon)]
        results[name] = run(cmd)

    # 3. report
    run([py, str(HERE / "generate_report.py"), "--input", str(root),
         "--output", str(root / "report.html")])

    # summary
    ran = [n for n, ok in results.items() if ok]
    failed = [n for n, ok in results.items() if not ok]
    print("\n" + "=" * 50)
    print(f"Pipeline done. {len(ran)} ok, {len(failed)} failed, "
          f"{len(skip)} skipped.")
    if failed:
        print(f"  failed: {failed}")
    print(f"Report: {root / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
