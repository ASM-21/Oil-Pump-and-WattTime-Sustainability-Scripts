#!/usr/bin/env python3
"""
carbon_scheduling.py
====================

Carbon-aware scheduling simulation. Takes the per-operation energy and duration
profiles from the operation_csvs folder, builds a per-program "job" (its operation
sequence as a power-vs-time profile), and lays that job onto a grid carbon-intensity
curve to compare scheduling strategies on total CO2e. Points straight at the
operation_csvs folder; no separate feature step.

Strategies compared (place the job to finish before a deadline):
  baseline_now     run immediately at t0
  fixed_overnight  start at a fixed off-peak hour
  threshold        start at the first window whose mean intensity is below a
                   percentile of the curve (the threshold heuristic)
  optimal_shift    brute-force the start time that minimizes carbon (lower bound)

Carbon curve: pass a real WattTime/MOER export with --carbon-csv (and --time-col /
--value-col / --value-unit), or several archetype curves with --carbon-dir. With no
input it synthesizes three daily archetypes (solar-dip, evening-peak, flat-volatile)
so it runs out of the box and shows that savings vary by grid and can go negative.

Outputs (into --output, default ./ml/scheduling):
  job_profiles.csv        per program: operation sequence, duration, power, energy
  schedule_results.csv    program x archetype x strategy: carbon, start, savings %
  savings_summary.csv      mean savings by strategy and archetype
  *.png                    carbon curves with chosen windows, savings bars

Usage
-----
  python carbon_scheduling.py --input ./operation_csvs
  python carbon_scheduling.py --input ./operation_csvs --carbon-csv moer.csv \
        --time-col point_time --value-col value --value-unit lbs_per_mwh
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

_HERE = Path(__file__).resolve().parent

import numpy as np
import pandas as pd

import features as F

warnings.filterwarnings("ignore")

DAY_S = 24 * 3600
# Unit conversions to kg CO2e per kWh.
UNIT_TO_KG_PER_KWH = {
    "kg_per_kwh": 1.0,
    "g_per_kwh": 1e-3,
    "lbs_per_mwh": 0.45359237 / 1000.0,   # lb->kg, per MWh->per kWh
    "kg_per_mwh": 1e-3,
}


# --- job profiles -----------------------------------------------------------

def build_jobs(table: pd.DataFrame, ecol: str) -> pd.DataFrame:
    """
    One representative job per program: operations ordered by their typical position
    (mean segment_id), each with mean duration, mean energy, and implied mean power.
    """
    rows = []
    for prog, g in table.groupby("program"):
        order = (g.groupby("operation")
                 .agg(seg=("segment_id", "mean"),
                      duration_s=("duration_s", "mean"),
                      energy=(ecol, "mean"))
                 .sort_values("seg").reset_index())
        for i, r in order.iterrows():
            dur = max(float(r["duration_s"]), 1.0)
            energy = float(r["energy"])
            power_kw = energy / (dur / 3600.0)   # kWh / h = kW
            rows.append({"program": prog, "step": i + 1, "operation": r["operation"],
                         "duration_s": dur, "energy_kwh": energy, "power_kw": power_kw})
    return pd.DataFrame(rows)


def job_power_per_second(job: pd.DataFrame) -> np.ndarray:
    """Piecewise-constant power (kW) sampled at 1 s over the whole job."""
    segs = [np.full(int(round(r["duration_s"])), r["power_kw"]) for _, r in job.iterrows()]
    return np.concatenate(segs) if segs else np.zeros(0)


# --- carbon curves ----------------------------------------------------------

def synth_archetypes() -> Dict[str, np.ndarray]:
    """Three 24 h carbon-intensity curves at 1 s resolution, kg CO2e/kWh."""
    t = np.linspace(0, 24, DAY_S, endpoint=False)
    curves = {
        # Solar-heavy: low midday (solar floods the grid), high overnight/evening.
        "solar_dip": 0.45 - 0.18 * np.cos((t - 13) / 24 * 2 * np.pi)
                     + 0.04 * np.sin(t / 24 * 6 * np.pi),
        # Evening peak: low in the morning, ramps to a sharp evening peak, stays high.
        "evening_peak": 0.30 + 0.22 / (1 + np.exp(-(t - 18)))
                        + 0.10 * np.exp(-((t - 19) ** 2) / 4),
        # Flat but volatile: small swings, shifting barely helps and can backfire.
        "flat_volatile": 0.40 + 0.04 * np.sin(t / 24 * 10 * np.pi)
                         + 0.03 * np.cos(t / 24 * 3 * np.pi),
    }
    return {k: np.clip(v, 0.05, None) for k, v in curves.items()}


def load_carbon_csv(path: Path, time_col: str, value_col: str, unit: str) -> np.ndarray:
    df = pd.read_csv(path)
    for c in (time_col, value_col):
        if c not in df.columns:
            raise ValueError(f"{path.name}: column '{c}' not found. Have {list(df.columns)}.")
    df = df[[time_col, value_col]].dropna()
    ts = pd.to_datetime(df[time_col], errors="coerce")
    val = pd.to_numeric(df[value_col], errors="coerce") * UNIT_TO_KG_PER_KWH[unit]
    ok = ts.notna() & val.notna()
    ts, val = ts[ok], val[ok]
    secs = (ts - ts.min()).dt.total_seconds().to_numpy()
    grid = np.arange(0, int(secs.max()) + 1)
    return np.interp(grid, secs, val.to_numpy())


def get_archetypes(args) -> Dict[str, np.ndarray]:
    if args.carbon_csv:
        p = Path(args.carbon_csv)
        return {p.stem: load_carbon_csv(p, args.time_col, args.value_col, args.value_unit)}
    if args.carbon_dir:
        out = {}
        for p in sorted(Path(args.carbon_dir).glob("*.csv")):
            out[p.stem] = load_carbon_csv(p, args.time_col, args.value_col, args.value_unit)
        if out:
            return out
    print("No carbon data supplied; using synthetic archetypes (solar_dip, "
          "evening_peak, flat_volatile).")
    return synth_archetypes()


# --- scheduling -------------------------------------------------------------

def carbon_for_start(power_s: np.ndarray, intensity_s: np.ndarray, start: int) -> float:
    """kg CO2e for running the job starting at second `start`."""
    window = intensity_s[start:start + len(power_s)]
    return float(np.sum(power_s * window) / 3600.0)   # kW * (kg/kWh) * (1s in h)


def feasible_starts(job_len: int, total: int, start_now: int, deadline_s: int,
                    step: int) -> np.ndarray:
    first = start_now
    last = min(total, start_now + deadline_s) - job_len
    if last < first:
        return np.array([first])
    return np.arange(first, last + 1, step)


def schedule_job(power_s, intensity_s, start_now, deadline_s, overnight_hour, pctl, step):
    total = len(intensity_s)
    job_len = len(power_s)
    starts = feasible_starts(job_len, total, start_now, deadline_s, step)
    carbons = np.array([carbon_for_start(power_s, intensity_s, int(s)) for s in starts])

    results = {}
    results["baseline_now"] = (start_now, carbon_for_start(power_s, intensity_s, start_now))
    # next occurrence of the overnight hour at or after arrival
    on = int(overnight_hour * 3600)
    while on < start_now:
        on += DAY_S
    on = min(on, total - job_len)
    results["fixed_overnight"] = (on, carbon_for_start(power_s, intensity_s, on))
    # threshold over the deferrable window only
    window_mean = np.array([np.mean(intensity_s[int(s):int(s) + job_len]) for s in starts])
    defer = intensity_s[start_now:min(total, start_now + deadline_s)]
    thr = np.percentile(defer, pctl)
    below = np.where(window_mean <= thr)[0]
    idx = below[0] if below.size else int(np.argmin(window_mean))
    results["threshold"] = (int(starts[idx]), float(carbons[idx]))
    best = int(np.argmin(carbons))
    results["optimal_shift"] = (int(starts[best]), float(carbons[best]))
    return results


def maybe_plot(archetypes, picks, savings, out_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    # Carbon curves with optimal windows for the first program.
    fig, ax = plt.subplots(figsize=(9, 4))
    hrs = lambda n: np.arange(n) / 3600.0
    for name, curve in archetypes.items():
        ax.plot(hrs(len(curve)), curve, label=name, lw=1.2)
    ax.set_xlabel("hour"); ax.set_ylabel("carbon intensity (kg CO2e/kWh)")
    ax.set_title("Grid carbon-intensity archetypes"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out_dir / "carbon_curves.png", dpi=130); plt.close(fig)

    # Savings by strategy, averaged over programs, per archetype.
    piv = savings.pivot_table(index="archetype", columns="strategy",
                              values="savings_pct", aggfunc="mean")
    piv = piv[[c for c in ["fixed_overnight", "threshold", "optimal_shift"] if c in piv.columns]]
    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(piv)); w = 0.8 / piv.shape[1]
    for k, col in enumerate(piv.columns):
        ax.bar(x + k * w, piv[col].values, w, label=col)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x + 0.4 - w / 2); ax.set_xticklabels(piv.index, rotation=15)
    ax.set_ylabel("carbon savings vs run-now (%)")
    ax.set_title("Scheduling savings by strategy and grid"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out_dir / "savings_by_strategy.png", dpi=130); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Carbon-aware scheduling simulation over operation energy profiles.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default=str(_HERE / "operation_csvs"))
    ap.add_argument("--output", default=str(_HERE / "ml/scheduling"))
    ap.add_argument("--carbon-csv", default=None, help="Single carbon-intensity CSV.")
    ap.add_argument("--carbon-dir", default=None, help="Folder of archetype CSVs.")
    ap.add_argument("--time-col", default="timestamp")
    ap.add_argument("--value-col", default="value")
    ap.add_argument("--value-unit", default="lbs_per_mwh",
                    choices=list(UNIT_TO_KG_PER_KWH))
    ap.add_argument("--target", choices=["auto", "kwh_meter", "wh_integral"], default="auto")
    ap.add_argument("--deadline-hours", type=float, default=24.0)
    ap.add_argument("--start-hour", type=float, default=20.0,
                    help="Clock hour (0-24) the job becomes available ('run now').")
    ap.add_argument("--overnight-hour", type=float, default=2.0)
    ap.add_argument("--threshold-pctl", type=float, default=25.0,
                    help="Run when window-mean intensity is below this percentile.")
    ap.add_argument("--step-min", type=float, default=5.0, help="Start-time search step.")
    args = ap.parse_args()

    out_dir = Path(args.output); out_dir.mkdir(parents=True, exist_ok=True)
    table, _ = F.prepare(args.input, "segment")
    ecol = ("energy_kwh_meter" if (args.target in ("auto", "kwh_meter")
            and "energy_kwh_meter" in table) else "energy_wh_integral")
    if ecol == "energy_wh_integral" and "energy_wh_integral" in table:
        table = table.assign(**{ecol: table["energy_wh_integral"] / 1000.0})  # Wh->kWh
        ecol_label = "energy_wh_integral(kWh)"
    else:
        ecol_label = ecol

    jobs = build_jobs(table, ecol)
    jobs.to_csv(out_dir / "job_profiles.csv", index=False)

    archetypes = get_archetypes(args)
    deadline_s = int(args.deadline_hours * 3600)
    step = max(int(args.step_min * 60), 1)
    start_now = int(args.start_hour * 3600)

    # Tile each curve so the arrival + deadline window is always covered.
    need = start_now + deadline_s + DAY_S
    tiled = {name: np.tile(curve, int(np.ceil(need / len(curve))))[:need]
             for name, curve in archetypes.items()}

    rows = []
    for prog, jg in jobs.groupby("program"):
        power_s = job_power_per_second(jg.sort_values("step"))
        job_len = len(power_s)
        total_energy = jg["energy_kwh"].sum()
        for arch, curve in tiled.items():
            res = schedule_job(power_s, curve, start_now, deadline_s, args.overnight_hour,
                               args.threshold_pctl, step)
            base = res["baseline_now"][1]
            for strat, (start, carbon) in res.items():
                rows.append({
                    "program": prog, "archetype": arch, "strategy": strat,
                    "start_clock_hour": round((start / 3600.0) % 24, 1),
                    "carbon_kg": round(carbon, 5),
                    "savings_pct": round(100 * (base - carbon) / base, 2) if base else 0.0,
                    "job_energy_kwh": round(total_energy, 5),
                    "job_duration_s": job_len,
                })
    results = pd.DataFrame(rows)
    results.to_csv(out_dir / "schedule_results.csv", index=False)

    savings = results[results["strategy"] != "baseline_now"]
    summary = (savings.groupby(["archetype", "strategy"])["savings_pct"].mean()
               .reset_index().sort_values(["archetype", "savings_pct"]))
    summary.to_csv(out_dir / "savings_summary.csv", index=False)
    maybe_plot(archetypes, None, results, out_dir)

    # ---- console summary -------------------------------------------------
    print(f"Energy target: {ecol_label}. Programs (jobs): {jobs['program'].nunique()}. "
          f"Grids: {len(archetypes)}.\n")
    print("Mean carbon savings vs run-now (averaged over jobs):")
    for arch in summary["archetype"].unique():
        sub = summary[summary["archetype"] == arch]
        print(f"  {arch}:")
        for _, r in sub.iterrows():
            flag = "  (worse than run-now)" if r["savings_pct"] < 0 else ""
            print(f"    {r['strategy']:15s} {r['savings_pct']:+6.1f}%{flag}")

    # Threshold vs time-of-day, and any backfire.
    piv = summary.pivot(index="archetype", columns="strategy", values="savings_pct")
    if {"threshold", "fixed_overnight"}.issubset(piv.columns):
        wins = (piv["threshold"] > piv["fixed_overnight"]).sum()
        print(f"\nThreshold beat fixed-overnight on {wins}/{len(piv)} grids.")
    if "threshold" in piv.columns and (piv["threshold"] < 0).any():
        bad = list(piv.index[piv["threshold"] < 0])
        print(f"Negative-savings case (heuristic backfires): {bad}. "
              f"On these grids the run-now window was already low-carbon.")

    print(f"\nWrote results to {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
