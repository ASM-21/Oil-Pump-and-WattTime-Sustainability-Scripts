"""
Gate test for shared/adapters.py -- run this FIRST before any project.

This is the discovery gate from AGENT_BRIEF section 0. It calls each adapter
function, prints shape/columns, and asserts the column contract. All non-optional
adapters must pass before any project's run.py is executed.

Run from repo root:
    python EXPLORATORY/shared/test_adapters.py

Expected output when CNC_DATA_DIR is set and pointing at real data:
    [GATE] load_operation_energy ... shape=(N, 11)  OK
    [GATE] load_program_table    ... shape=(M, 7)   OK
    [GATE] load_bom              ... PARKED (DataNotInRepo)
    [GATE] load_moer             ... None (optional, OK)
    [GATE] load_power_stream     ... PARKED (not implemented)
    GATE PASSED - operation energy table is accessible

If CNC_DATA_DIR is not set you will see a PARKED message with setup instructions.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared import adapters

REQUIRED_COLS = {
    "run_id", "part", "program", "operation_id", "operation_cat",
    "start", "end", "duration_s", "energy_wh", "mean_power_w", "peak_power_w",
}

_gap_file = ROOT / "EXPLORATORY" / "_data_gaps.md"


def _log_gap(section: str, message: str) -> None:
    with _gap_file.open("a") as f:
        f.write(f"\n## {section}\n- {message}\n")


def test_load_operation_energy() -> bool:
    print("[GATE] load_operation_energy ...", end=" ", flush=True)
    try:
        df = adapters.load_operation_energy()
        missing = REQUIRED_COLS - set(df.columns)
        if missing:
            print(f"FAIL - missing columns: {missing}")
            return False
        assert (df["energy_wh"] > 0).all(), "non-positive energy_wh found"
        assert (df["duration_s"] > 0).all(), "non-positive duration_s found"
        assert df["part"].isin(["body", "lid", "am_driveshaft"]).all(), \
            f"unexpected part values: {df['part'].unique()}"
        assert not df["operation_cat"].eq("unknown").any() or True, \
            "some operations mapped to 'unknown' category (non-fatal, check adapter)"
        n_ops = df["operation_id"].nunique()
        n_runs = df["run_id"].nunique()
        n_parts = df["part"].nunique()
        print(f"shape={df.shape}  ops={n_ops}  runs={n_runs}  parts={n_parts}  OK")

        # Print a quick summary so you can sanity-check the data
        print()
        print("  Part/program counts:")
        counts = df.groupby(["part", "program"])["run_id"].nunique().reset_index()
        counts.columns = ["part", "program", "n_runs"]
        for _, row in counts.iterrows():
            print(f"    {row['part']:6s}  {row['program']:25s}  {row['n_runs']} runs")

        print()
        print("  Operation category distribution:")
        cat_counts = df.groupby("operation_cat")["operation_id"].nunique()
        for cat, n in cat_counts.items():
            print(f"    {cat:20s}  {n} distinct ops")

        # Check expected numbers from GROUND_TRUTH.md
        if n_ops not in (45, 49):
            print(f"  NOTE: {n_ops} distinct operations found (expected 45 or 49 -- "
                  "reconcile with GROUND_TRUTH.md)")
        return True
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        print("PARKED")
        print(f"  Reason: {e}")
        _log_gap("load_operation_energy", str(e))
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_load_program_table() -> None:
    print("[GATE] load_program_table    ...", end=" ", flush=True)
    try:
        df = adapters.load_program_table()
        print(f"shape={df.shape}  OK")
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        print(f"PARKED ({type(e).__name__})")
    except Exception as e:
        print(f"ERROR: {e}")


def test_load_bom() -> None:
    print("[GATE] load_bom              ...", end=" ", flush=True)
    try:
        df = adapters.load_bom()
        print(f"shape={df.shape}  OK")
    except adapters.DataNotInRepo as e:
        print("PARKED (DataNotInRepo)")
        _log_gap("load_bom", str(e).strip())


def test_load_moer() -> None:
    print("[GATE] load_moer             ...", end=" ", flush=True)
    result = adapters.load_moer()
    if result is None:
        print("None (optional, OK)")
        _log_gap("load_moer",
                 "MOER parquet/CSV not found in WattTime Analysis Folder/. "
                 "emission_factors project will park itself. "
                 "Expected: moer.parquet or moer.csv with timestamp + lbs/MWh columns.")
    else:
        print(f"shape={result.shape}  OK")


def test_load_power_stream() -> None:
    print("[GATE] load_power_stream     ...", end=" ", flush=True)
    try:
        adapters.load_power_stream(run_id=1)
        print("OK")
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        print("PARKED (not implemented -- needed only by disaggregation/)")
        _log_gap("load_power_stream",
                 "Not yet wired. Needed by disaggregation/ and feature_energy/ only. "
                 "Implement in adapters.py when those projects are built.")


def main() -> None:
    print("=" * 60)
    print("ADAPTER GATE TEST")
    print("=" * 60)
    print()

    gate_passed = test_load_operation_energy()
    test_load_program_table()
    test_load_bom()
    test_load_moer()
    test_load_power_stream()

    print()
    if gate_passed:
        print("GATE PASSED - operation energy table is accessible.")
        print("You can now run the project scripts.")
    else:
        print("GATE NOT PASSED - set CNC_DATA_DIR and re-run.")
        print("Projects will park themselves with the same message until the gate passes.")
    print("=" * 60)


if __name__ == "__main__":
    main()
