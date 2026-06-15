"""
Run all EXPLORATORY projects in order.

Usage (from repo root):
    python EXPLORATORY/run_all.py

What this does:
  1. Runs the adapter gate test first. If the gate fails (CNC_DATA_DIR not set),
     all data-dependent projects will park themselves automatically.
  2. Runs each project's run.py in order, catching failures.
  3. Prints a status line per project: ok / parked / smoke-failed / error.
  4. Never stops on a parked or failed project; always continues.

Status codes:
  ok           -- run.py exited 0 with no failures
  parked       -- DataNotInRepo caught; project logged to _data_gaps.md
  smoke-failed -- smoke test failed; check the output for the specific assertion
  error        -- run.py crashed with an unexpected exception

Read _data_gaps.md after running to see what data you need to supply.
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPLORATORY = Path(__file__).parent

PROJECTS = [
    "estimation_ladder",   # Tier A -- build first
    "allocation",          # Tier A -- build second
    "wear_runorder",       # build only if the above are done
]


def run_gate() -> bool:
    """Run the adapter gate test. Returns True if the gate passed."""
    print("=" * 60)
    print("STEP 0: ADAPTER GATE TEST")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, str(EXPLORATORY / "shared" / "test_adapters.py")],
        capture_output=False,
    )
    passed = result.returncode == 0
    print()
    return passed


def run_project(name: str) -> str:
    """Run one project's run.py. Returns status string."""
    script = EXPLORATORY / name / "run.py"
    if not script.exists():
        return "missing"

    print(f"  Running {name}/ ...", end=" ", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            last_line = stdout.split("\n")[-1] if stdout else ""
            if "PARKED" in stdout:
                print("parked")
                return "parked"
            print("ok")
            return "ok"
        else:
            if "PARKED" in stdout:
                print("parked")
                return "parked"
            if "SMOKE TEST FAILED" in stdout or "SMOKE TEST FAILED" in stderr:
                print("smoke-failed")
                print(f"    {stdout or stderr}")
                return "smoke-failed"
            print("error")
            print(f"    stdout: {stdout[-500:] if stdout else '(none)'}")
            print(f"    stderr: {stderr[-500:] if stderr else '(none)'}")
            return "error"
    except subprocess.TimeoutExpired:
        print("timeout (>300s)")
        return "timeout"
    except Exception as e:
        print(f"error ({e})")
        return "error"


def main() -> None:
    print()
    print("=" * 60)
    print("EXPLORATORY run_all.py")
    print("=" * 60)
    print()

    gate_passed = run_gate()

    print("=" * 60)
    print("PROJECTS")
    print("=" * 60)
    statuses: dict[str, str] = {}
    for name in PROJECTS:
        statuses[name] = run_project(name)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, status in statuses.items():
        symbol = {"ok": "[OK]", "parked": "[--]", "smoke-failed": "[!!]",
                  "error": "[XX]", "timeout": "[TO]", "missing": "[??]"}.get(status, "[??]")
        print(f"  {symbol}  {name:25s}  {status}")

    print()
    if any(s == "parked" for s in statuses.values()):
        print("Some projects are parked. See EXPLORATORY/_data_gaps.md for details.")
        print("Set CNC_DATA_DIR (and AM_DATA_DIR if needed) and re-run.")
    if all(s in ("ok", "parked") for s in statuses.values()):
        print("All non-parked projects completed without errors.")
    else:
        print("Some projects had failures. Check the output above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
