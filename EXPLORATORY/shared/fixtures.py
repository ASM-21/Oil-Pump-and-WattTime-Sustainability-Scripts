"""
Synthetic 1 Hz power-stream fixture generator.

WHY THIS EXISTS
The raw Al6061 measurement CSVs are not committed to this repo, so nothing
downstream can be exercised end to end without the owner's local data. This
module generates synthetic CSVs in the EXACT on-disk format the real meter
produced (interleaved Time,Dataname,Value rows carrying processKindId,
partKindId, and active power at 1 Hz, filenames Al6061_{body|lid}{N}_p{M}.csv,
the real production UUIDs), together with an exact ground-truth energy table
computed with the same trapezoid-and-gap rule EnergyForFeatureLib uses.

Because the format is exact, a fixture folder is a drop-in stand-in for
CNC_DATA_DIR: point the adapter at it and the ENTIRE existing pipeline
(EnergyAnalyzer -> clean_data -> adapters contract) runs unmodified. Every
EXPLORATORY project can therefore verify itself end to end before the real
data is available, against known-truth energies rather than eyeballed output.

DESIGN NOTES
- Stdlib only (csv, random, datetime, re). It must run in environments where
  the scientific stack is unavailable, and it must not import the pandas-based
  modules it exists to test.
- The two UUID maps are parsed from EnergyForFeatureLib.py source with a
  regex rather than duplicated here, so fixtures can never drift out of sync
  with the production decoding tables.
- Run-to-run variability is structured by operation category to mirror the
  paper's finding (finishing low CV, spotting/tapping high CV), and an
  optional per-run drift lets wear/run-order code be tested against a known
  injected trend.

USAGE
    from EXPLORATORY.shared.fixtures import generate_fixture_dataset
    truth = generate_fixture_dataset("/tmp/fixture_cnc", n_runs=3, seed=7)
    # then: os.environ["CNC_DATA_DIR"] = "/tmp/fixture_cnc" and run anything.

CLI (writes a fixture folder plus fixture_truth.csv):
    python EXPLORATORY/shared/fixtures.py /tmp/fixture_cnc 3
"""

from __future__ import annotations

import csv
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FEATURE_LIB_SRC = (
    _REPO_ROOT / "Machine Specific Scripts" / "CNC" / "EnergyForFeatureLib.py"
)

# The trapezoid integration in EnergyForFeatureLib drops sample pairs more than
# this many seconds apart. Ground truth must apply the same rule.
MAX_GAP_SEC = 3.0


# ---------------------------------------------------------------------------
# UUID maps, parsed from the production source so they cannot drift
# ---------------------------------------------------------------------------

def _parse_uuid_dict(source: str, dict_name: str) -> dict[str, str]:
    """Extract a {'UUID': 'NAME'} dict literal from EnergyForFeatureLib source."""
    block = re.search(
        rf"self\.{dict_name}\s*=\s*\{{(.*?)\}}", source, flags=re.DOTALL
    )
    if not block:
        raise RuntimeError(f"Could not locate {dict_name} in {_FEATURE_LIB_SRC}")
    pairs = re.findall(r"'([^']+)'\s*:\s*'([^']+)'", block.group(1))
    return dict(pairs)


def load_production_uuid_maps() -> tuple[dict[str, str], dict[str, str]]:
    """Return (partkind_to_program, uuid_to_operation) from the real script."""
    source = _FEATURE_LIB_SRC.read_text()
    return (
        _parse_uuid_dict(source, "partkind_to_program"),
        _parse_uuid_dict(source, "uuid_to_operation"),
    )


def _invert(d: dict[str, str]) -> dict[str, str]:
    return {v: k for k, v in d.items()}


# ---------------------------------------------------------------------------
# Fixture machine model
# ---------------------------------------------------------------------------

# Idle/base power of the fixture machine (W). Everything above this is process.
IDLE_POWER_W = 700.0

