"""
End-to-end tests for the shared analysis layer, driven by synthetic fixtures.

WHAT THIS PROVES
fixtures.py writes CSVs in the exact real on-disk format, so these tests run
the ENTIRE production path (EnergyForFeatureLib.EnergyAnalyzer -> clean_data
-> adapters contract -> new shared modules) against known-truth energies.
Passing here means the code is ready for the real data: point CNC_DATA_DIR at
the actual Al6061 folder and nothing changes but the numbers.

RUN (needs pandas/numpy/scipy; from the repo root):
    python EXPLORATORY/shared/test_shared.py
or via pytest:
    pytest EXPLORATORY/shared/test_shared.py -q

NOTE
The cloud session that authored this could not install the scientific stack
(network policy blocks PyPI), so this file is the FIRST thing to run locally.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from EXPLORATORY.shared import fixtures
from EXPLORATORY.shared import segmentation
from EXPLORATORY.shared import signatures
from EXPLORATORY.shared import montecarlo
from EXPLORATORY.shared.checks import require


def _fixture_env(tmp: str, n_runs: int = 3, **kw) -> pd.DataFrame:
    """Generate fixtures into tmp, point CNC_DATA_DIR at them, return truth."""
    truth_rows = fixtures.generate_fixture_dataset(tmp, n_runs=n_runs, **kw)
    os.environ["CNC_DATA_DIR"] = tmp
    return pd.DataFrame(truth_rows)


def test_pipeline_recovers_truth_energy():
    """adapters.load_operation_energy through the REAL analyzer matches truth."""
    from EXPLORATORY.shared import adapters

    with tempfile.TemporaryDirectory() as tmp:
        truth = _fixture_env(tmp)
        df = adapters.load_operation_energy()

        require(len(df) > 0, "pipeline returned no rows from fixtures")
        merged = truth.merge(
            df,
            left_on=["part", "run_id", "program", "operation"],
            right_on=["part", "run_id", "program", "operation_id"],
            how="left",
            suffixes=("_truth", "_pipe"),
        )
        require(merged["energy_wh_pipe"].notna().all(),
                "pipeline lost fixture operations:\n"
                + str(merged[merged["energy_wh_pipe"].isna()][["part", "run_id", "program", "operation"]]))
        rel = (merged["energy_wh_pipe"] - merged["energy_wh_truth"]).abs() \
            / merged["energy_wh_truth"]
        require(bool((rel < 0.005).all()),
                f"energy mismatch vs truth; worst rel err {rel.max():.4%}")
        # Category taxonomy must cover every fixture operation.
        require(not df["operation_cat"].eq("unknown").any(),
                "fixture operation missing from _OP_TO_CATEGORY")
    print("  pipeline recovers truth energy: OK "
          f"({len(merged)} operations, worst rel err {rel.max():.5%})")


def test_power_stream_loader():
    """load_power_stream returns 1 Hz samples whose sum matches truth energy."""
    from EXPLORATORY.shared import adapters

    with tempfile.TemporaryDirectory() as tmp:
        truth = _fixture_env(tmp)
        stream = adapters.load_power_stream(1, part="body")

        require(len(stream) > 0, "empty power stream")
        for src, sf in stream.groupby("source_file"):
            require(sf["t"].is_monotonic_increasing,
                    f"stream not time-sorted within {src}")
        require((stream["power_w"] >= 0).all(), "negative power in stream")

        # Rectangle-rule energy of one operation's samples should be within a
        # few percent of the trapezoid truth (they differ by half samples at
        # the segment edges only).
        row = truth[(truth["part"] == "body") & (truth["run_id"] == 1)
                    & (truth["operation"] == "CAVITY_MILL_OUTSIDE")].iloc[0]
        op = stream[stream["operation_id"] == "CAVITY_MILL_OUTSIDE"]
        e_rect = op["power_w"].sum() / 3600.0
        rel = abs(e_rect - row["energy_wh"]) / row["energy_wh"]
        require(rel < 0.02, f"stream energy off by {rel:.2%} vs truth")

        pairs = adapters.list_run_ids("body")
        require((("body", 1) in pairs), f"list_run_ids missing body run 1: {pairs}")
    print(f"  power stream loader: OK ({len(stream)} samples, rel err {rel:.4%})")


def test_segmentation_recovers_boundaries():
    """UUID-free changepoints recover the fixture's operation boundaries."""
    from EXPLORATORY.shared import adapters

    with tempfile.TemporaryDirectory() as tmp:
        _fixture_env(tmp)
        stream = adapters.load_power_stream(1, part="body")
        one_file = stream[stream["source_file"] == "Al6061_body1_p1.csv"]
        power = one_file["power_w"].to_numpy()

        # Reference boundaries: where the labeled operation changes.
        ops = one_file["operation_id"].to_numpy()
        ref = [i for i in range(1, len(ops)) if ops[i] != ops[i - 1]]

        detected = segmentation.detect_changepoints(power, min_seg_len=4)
        score = segmentation.boundary_recovery(detected, ref, tol_s=5)
        require(score["recall"] > 0.7,
                f"boundary recall too low on clean fixture: {score}")

        states = segmentation.classify_states(power)
        require(set(states) <= {"off", "idle", "positioning", "cutting"},
                f"unexpected state labels: {set(states)}")
        require((states == "cutting").mean() > 0.3,
                "cutting share implausibly low on fixture stream")
    print(f"  segmentation: OK (recall {score['recall']:.2f}, "
          f"precision {score['precision']:.2f} on {score['n_reference']} boundaries)")


