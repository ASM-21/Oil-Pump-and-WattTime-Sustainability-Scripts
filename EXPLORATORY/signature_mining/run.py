"""
SIGNATURE MINING -- below energy totals, into the raw 1 Hz waveforms.

The paper's attribution rides on CAM-originated UUIDs. This project asks how
much of that attribution is recoverable from the power SIGNAL alone, because
that is what decides whether the method generalizes to machines with no CAM
integration (the retrofit claim):

  1. Boundary recovery: UUID-free changepoint detection vs UUID boundaries
     (precision/recall/F1 per program).
  2. Machine-state decomposition: off/idle/positioning/cutting shares of
     time and energy, from power alone.
  3. Operation fingerprinting: nearest-centroid on signature features,
     leave-one-run-out. Plus the honest generalization test: train on BODY
     operations only, classify LID operations at the category level
     (cross-part transfer).

Always runs: fixtures (exact real format, known truth) verify the method
end to end through the real pipeline. If CNC_DATA_DIR points at the real
Al6061 data, the same analysis runs again on it and writes the measured
tables next to the fixture ones.

Run from the repo root:
    python EXPLORATORY/signature_mining/run.py
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

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared import fixtures, segmentation, signatures
from EXPLORATORY.shared.adapters import _OP_TO_CATEGORY

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()


# ---------------------------------------------------------------------------
# Analysis on one data source (fixture folder or the real CNC_DATA_DIR)
# ---------------------------------------------------------------------------

def analyze_source(tag: str) -> dict:
    """Run all three analyses against whatever CNC_DATA_DIR points at."""
    from EXPLORATORY.shared import adapters

    runs = adapters.list_run_ids()
    require(len(runs) > 0, f"no runs found for source {tag}")

    boundary_rows, state_rows, feature_rows = [], [], []
    example_trace = None

    for part, run_id in runs:
        stream = adapters.load_power_stream(run_id, part=part)
        idle_w = float(np.percentile(stream["power_w"], 10))

        for src, sf in stream.groupby("source_file"):
            power = sf["power_w"].to_numpy()
            ops = sf["operation_id"].to_numpy()

            # 1. Boundary recovery.
            ref = [i for i in range(1, len(ops)) if ops[i] != ops[i - 1]]
            detected = segmentation.detect_changepoints(power, min_seg_len=4)
            score = segmentation.boundary_recovery(detected, ref, tol_s=5)
            boundary_rows.append({"source": tag, "file": src, **score})
            if example_trace is None:
                example_trace = (src, power, ref, detected)

            # 2. State decomposition (time and energy shares).
            states = segmentation.classify_states(power, idle_power_w=idle_w)
            for state in ("off", "idle", "positioning", "cutting"):
                m = states == state
                state_rows.append({
                    "source": tag, "file": src, "state": state,
                    "time_share_pct": 100 * float(m.mean()),
                    "energy_share_pct": 100 * float(power[m].sum() / power.sum()),
                })

            # 3. Signature features per operation instance.
            for op, seg in sf.groupby("operation_id"):
                if op == "NONE" or str(op).startswith("UNKNOWN"):
                    continue
                feats = signatures.extract_features(seg["power_w"].to_numpy(), idle_w)
                feats.update({
                    "op": op,
                    "category": _OP_TO_CATEGORY.get(op, "unknown"),
                    "part": part,
                    "run": f"{part}{run_id}",
                })
                feature_rows.append(feats)

    boundaries = pd.DataFrame(boundary_rows)
    states = pd.DataFrame(state_rows)
    feats = pd.DataFrame(feature_rows)

    X = feats[signatures.FEATURE_NAMES].to_numpy()
    loro = signatures.leave_one_group_out(X, feats["op"], feats["run"])

    # Cross-part transfer at CATEGORY level: body-trained, lid-tested.
    body = feats[feats["part"] == "body"]
    lid = feats[feats["part"] == "lid"]
    transfer = None
    shared_cats = set(body["category"]) & set(lid["category"])
    lid_shared = lid[lid["category"].isin(shared_cats)]
    if len(lid_shared) and len(body):
        clf = signatures.NearestCentroid().fit(
            body[signatures.FEATURE_NAMES].to_numpy(), body["category"])
        pred = clf.predict(lid_shared[signatures.FEATURE_NAMES].to_numpy())
        transfer = float(np.mean(pred == lid_shared["category"].to_numpy()))

    # Open-set rejection: an attribution system in the field will meet
    # operations it was never trained on; misassigning them silently would
    # corrupt the energy ledger. Calibrate a distance threshold from the
    # training set's own nearest-centroid distances (95th percentile), then
    # confirm a synthetic never-seen signature (a 4x power anomaly in feature
    # space, e.g. a fault or an unknown heavy operation) lands beyond it.
    clf_all = signatures.NearestCentroid().fit(X, feats["op"])
    _, d_train = clf_all.predict_with_distance(X)
    threshold = float(np.percentile(d_train, 95))
    anomaly = X[np.argmax(X[:, signatures.FEATURE_NAMES.index("mean_w")])].copy()
    for col in ("mean_w", "peak_w", "p25_w", "p75_w", "mean_abs_diff_w"):
        anomaly[signatures.FEATURE_NAMES.index(col)] *= 4.0
    _, d_anom = clf_all.predict_with_distance(anomaly.reshape(1, -1))
    open_set = {
        "threshold": threshold,
        "train_reject_rate": float(np.mean(d_train > threshold)),
        "anomaly_distance": float(d_anom[0]),
        "anomaly_rejected": bool(d_anom[0] > threshold),
    }

    return {
        "tag": tag,
        "boundaries": boundaries,
        "states": states,
        "features": feats,
        "loro": loro,
        "transfer_acc": transfer,
        "open_set": open_set,
        "example_trace": example_trace,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def figure_trace(example, tag: str) -> None:
    import matplotlib.pyplot as plt

    src, power, ref, detected = example
    apply_style()
    fig, ax = plt.subplots(figsize=(7.0, 2.2))
    t = np.arange(len(power))
    ax.plot(t, power, linewidth=0.6, color=COLORS[0])
    for i, r in enumerate(ref):
        ax.axvline(r, color=COLORS[3], linewidth=0.8,
                   label="UUID boundary" if i == 0 else None)
    for i, d in enumerate(detected):
        ax.axvline(d, color=COLORS[6], linewidth=0.8, linestyle="--",
                   label="detected (power only)" if i == 0 else None)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Power (W)")
    ax.set_title(f"{src} ({tag})", fontsize=7)
    ax.legend(fontsize=6, loc="upper right")
    save_fig(fig, str(OUT / f"boundary_overlay_{tag}"))


def figure_state_shares(states: pd.DataFrame, tag: str) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    agg = states.groupby("state")[["time_share_pct", "energy_share_pct"]].mean()
    agg = agg.reindex(["cutting", "positioning", "idle", "off"]).dropna()
    fig, ax = plt.subplots(figsize=(3.5, 2.4))
    y = np.arange(len(agg))
    ax.barh(y - 0.18, agg["time_share_pct"], height=0.36,
            color=COLORS[2], label="time share")
    ax.barh(y + 0.18, agg["energy_share_pct"], height=0.36,
            color=COLORS[6], label="energy share")
    ax.set_yticks(y, agg.index)
    ax.set_xlabel("Share (%)")
    ax.legend(fontsize=6)
    save_fig(fig, str(OUT / f"state_shares_{tag}"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_and_write(result: dict) -> list[str]:
    tag = result["tag"]
    result["boundaries"].to_csv(OUT / f"boundary_recovery_{tag}.csv", index=False)
    result["states"].to_csv(OUT / f"state_shares_{tag}.csv", index=False)
    result["features"].to_csv(OUT / f"signature_features_{tag}.csv", index=False)
    figure_trace(result["example_trace"], tag)
    figure_state_shares(result["states"], tag)

    loro = result["loro"]
    lines = [
        f"### Source: {tag}",
        "",
        f"- Boundary recovery (mean over files): "
        f"recall {result['boundaries']['recall'].mean():.2f}, "
        f"precision {result['boundaries']['precision'].mean():.2f}, "
        f"f1 {result['boundaries']['f1'].mean():.2f}",
        f"- Fingerprint LORO accuracy: {loro['accuracy']:.2f} "
        f"({loro['n_correct']}/{loro['n_total']})",
        f"- Cross-part transfer (body-trained, lid categories): "
        + (f"{result['transfer_acc']:.2f}" if result["transfer_acc"] is not None
           else "n/a"),
        f"- Open-set rejection: threshold {result['open_set']['threshold']:.2f} "
        f"(95th pct of training distances, "
        f"{100 * result['open_set']['train_reject_rate']:.0f}% train rejection); "
        f"synthetic 4x anomaly at distance "
        f"{result['open_set']['anomaly_distance']:.2f} -> "
        + ("REJECTED" if result["open_set"]["anomaly_rejected"] else "NOT rejected"),
        "",
    ]
    return lines


def main() -> None:
    sections: list[str] = []

    # 1. Fixture pass: always runs, verifies the method against known truth.
    saved = os.environ.get("CNC_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            fix = analyze_source("fixture")
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved

    require(fix["boundaries"]["recall"].mean() > 0.7,
            "fixture boundary recall below 0.7; detector regressed")
    require(fix["loro"]["accuracy"] > 0.6,
            "fixture fingerprint accuracy below 0.6; features regressed")
    require(fix["open_set"]["anomaly_rejected"],
            "synthetic never-seen signature was NOT rejected; open-set "
            "threshold calibration regressed")
    sections += run_and_write(fix)

    # 2. Real pass, only if the environment points at data.
    real_note = ("Real CNC data not reachable in this run. Set CNC_DATA_DIR "
                 "to the Al6061 folder and re-run; the measured tables will "
                 "be written next to the fixture ones with tag 'measured'.")
    if os.environ.get("CNC_DATA_DIR") and os.environ.get("FIXTURE_SMOKE") != "1":
        try:
            real = analyze_source("measured")
            sections += run_and_write(real)
            real_note = "Measured tables written (tag 'measured')."
        except Exception as e:  # park the real half only
            gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
            with gap.open("a") as f:
                f.write(f"- signature_mining (real-data pass): {e}\n")
            real_note = f"Real-data pass parked: {e}"

    require(not log.any_disagreements(), "a cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Signature mining: findings\n\n"
        "Claim under test: operation-level attribution is partially "
        "recoverable from the 1 Hz power signal alone, making the method "
        "retrofittable on machines without CAM/UUID integration.\n\n"
        + "\n".join(sections) + "\n"
        f"{real_note}\n\n"
        "Interpretation guide: boundary recall is the fraction of true "
        "operation transitions a UUID-free detector finds; fingerprint "
        "accuracy is how often the operation's identity is recovered from "
        "waveform features; cross-part transfer shows whether signatures "
        "learned on one part carry to another at the category level.\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK signature_mining")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