# Per-operation profile: (power_above_idle_W, duration_s, cv_across_runs).
# CV structure mirrors the paper: cavity/face/finishing tight, spotting/
# tapping/drilling loose. Values are plausible for a VMX30Ui-class machine but
# are NOT measurements; the point is known truth, not realism of magnitudes.
_OP_PROFILE: dict[str, tuple[float, int, float]] = {
    # PROGRAM_1_Body: roughing
    "FACE_DATUM_A":            (1100.0, 90,  0.03),
    "CAVITY_MILL_OUTSIDE":     (2800.0, 420, 0.04),
    "CAVITY_MILL_INSIDE":      (2500.0, 360, 0.04),
    "WALL_FLOOR_PROFILING":    (900.0,  150, 0.08),
    "FLOOR_FACING":            (1000.0, 120, 0.05),
    # PROGRAM_2_Body: finishing
    "FACE_TOP_PLANE":          (1000.0, 100, 0.03),
    "FINISH_OUTER_WALL":       (600.0,  200, 0.02),
    "FINISH_OUTER_PROFILE":    (550.0,  180, 0.02),
    "FINISH_INNER_PROFILE":    (520.0,  170, 0.02),
    "PLANAR_DEBURRING":        (400.0,  80,  0.10),
    # PROGRAM_3_Body: hole making
    "SPOTTING_LID_HOLES":      (250.0,  30,  0.20),
    "DRILLING_LID_HOLES":      (800.0,  120, 0.12),
    "TAPPING_LID_HOLES":       (450.0,  60,  0.22),
    "SPOTTING_CBORE":          (240.0,  25,  0.25),
    "DRILLING_CBORE":          (850.0,  90,  0.12),
    "FINISH_CBORE":            (500.0,  70,  0.03),
    # PROGRAM_4_Body: ports and marking
    "SPOTTING_NPT_TOP":        (230.0,  25,  0.25),
    "DRILLING_NPT_TOP":        (900.0,  100, 0.12),
    "TAPPING_NPT_TOP":         (480.0,  55,  0.20),
    "ENGRAVING":               (150.0,  45,  0.15),
    # PROGRAM_1_Lid: shaping
    "LID_FLOOR_FACING":        (950.0,  90,  0.04),
    "LID_CAVITY_MILL":         (2200.0, 300, 0.04),
    "LID_POCKETING":           (1800.0, 240, 0.05),
    "LID_FINISH_SURFACES":     (550.0,  160, 0.02),
    # PROGRAM_2_Lid: holes and edges
    "LID_SPOTTING_HOLES":      (240.0,  28,  0.22),
    "LID_DRILLING_HOLES":      (820.0,  110, 0.12),
    "LID_HOLE_MILLING":        (700.0,  130, 0.05),
    "LID_CHAMFER_EDGES":       (350.0,  60,  0.06),
    "LID_FINISH_FACE":         (520.0,  120, 0.02),
}

# Operation sequence per program. Any consistent assignment works because the
# truth table is generated, but the shape (roughing, finishing, hole-making)
# follows the real part flow described in the context docs.
PROGRAM_SEQUENCES: dict[str, list[str]] = {
    "PROGRAM_1_Body": ["FACE_DATUM_A", "CAVITY_MILL_OUTSIDE",
                       "CAVITY_MILL_INSIDE", "WALL_FLOOR_PROFILING",
                       "FLOOR_FACING"],
    "PROGRAM_2_Body": ["FACE_TOP_PLANE", "FINISH_OUTER_WALL",
                       "FINISH_OUTER_PROFILE", "FINISH_INNER_PROFILE",
                       "PLANAR_DEBURRING"],
    "PROGRAM_3_Body": ["SPOTTING_LID_HOLES", "DRILLING_LID_HOLES",
                       "TAPPING_LID_HOLES", "SPOTTING_CBORE",
                       "DRILLING_CBORE", "FINISH_CBORE"],
    "PROGRAM_4_Body": ["SPOTTING_NPT_TOP", "DRILLING_NPT_TOP",
                       "TAPPING_NPT_TOP", "ENGRAVING"],
    "PROGRAM_1_Lid":  ["LID_FLOOR_FACING", "LID_CAVITY_MILL",
                       "LID_POCKETING", "LID_FINISH_SURFACES"],
    "PROGRAM_2_Lid":  ["LID_SPOTTING_HOLES", "LID_DRILLING_HOLES",
                       "LID_HOLE_MILLING", "LID_CHAMFER_EDGES",
                       "LID_FINISH_FACE"],
}