def test_fingerprint_classification():
    """Leave-one-run-out nearest-centroid identifies fixture operations."""
    from EXPLORATORY.shared import adapters

    with tempfile.TemporaryDirectory() as tmp:
        _fixture_env(tmp, n_runs=3)
        rows = []
        for part in ("body", "lid"):
            for run in (1, 2, 3):
                stream = adapters.load_power_stream(run, part=part)
                idle = float(np.percentile(stream["power_w"], 10))
                for op, seg in stream.groupby("operation_id"):
                    if op == "NONE" or op.startswith("UNKNOWN"):
                        continue
                    feats = signatures.extract_features(
                        seg["power_w"].to_numpy(), idle)
                    feats.update({"op": op, "run": f"{part}{run}"})
                    rows.append(feats)
        table = pd.DataFrame(rows)
        X = table[signatures.FEATURE_NAMES].to_numpy()
        result = signatures.leave_one_group_out(X, table["op"], table["run"])
        require(result["n_total"] > 0, "no evaluable rows")
        require(result["accuracy"] > 0.6,
                f"fingerprint accuracy too low on clean fixture: {result['accuracy']:.2f}")
    print(f"  fingerprinting: OK (LORO accuracy {result['accuracy']:.2f} "
          f"over {result['n_total']} operation instances)")


