"""
Fixture smoke of EVERY EXPLORATORY project, no measurement data required.

This is the full-matrix proof that all nine projects, including the Tier-A
flagships (estimation_ladder, allocation, wear_runorder), run end to end
BEFORE the real Al6061 CSVs are available:

  1. Generates a synthetic fixture campaign (shared/fixtures.py; exact real
     CSV format, 6 runs so Shapiro-Wilk and run-order tests have enough
     replicates, no injected drift).
  2. Points CNC_DATA_DIR at it and sets FIXTURE_SMOKE=1, which tells the
     Tier-A smoke tests to downgrade quoted-number disagreements (1,376 W,
     0.677 ratio, 11.7% homing are properties of the MEASURED campaign that
     synthetic data cannot reproduce) to warnings. Structural invariants
     stay fatal.
  3. Runs the adapter gate and each project's run.py as a subprocess and
     prints a status matrix. Exit code is nonzero if anything genuinely
     failed.

Run from the repo root (needs pandas/numpy/matplotlib; scipy/statsmodels
enable the two projects that use them, otherwise those are SKIPped):

    python EXPLORATORY/smoke_fixture_all.py

This does NOT replace running on real data; it proves the code paths so the
first real run is about the numbers, not the plumbing.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORATORY = Path(__file__).parent

# (project, required optional deps)
PROJECTS: list[tuple[str, tuple[str, ...]]] = [
    ("theory/estimator_errors", ()),
    ("theory/allocation_theory", ()),
    ("theory/power_decomposition", ()),
    ("signature_mining", ()),
    ("energy_budget", ()),
    ("uncertainty_prediction", ()),
    ("estimation_ladder", ("scipy",)),
    ("allocation", ()),
    ("wear_runorder", ("scipy", "statsmodels")),
]


def _missing_deps(deps: tuple[str, ...]) -> list[str]:
    return [d for d in deps if importlib.util.find_spec(d) is None]


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from EXPLORATORY.shared import fixtures

    statuses: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="fixture_cnc_") as tmp:
        truth = fixtures.generate_fixture_dataset(tmp, n_runs=6, seed=7)
        print(f"Fixture campaign: {len(truth)} truth operations in {tmp}")

        env = os.environ.copy()
        env["CNC_DATA_DIR"] = tmp
        env["FIXTURE_SMOKE"] = "1"

        print()
        print("=" * 64)
        print("GATE: shared/test_adapters.py on fixtures")
        print("=" * 64)
        gate = subprocess.run(
            [sys.executable, str(EXPLORATORY / "shared" / "test_adapters.py")],
            env=env, timeout=300,
        )
        statuses["shared/test_adapters (gate)"] = "OK" if gate.returncode == 0 else "FAIL"

        for name, deps in PROJECTS:
            missing = _missing_deps(deps)
            if missing:
                print(f"\n[{name}] SKIP -- missing optional deps: {missing}")
                statuses[name] = f"SKIP (pip install {' '.join(missing)})"
                continue
            script = EXPLORATORY / name / "run.py"
            print()
            print("=" * 64)
            print(f"PROJECT: {name} (fixture data)")
            print("=" * 64)
            try:
                res = subprocess.run(
                    [sys.executable, str(script)], env=env, timeout=600,
                )
                statuses[name] = "OK" if res.returncode == 0 else "FAIL"
            except subprocess.TimeoutExpired:
                statuses[name] = "TIMEOUT"

    print()
    print("=" * 64)
    print("FIXTURE SMOKE MATRIX")
    print("=" * 64)
    width = max(len(k) for k in statuses)
    for name, status in statuses.items():
        print(f"  {name:<{width}}  {status}")
    failed = [k for k, v in statuses.items() if v in ("FAIL", "TIMEOUT")]
    print()
    if failed:
        print(f"{len(failed)} project(s) FAILED on fixtures: {failed}")
        print("These are real code defects, not data gaps -- fix before the real run.")
        return 1
    print("ALL PROJECTS RUN CLEAN ON FIXTURES.")
    print("Next: set CNC_DATA_DIR to the real Al6061 folder and run "
          "EXPLORATORY/run_all.py for the measured numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