# Seconds of in-program idle (processKindId = NONE) between operations, and
# seconds of out-of-program capture (partKindId = NONE) at file start/end.
# Idle spans must be at least as long as the changepoint detectors'
# min_seg_len (4 s at the call sites) or boundary-recovery scores on
# fixtures become flaky for reasons unrelated to the method.
INTER_OP_IDLE_S = (6, 10)
FILE_PAD_S = (6, 10)


def _trapezoid_energy_wh(powers: list[float]) -> tuple[float, float]:
    """Energy (Wh) and duration (s) of a contiguous 1 Hz sample block, using
    the same average-of-adjacent-samples rule as EnergyAnalyzer.calculate_energy
    (dt = 1 s always, so the gap rule never triggers within a block)."""
    if len(powers) < 2:
        return 0.0, 0.0
    energy = sum((powers[i] + powers[i + 1]) / 2.0 for i in range(len(powers) - 1))
    return energy / 3600.0, float(len(powers) - 1)


def generate_fixture_dataset(
    out_dir: str | Path,
    n_runs: int = 3,
    seed: int = 7,
    noise_sd_frac: float = 0.03,
    drift_pct_per_run: float = 0.0,
    start_time: str = "2025-03-03 09:00:00",
) -> list[dict]:
    """
    Write one CSV per (run, program) into out_dir and return the ground-truth
    table as a list of dicts with keys:
        file, part, run_id, program, operation, energy_wh, duration_s,
        mean_power_w, start_offset_s
    Also writes the same table to out_dir/fixture_truth.csv.

    n_runs applies to both body (4 programs) and lid (2 programs).
    drift_pct_per_run injects a known linear energy trend across run numbers
    (0.0 = exchangeable runs) so run-order tests can be validated both ways.
    Determinism: identical arguments always produce identical files.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    program_to_uuid = _invert(load_production_uuid_maps()[0])
    operation_to_uuid = _invert(load_production_uuid_maps()[1])
    none_program_uuid = program_to_uuid["NONE"]

    t0 = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    truth: list[dict] = []

    for program, ops in PROGRAM_SEQUENCES.items():
        part = "body" if program.endswith("Body") else "lid"
        prog_num = int(program.split("_")[1])
        prog_uuid = program_to_uuid[program]

        for run in range(1, n_runs + 1):
            # Per-run multiplier: structured CV plus optional injected drift.
            drift = 1.0 + drift_pct_per_run / 100.0 * (run - 1)
            fname = f"Al6061_{part}{run}_p{prog_num}.csv"
            rows: list[tuple[str, str, str]] = []  # (Time, Dataname, Value)
            t = t0 + timedelta(hours=(prog_num - 1) * 2 + (run - 1) * 8)

            def emit(seconds: int, power_fn, proc_uuid: str, part_uuid: str,
                     _t=[t]) -> list[float]:
                """Append `seconds` samples; returns the power values."""
                powers = []
                for _ in range(seconds):
                    p = max(0.0, power_fn())
                    stamp = _t[0].strftime("%Y-%m-%d %H:%M:%S")
                    rows.append((stamp, "processKindId", proc_uuid))
                    rows.append((stamp, "partKindId", part_uuid))
                    rows.append((stamp, "active power", f"{p:.1f}"))
                    powers.append(p)
                    _t[0] += timedelta(seconds=1)
                return powers

            def idle_power() -> float:
                return rng.gauss(IDLE_POWER_W, IDLE_POWER_W * 0.01)

            # Lead-in outside any program (analyzer skips program NONE).
            emit(rng.randint(*FILE_PAD_S), idle_power, "NONE", none_program_uuid)

            for op in ops:
                level, dur_s, cv = _OP_PROFILE[op]
                # One draw per (op, run): run-to-run CV, not sample noise.
                run_level = level * drift * max(0.1, rng.gauss(1.0, cv))
                op_uuid = operation_to_uuid[op]

                # In-program idle before the operation (maps to NONE_IDLE).
                emit(rng.randint(*INTER_OP_IDLE_S), idle_power, "NONE", prog_uuid)

                mean_p = IDLE_POWER_W + run_level
                offset_s = len(rows) // 3  # true sample offset incl. idle/pad
                powers = emit(
                    dur_s,
                    lambda: rng.gauss(mean_p, mean_p * noise_sd_frac),
                    op_uuid,
                    prog_uuid,
                )
                e_wh, d_s = _trapezoid_energy_wh(powers)
                truth.append({
                    "file": fname,
                    "part": part,
                    "run_id": run,
                    "program": program,
                    "operation": op,
                    "energy_wh": round(e_wh, 6),
                    "duration_s": d_s,
                    "mean_power_w": round(sum(powers) / len(powers), 3),
                    "start_offset_s": offset_s,
                })

            # Trailing in-program idle, then lead-out outside the program.
            emit(rng.randint(*INTER_OP_IDLE_S), idle_power, "NONE", prog_uuid)
            emit(rng.randint(*FILE_PAD_S), idle_power, "NONE", none_program_uuid)

            with (out / fname).open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "Dataname", "Value"])
                writer.writerows(rows)

    truth_path = out / "fixture_truth.csv"
    with truth_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(truth[0].keys()))
        writer.writeheader()
        writer.writerows(truth)

    return truth


# ---------------------------------------------------------------------------
# AM (FDM) fixtures
# ---------------------------------------------------------------------------
# Same long Time/Dataname/Value format, but the power metric is the literal
# 'power' (per the Additive scripts), there are no UUIDs, and each file is
# one print: {Prefix}_Part{N}.csv. Profile: heat-up ramp to a ~200 W plateau
# (bed+nozzle+steppers all working: the high-utilization contrast machine),
# brief cooldown tail. A 'temperature' metric is interleaved so loaders are
# proven to filter on Dataname.

AM_PLATEAU_W = 200.0
AM_RAMP_S = 60
AM_COOL_S = 30

_AM_PRINT_DURATION_S = {   # plateau seconds per part type (kept short; 1 Hz)
    "DriveGear": 600,
    "DriveShaft": 480,
    "IdleGear": 540,
    "IdleShaft": 420,
}


def generate_am_fixture_dataset(
    out_dir: str | Path,
    n_runs: int = 2,
    seed: int = 7,
    noise_sd_frac: float = 0.02,
    start_time: str = "2025-09-10 09:00:00",
) -> list[dict]:
    """
    Write one CSV per (part type, run) into out_dir; return the truth table
    (file, part, run_id, energy_wh, duration_s, mean_power_w).

    Truth energy uses the SAME integration the adapter applies (dt between
    consecutive samples, first sample dropped, sum P*dt), so the loader must
    reproduce it exactly, not approximately.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    t0 = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    truth: list[dict] = []

    for pi, (prefix, plateau_s) in enumerate(sorted(_AM_PRINT_DURATION_S.items())):
        for run in range(1, n_runs + 1):
            fname = f"{prefix}_Part{run}.csv"
            t = t0 + timedelta(hours=pi * 6 + (run - 1) * 24)
            powers: list[float] = []
            rows: list[tuple[str, str, str]] = []
            n_total = AM_RAMP_S + plateau_s + AM_COOL_S
            for i in range(n_total):
                if i < AM_RAMP_S:
                    base = AM_PLATEAU_W * i / AM_RAMP_S
                elif i < AM_RAMP_S + plateau_s:
                    base = AM_PLATEAU_W
                else:
                    base = AM_PLATEAU_W * 0.15
                p = max(0.0, rng.gauss(base, AM_PLATEAU_W * noise_sd_frac))
                stamp = t.strftime("%Y-%m-%d %H:%M:%S.%f")
                rows.append((stamp, "power", f"{p:.1f}"))
                rows.append((stamp, "temperature", f"{60 + base / 10:.1f}"))
                powers.append(p)
                t += timedelta(seconds=1)

            # Truth with the adapter's rule: drop first sample, dt = 1 s.
            energy_wh = sum(powers[1:]) / 3600.0
            duration_s = float(n_total - 1)
            truth.append({
                "file": fname,
                "part": prefix,
                "run_id": run,
                "energy_wh": round(energy_wh, 6),
                "duration_s": duration_s,
                "mean_power_w": round(energy_wh * 3600.0 / duration_s, 3),
            })
            with (out / fname).open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Time", "Dataname", "Value"])
                writer.writerows(rows)

    truth_path = out / "am_fixture_truth.csv"
    with truth_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(truth[0].keys()))
        writer.writeheader()
        writer.writerows(truth)
    return truth


