"""
Validate anomalies.py and report.py.

Checks:
  - small groups are marked insufficient_n, not flagged (no false outliers)
  - with enough parts, a planted energy outlier is caught (experiment level)
  - drift_scan runs and marks proxy ordering
  - signal_anomalies catches a part whose counter does not match the NC
  - generate_report writes a self-contained HTML with embedded figures
"""

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

import config as C
import dataset_explorer as dx
import anomalies as anom
import report as rpt

logging.basicConfig(level=logging.WARNING)

MPF = """; part
N10 G90 G54
N20 T1 M6
N30 S6000 M3 F600
N40 G0 X10 Y10 Z2
N50 G1 Z-3 F300
N60 G1 X50 Y10 F600
N70 G0 Z20
N80 M5
N90 M30
"""
LINE_W = {10: 300, 20: 1000, 30: 700, 40: 500, 50: 1400, 60: 1400,
          70: 500, 80: 700, 90: 300}


def write_part(folder, eid, scale, bad_counter=False):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{eid}.mpf").write_text(MPF)
    counter, p_sp, p_x = [], [], []
    for ln, w in LINE_W.items():
        w *= scale
        for _ in range(500):
            # a part with a broken counter: numbers that match no N-number
            counter.append(ln + 1000 if bad_counter else ln)
            p_sp.append(w*0.8); p_x.append(w*0.2)
    n = len(counter)
    json.dump({"CYCLE": counter, "POWER|1": p_x, "POWER|2": [0.0]*n,
               "POWER|3": [0.0]*n, "POWER|4": [0.0]*n, "POWER|5": [0.0]*n,
               "POWER|6": p_sp, "POWER|7": [0.0]*n}, open(folder/f"{eid}.json", "w"))


def main():
    # small corpus (3 parts) to test insufficient_n honesty
    small = Path("anom_small")
    write_part(small/"a1", "a1", 1.0)
    write_part(small/"a2", "a2", 1.1)
    write_part(small/"b1", "b1", 1.6)
    cfg = C.BRILLINGER
    man_s = dx.build_manifest(small, cfg)
    res_s = dx.corpus_run(man_s, cfg)

    print("=" * 60, "\n[A] small groups -> insufficient_n, no false flags")
    oo = anom.operation_outliers(res_s["store"], metric="energy_j")
    eo = anom.experiment_outliers(res_s["per_experiment"])
    print("operation group notes:\n", oo["group_notes"].to_string(index=False))
    print("experiment flags (should be empty):", len(eo["flags"]))
    ok_smalln = (oo["group_notes"]["status"] == "insufficient_n").all() and eo["flags"].empty
    print(f"  no spurious flags on n<5 groups: {ok_smalln}")

    # larger corpus: 8 normal AlCuMgPb parts + 1 planted outlier (5x energy)
    big = Path("anom_big")
    for i in range(8):
        write_part(big/f"n{i}", f"n{i}", 1.0 + 0.02*i)
    write_part(big/"outlier", "outlier", 5.0)   # clear energy outlier
    man_b = dx.build_manifest(big, cfg)   # all AlCuMgPb (same material)
    res_b = dx.corpus_run(man_b, cfg)

    print("\n" + "=" * 60, "\n[B] planted outlier caught (n>=5 group)")
    eo_b = anom.experiment_outliers(res_b["per_experiment"])
    print(eo_b["flags"].to_string(index=False))
    caught = "outlier" in set(eo_b["flags"].get("experiment", pd.Series(dtype=str)))
    print(f"  'outlier' part flagged: {caught}")

    print("\n" + "=" * 60, "\n[C] drift scan (proxy ordering)")
    drift = anom.drift_scan(res_b["per_experiment"])
    print(drift.to_string(index=False))
    ok_drift = bool(drift["order_is_proxy"].all()) and "flag" in drift.columns

    print("\n" + "=" * 60, "\n[D] signal anomalies: broken-counter part")
    bad = Path("anom_bad")
    write_part(bad/"good", "good", 1.0, bad_counter=False)
    write_part(bad/"broken", "broken", 1.0, bad_counter=True)
    man_bad = dx.build_manifest(bad, cfg)
    sa = anom.signal_anomalies(man_bad, cfg)
    print(sa.to_string(index=False))
    flagged_broken = "broken" in set(sa.get("experiment", pd.Series(dtype=str)))
    print(f"  broken-counter part flagged for low nc match: {flagged_broken}")

    print("\n" + "=" * 60, "\n[E] report generation")
    figs = Path("anom_figs"); figs.mkdir(exist_ok=True)
    # make one real figure to embed
    import viz, signals as sig
    power = dx.bp.load_power_json(str(big/"n0"/"n0.json"),
                                 cmap=dx.channel_map_from_config(cfg))
    nc = dx.bp.parse_mpf(str(big/"n0"/"n0.mpf"))
    lbl = sig.label_samples(power, nc, cfg)
    viz.save_figure(viz.plot_power_timeline(lbl)[0], figs/"timeline.png")

    ch = dx.characterize_corpus(res_b["store"], res_b["per_experiment"])
    an_all = anom.run_all(res_b["store"], res_b["per_experiment"], man_b, cfg)
    flags = {k: (v.get("flags") if isinstance(v, dict) else v) for k, v in an_all.items()}
    ctx = {
        "provenance": res_b["provenance"].as_dict(),
        "manifest": man_b, "per_experiment": res_b["per_experiment"],
        "characterization": ch, "anomalies": flags,
        "feature_correlations": pd.DataFrame(
            {"feature": ["bbox_x_mm"], "correlation": [0.9], "n": [9]}),
        "feature_table": res_b["per_experiment"],
        "figures": {"power timeline": figs/"timeline.png"},
    }
    path = rpt.generate_report(ctx, Path("anom_out")/"report.html")
    size = Path(path).stat().st_size
    text = Path(path).read_text()
    ok_report = size > 3000 and "base64" in text \
        and "Feature correlations" in text and "Exploratory only" in text
    print(f"  report {size}B, embeds figure + carries stats caveat: {ok_report}")

    results = {"small_n_honesty": bool(ok_smalln), "outlier_caught": bool(caught),
               "drift": bool(ok_drift), "signal_anomaly": bool(flagged_broken),
               "report": bool(ok_report)}
    print("\n" + "=" * 60)
    print("RESULTS:", results)
    print("ALL PASS:", all(results.values()))


if __name__ == "__main__":
    main()
