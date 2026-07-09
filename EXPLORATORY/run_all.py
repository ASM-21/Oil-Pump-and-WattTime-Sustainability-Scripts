"""
Run all EXPLORATORY projects in order.

Press Run / run directly:
    python EXPLORATORY/run_all.py

What this does:
  1. Asks for your CNC data folder path on first run (saves it so you won't be asked again).
  2. Runs the adapter gate test.
  3. Runs each project's run.py in order, printing output live as it goes.
  4. Never stops on a parked or failed project -- always continues to the next.
  5. Prints a one-line status summary per project at the end.

Status codes in the summary:
  [OK]  -- run.py exited 0
  [--]  -- parked (data not available; check _data_gaps.md)
  [!!]  -- smoke test failed
  [XX]  -- unexpected error
"""

from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORATORY = Path(__file__).parent

PROJECTS = [
    # Never park: theory closed forms validated on fixtures through the
    # real pipeline; real data only adds empirical confirmation rows.
    "theory/estimator_errors",
    "theory/allocation_theory",
    "theory/power_decomposition",
    # Always produce a fixture-verified result set; add 'measured' tables
    # when CNC_DATA_DIR points at the real Al6061 folder.
    "signature_mining",
    "energy_budget",
    "uncertainty_prediction",
    # Park without real data (fixture mode not applicable: their claims are
    # about the measured campaign itself).
    "estimation_ladder",   # Tier A -- build first
    "allocation",          # Tier A -- build second
    "wear_runorder",       # build after the above two
]


def _ensure_data_path() -> dict[str, str]:
    """
    Resolve CNC_DATA_DIR once here so all subprocesses inherit it.
    Uses the adapter's saved-config logic so the user only types the path once.
    Returns a copy of os.environ with CNC_DATA_DIR set.
    """
    sys.path.insert(0, str(ROOT))
    from EXPLORATORY.shared.adapters import _resolve_data_dir, DataNotInRepo  # noqa

    env = os.environ.copy()
    if not env.get("CNC_DATA_DIR"):
        try:
            path = _resolve_data_dir(
                "CNC_DATA_DIR",
                "Folder containing your Al6061_body*.csv and Al6061_lid*.csv files from IN-MaC CNC runs.",
            )
            env["CNC_DATA_DIR"] = path
        except DataNotInRepo as e:
            print(f"Cannot resolve CNC data path: {e}")
            print("Projects that need CNC data will park themselves.")
    return env


def run_gate(env: dict) -> None:
    print("=" * 60)
    print("STEP 0: ADAPTER GATE TEST")
    print("=" * 60)
    subprocess.run(
        [sys.executable, str(EXPLORATORY / "shared" / "test_adapters.py")],
        env=env,
    )
    print()


def run_project(name: str, env: dict) -> str:
    """Run one project's run.py, streaming output live. Returns status string."""
    script = EXPLORATORY / name / "run.py"
    if not script.exists():
        print(f"  [{name}] MISSING -- {script} not found")
        return "missing"

    print()
    print("=" * 60)
    print(f"PROJECT: {name}")
    print("=" * 60)

    # Stream output live (no capture) -- user sees progress in real time
    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        timeout=300,
    )

    if result.returncode == 0:
        return "ok"
    else:
        return "error"


def main() -> None:
    print()
    print("=" * 60)
    print("EXPLORATORY run_all")
    print("=" * 60)
    print()

    # Resolve data path once so subprocesses inherit it
    env = _ensure_data_path()

    # Gate test
    run_gate(env)

    # Projects
    statuses: dict[str, str] = {}
    for name in PROJECTS:
        try:
            statuses[name] = run_project(name, env)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT (>300s)")
            statuses[name] = "timeout"
        except Exception as e:
            print(f"  ERROR: {e}")
            statuses[name] = "error"

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    symbol_map = {"ok": "[OK]", "parked": "[--]", "error": "[XX]",
                  "timeout": "[TO]", "missing": "[??]"}
    for name, status in statuses.items():
        # Infer parked from exit code vs PARKED text -- subprocess was not captured
        # so we use exit code 0 = ok, non-zero = something went wrong
        symbol = symbol_map.get(status, "[??]")
        print(f"  {symbol}  {name}")

    print()
    print("Outputs land in EXPLORATORY/<project>/outputs/")
    print("Findings in   EXPLORATORY/<project>/FINDINGS.md")
    print("Data gaps in  EXPLORATORY/_data_gaps.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