def selftest() -> None:
    """Stdlib-only invariants; runs without pandas/numpy installed."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        truth = generate_fixture_dataset(tmp, n_runs=2, seed=11)
        files = sorted(Path(tmp).glob("Al6061_*.csv"))
        n_programs = len(PROGRAM_SEQUENCES)
        assert len(files) == n_programs * 2, f"expected {n_programs * 2} files, got {len(files)}"
        n_ops_expected = sum(len(v) for v in PROGRAM_SEQUENCES.values()) * 2
        assert len(truth) == n_ops_expected, (len(truth), n_ops_expected)
        assert all(r["energy_wh"] > 0 for r in truth), "non-positive truth energy"
        assert all(r["duration_s"] > 0 for r in truth), "non-positive truth duration"

        # Determinism: same seed, same bytes.
        with tempfile.TemporaryDirectory() as tmp2:
            generate_fixture_dataset(tmp2, n_runs=2, seed=11)
            a = (files[0]).read_text()
            b = (Path(tmp2) / files[0].name).read_text()
            assert a == b, "generator is not deterministic for a fixed seed"

        # Every third row of a file body is a power row; UUIDs decode.
        maps = load_production_uuid_maps()
        assert "PROGRAM_1_Body" in maps[0].values()
        assert "CAVITY_MILL_OUTSIDE" in maps[1].values()

        # start_offset_s must count ALL preceding samples (idle and pad too):
        # strictly increasing within each file, never starting at 0.
        by_file: dict[str, list[int]] = {}
        for r in truth:
            by_file.setdefault(r["file"], []).append(r["start_offset_s"])
        for fname, offsets in by_file.items():
            assert offsets == sorted(offsets), f"offsets not increasing in {fname}"
            assert offsets[0] >= FILE_PAD_S[0], f"first offset ignores pad in {fname}"

    # AM fixtures: determinism, truth positivity, plateau near 200 W.
    with tempfile.TemporaryDirectory() as tmp:
        am = generate_am_fixture_dataset(tmp, n_runs=2, seed=5)
        files = sorted(Path(tmp).glob("*_Part*.csv"))
        assert len(files) == len(_AM_PRINT_DURATION_S) * 2, len(files)
        assert all(r["energy_wh"] > 0 for r in am)
        for r in am:
            assert 0.5 * AM_PLATEAU_W < r["mean_power_w"] <= 1.05 * AM_PLATEAU_W, r
        with tempfile.TemporaryDirectory() as tmp2:
            generate_am_fixture_dataset(tmp2, n_runs=2, seed=5)
            a = files[0].read_text()
            b = (Path(tmp2) / files[0].name).read_text()
            assert a == b, "AM generator is not deterministic for a fixed seed"
    print("fixtures selftest OK")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        dest = sys.argv[1]
        runs = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        rows = generate_fixture_dataset(dest, n_runs=runs)
        print(f"Wrote {len(rows)} truth rows and CSVs to {dest}")
    else:
        selftest()