def test_am_fixture_loader():
    """AM loader reproduces AM fixture truth exactly (same dt rule)."""
    from EXPLORATORY.shared import adapters

    saved = os.environ.get("AM_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            truth = pd.DataFrame(fixtures.generate_am_fixture_dataset(tmp, n_runs=2))
            os.environ["AM_DATA_DIR"] = tmp
            table = adapters.load_am_energy()
            merged = truth.merge(table, on=["part", "run_id"],
                                 suffixes=("_truth", "_load"))
            require(len(merged) == len(truth), "AM loader lost fixture prints")
            rel = ((merged["energy_wh_load"] - merged["energy_wh_truth"]).abs()
                   / merged["energy_wh_truth"])
            require(bool((rel < 1e-6).all()),
                    f"AM energy mismatch vs truth: worst {rel.max():.2e}")
            stream = adapters.load_am_power_stream("DriveShaft", 1)
            require((stream["power_w"] >= 0).all(), "negative AM power")
            require(stream["t"].is_monotonic_increasing, "AM stream not sorted")
    finally:
        if saved is None:
            os.environ.pop("AM_DATA_DIR", None)
        else:
            os.environ["AM_DATA_DIR"] = saved
    print(f"  AM fixture loader: OK ({len(merged)} prints, exact energy match)")


def test_montecarlo_agrees_with_delta_method():
    """MC total-energy interval matches the exact delta-method moments."""
    rng = np.random.default_rng(0)
    stats = [
        montecarlo.OperationStat(f"op{i}", float(m), float(s), 20)
        for i, (m, s) in enumerate(zip(rng.uniform(5, 200, 30),
                                       rng.uniform(0.5, 10, 30)))
    ]
    samples = montecarlo.mc_total_energy(stats, n_draws=40000, seed=1)
    mc_mean, mc_sd = float(samples.mean()), float(samples.std(ddof=1))
    d_mean, d_sd = montecarlo.delta_total_energy(stats)
    require(abs(mc_mean - d_mean) / d_mean < 0.01,
            f"MC mean {mc_mean:.2f} vs delta {d_mean:.2f}")
    require(abs(mc_sd - d_sd) / d_sd < 0.05,
            f"MC sd {mc_sd:.3f} vs delta {d_sd:.3f}")

    fp = montecarlo.footprint_from_energy(
        samples, mass_g=1880.0, mass_sd_g=5.0,
        cf_al_kg_per_kg=12.0, grid_ci_kg_per_kwh=0.4)
    require(bool((fp["mfg_share_pct"] > 0).all()
                 and (fp["mfg_share_pct"] < 100).all()),
            "manufacturing share outside (0, 100)")
    print(f"  montecarlo vs delta: OK (mean {mc_mean:.1f} vs {d_mean:.1f} Wh, "
          f"sd {mc_sd:.2f} vs {d_sd:.2f})")


def test_injected_drift_is_visible():
    """A fixture generated WITH drift shows it; one without does not."""
    from EXPLORATORY.shared import adapters

    def slope_of(truth_df, op="CAVITY_MILL_OUTSIDE"):
        g = truth_df[truth_df["operation"] == op]
        x = g["run_id"].to_numpy(dtype=float)
        y = g["energy_wh"].to_numpy(dtype=float)
        return float(np.polyfit(x, y, 1)[0] / y.mean())

    with tempfile.TemporaryDirectory() as tmp:
        truth_flat = pd.DataFrame(fixtures.generate_fixture_dataset(
            tmp, n_runs=6, seed=3, drift_pct_per_run=0.0, noise_sd_frac=0.01))
    with tempfile.TemporaryDirectory() as tmp:
        truth_drift = pd.DataFrame(fixtures.generate_fixture_dataset(
            tmp, n_runs=6, seed=3, drift_pct_per_run=4.0, noise_sd_frac=0.01))
    require(slope_of(truth_drift) > slope_of(truth_flat) + 0.01,
            "injected 4%/run drift not visible in truth energies")
    print("  injected drift visibility: OK")


ALL_TESTS = [
    test_pipeline_recovers_truth_energy,
    test_power_stream_loader,
    test_segmentation_recovers_boundaries,
    test_fingerprint_classification,
    test_am_fixture_loader,
    test_montecarlo_agrees_with_delta_method,
    test_injected_drift_is_visible,
]


def main() -> int:
    print("=" * 60)
    print("SHARED LAYER TESTS (synthetic fixtures, full real pipeline)")
    print("=" * 60)
    failures = 0
    saved_env = os.environ.get("CNC_DATA_DIR")
    for t in ALL_TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"  FAIL {t.__name__}: {e}")
        finally:
            if saved_env is None:
                os.environ.pop("CNC_DATA_DIR", None)
            else:
                os.environ["CNC_DATA_DIR"] = saved_env
    print("=" * 60)
    print("ALL PASSED" if failures == 0 else f"{failures} TEST(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
