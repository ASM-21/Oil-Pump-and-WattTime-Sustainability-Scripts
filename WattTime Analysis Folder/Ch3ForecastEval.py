"""
ch3_forecast_eval.py — Day-Ahead Forecast Scheduling Evaluation

Simple method:
  For each region and date, take the LAST forecast issued before midnight
  the night before (generated_at < date 00:00 local).  Use those forecast
  values to pick the lowest-MOER 2-hr window within the shift (06:00-18:00).
  Measure actual 5-min MOER at that chosen window.  Compare to baseline and
  optimal.

This is intentionally simple — it mirrors the real operator workflow:
  "Check tonight's forecast, pick tomorrow's best window."

Outputs (ch3_outputs/):
    Tables:
        table_forecast_eval_summary.csv/md  — savings %, capture rate by region
        table_forecast_eval_days.csv        — day-level detail
    Figures:
        fig_forecast_savings.png/pdf        — grouped bar vs baseline/TL/optimal
        fig_forecast_capture_rate.png/pdf   — capture rate by region
        fig_forecast_error_dist.png/pdf     — forecast error violin
    Numbers appended to ch3_numbers.md

Usage:
    python ch3_forecast_eval.py
    python ch3_forecast_eval.py --recompute
"""

import argparse
import gc
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pyarrow.parquet as pq
import pyarrow.compute as pc
import pytz

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, get_run_dir, bootstrap_ci,
    CH3_REGIONS, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    N_BOOTSTRAP, CHARACTERIZATION_YEARS,
    rlabel, rshort, rcolor,
    TABLES_DIR, FIGURES_DIR,
)
from config import REGIONS as ALL_REGIONS

warnings.filterwarnings("ignore", category=FutureWarning)

# Timezone per CH3 region
_REGION_TZ = {r: ALL_REGIONS[r]["timezone"] for r in CH3_REGIONS if r in ALL_REGIONS}

# =============================================================================
# CONFIG
# =============================================================================

ANALYSIS_YEARS        = CHARACTERIZATION_YEARS
MIN_FORECAST_COVERAGE = 0.30   # exclude region if fewer than 30% of days have a forecast
SECTION_TAG           = "Forecast-Eval"


# =============================================================================
# I/O helpers
# =============================================================================

def _forecast_path() -> "Path | None":
    run_dir = get_run_dir()
    p = run_dir / "processed" / "data_forecast.parquet"
    return p if p.exists() else None


def _discover_regions(fc_path: Path) -> list:
    pf = pq.ParquetFile(fc_path)
    n  = pf.metadata.num_row_groups
    idx = list(range(0, n, max(1, n // 20)))[:20]
    regions = set()
    for i in idx:
        rg = pf.read_row_group(i, columns=["region"])
        regions.update(pc.unique(rg.column("region")).to_pylist())
    return sorted(regions)


def _load_forecast_region(fc_path: Path, region: str) -> pd.DataFrame:
    """Load forecast rows for one region, timestamps stripped to tz-naive UTC."""
    try:
        tbl = pq.read_table(
            fc_path,
            columns=["region", "point_time", "generated_at", "value"],
            filters=[("region", "=", region)],
        )
    except Exception as e:
        raise RuntimeError(
            f"Pyarrow filter failed for {region}: {e}\n"
            "Re-save parquet with engine='pyarrow', index=False."
        ) from e

    df = tbl.to_pandas()
    del tbl; gc.collect()

    for col in ["point_time", "generated_at"]:
        df[col] = pd.to_datetime(df[col])
        if df[col].dt.tz is not None:
            df[col] = df[col].dt.tz_convert("UTC").dt.tz_localize(None)

    return df


# =============================================================================
# CORE: pick best window from night-before forecast
# =============================================================================

def build_day_ahead_decisions(fc_df: pd.DataFrame, region: str) -> pd.DataFrame:
    """
    For each target date D, take the latest forecast generated before midnight
    (D 00:00 UTC).  Use that forecast's 5-min values to find the 2-hr window
    (24 consecutive 5-min intervals) within the shift [06:00, 18:00) local that
    has the lowest mean predicted MOER — identical rolling-window logic to the
    actual evaluation.

    Returns one row per date:
        date, forecast_start_time (local tz-naive), forecast_start_hour (int),
        forecast_moer_pred, generated_at, horizon_h
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)  # 24
    tz            = _REGION_TZ.get(region, "UTC")
    tzobj         = pytz.timezone(tz)

    fc_df = fc_df.copy()

    # Strip tz from generated_at → tz-naive UTC
    if fc_df["generated_at"].dt.tz is not None:
        fc_df["generated_at"] = fc_df["generated_at"].dt.tz_convert("UTC").dt.tz_localize(None)

    # Convert point_time → local tz-naive
    if fc_df["point_time"].dt.tz is None:
        pt_local = fc_df["point_time"].dt.tz_localize("UTC").dt.tz_convert(tz).dt.tz_localize(None)
    else:
        pt_local = fc_df["point_time"].dt.tz_convert(tz).dt.tz_localize(None)

    fc_df["local_time"] = pt_local
    fc_df["local_hour"] = pt_local.dt.hour
    fc_df["local_date"] = pt_local.dt.date

    # Keep only shift window
    fc_df = fc_df[
        (fc_df["local_hour"] >= DAY_SHIFT_START) &
        (fc_df["local_hour"] < DAY_SHIFT_END)
    ]

    if ANALYSIS_YEARS:
        years = pd.to_datetime(fc_df["local_date"].astype(str)).dt.year
        fc_df = fc_df[years.isin(ANALYSIS_YEARS)]

    if fc_df.empty:
        return pd.DataFrame()

    rows = []
    for target_date, ddf in fc_df.groupby("local_date"):
        midnight_utc = pd.Timestamp(target_date)  # tz-naive UTC midnight

        # Only forecasts issued before midnight on this date
        candidates = ddf[ddf["generated_at"] < midnight_utc]
        if candidates.empty:
            continue

        # Latest vintage
        latest_gen = candidates["generated_at"].max()
        fc_today   = candidates[candidates["generated_at"] == latest_gen]                         .sort_values("local_time")

        vals = fc_today["value"].values
        n    = len(vals)
        if n < job_intervals:
            continue

        # Rolling 2-hr window mean over 5-min forecast values
        cs       = np.concatenate([[0], np.cumsum(vals)])
        n_win    = n - job_intervals + 1
        win_means = (cs[job_intervals:] - cs[:n_win]) / job_intervals

        best_idx  = int(np.argmin(win_means))
        best_pred = float(win_means[best_idx])
        best_time = fc_today["local_time"].iloc[best_idx]   # tz-naive local start time
        best_h    = int(best_time.hour)

        # horizon_h: hours between latest_gen (UTC) and local shift start (→ UTC)
        local_shift  = pd.Timestamp(target_date).replace(hour=DAY_SHIFT_START)
        utc_offset_h = tzobj.utcoffset(local_shift.to_pydatetime()).total_seconds() / 3600
        shift_utc_ts = local_shift - pd.Timedelta(hours=utc_offset_h)
        horizon_h    = (shift_utc_ts - latest_gen).total_seconds() / 3600

        rows.append({
            "date":                pd.Timestamp(target_date),
            "forecast_start_time": best_time,
            "forecast_start_hour": best_h,
            "forecast_moer_pred":  best_pred,
            "generated_at":        latest_gen,
            "horizon_h":           float(horizon_h),
        })

    return pd.DataFrame(rows)


# =============================================================================
# Evaluate actual MOER at forecast-chosen window
# =============================================================================

def evaluate_decisions(df_5min: pd.DataFrame, decisions: pd.DataFrame,
                        region: str) -> pd.DataFrame:
    """
    For each day in decisions, look up actual 5-min MOER at the forecast-chosen
    start hour and compute savings vs baseline (uniform random) and optimal
    (perfect hindsight).  No thresholds needed — forecast picks purely on
    lowest predicted MOER.

    baseline = mean of all valid 2-hr rolling-window means (uniform random start)
    optimal  = min 2-hr rolling-window mean (perfect hindsight)
    forecast = actual mean MOER over the 2-hr window starting at forecast_hour
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)  # 24

    win = df_5min[
        (df_5min["region"] == region) &
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].sort_values("point_time_local").copy()

    decisions = decisions.copy()
    decisions["date"] = pd.to_datetime(decisions["date"]).dt.normalize()

    records = []
    for date, ddf in win.groupby("date"):
        dec = decisions[decisions["date"] == pd.Timestamp(date)]
        if dec.empty:
            continue

        vals  = ddf["value"].values
        hours = ddf["hour"].values
        n     = len(vals)
        if n < job_intervals:
            continue

        # All valid 2-hr rolling window means (same as simulate_day baseline/optimal)
        cs      = np.concatenate([[0], np.cumsum(vals)])
        n_win   = n - job_intervals + 1
        win_means = (cs[job_intervals:] - cs[:n_win]) / job_intervals

        baseline = float(np.mean(win_means))   # uniform random start
        optimal  = float(np.min(win_means))    # perfect hindsight

        fc_pred   = float(dec["forecast_moer_pred"].iloc[0])
        horizon   = float(dec["horizon_h"].iloc[0])
        fc_h      = int(dec["forecast_start_hour"].iloc[0])

        # Match forecast start to exact 5-min interval if available,
        # otherwise fall back to first interval of that hour
        if "forecast_start_time" in dec.columns and pd.notna(dec["forecast_start_time"].iloc[0]):
            fc_time = pd.Timestamp(dec["forecast_start_time"].iloc[0])
            # Find interval index matching this local time
            if "point_time_local" in ddf.columns:
                times = pd.to_datetime(ddf["point_time_local"])
                time_idx = np.where(times.dt.floor("5min") == fc_time.floor("5min"))[0]
                idx = time_idx if len(time_idx) > 0 else np.where(hours == fc_h)[0]
            else:
                idx = np.where(hours == fc_h)[0]
        else:
            idx = np.where(hours == fc_h)[0]

        if len(idx) == 0 or idx[0] + job_intervals > n:
            continue
        actual_at_fc = float(vals[idx[0]:idx[0] + job_intervals].mean())

        def _sav(m):
            return (baseline - m) / baseline * 100 if baseline > 0 else 0.0

        sav_fc  = _sav(actual_at_fc)
        sav_opt = _sav(optimal)
        cap     = sav_fc / sav_opt if sav_opt > 0 else (1.0 if sav_fc >= 0 else 0.0)

        records.append({
            "region":             region,
            "date":               pd.Timestamp(date),
            "year":               int(ddf["year"].iloc[0]),
            "month":              int(ddf["month"].iloc[0]),
            "season":             ddf["season"].iloc[0],
            "forecast_hour":      fc_h,
            "horizon_h":          horizon,
            "forecast_moer_pred": fc_pred,
            "actual_fc_moer":     actual_at_fc,
            "baseline_moer":      baseline,
            "optimal_moer":       optimal,
            "forecast_error":     fc_pred - actual_at_fc,
            "abs_forecast_error": abs(fc_pred - actual_at_fc),
            "savings_forecast":   sav_fc,
            "savings_optimal":    sav_opt,
            "capture_rate":       cap,
        })

    return pd.DataFrame(records)


# =============================================================================
# Summary table + figures  (unchanged logic, just cleaner)
# =============================================================================

def build_summary(sim_df: pd.DataFrame, coverage_notes: dict) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        rd  = sim_df[sim_df["region"] == region]
        note = coverage_notes.get(region, "")
        if len(rd) == 0:
            rows.append({"Region": rlabel(region),
                         "Archetype": CH3_REGIONS[region]["archetype"],
                         "N Days": 0,
                         "Forecast Savings (%)": np.nan,
                         "FC Savings 95% CI Lo": np.nan,
                         "FC Savings 95% CI Hi": np.nan,
                         "Optimal Savings (%)": np.nan,

                         "Capture Rate (%)": np.nan,
                         "CR 95% CI Lo": np.nan,
                         "CR 95% CI Hi": np.nan,
                         "Mean Horizon (h)": np.nan,
                         "Forecast MAE (lbs/MWh)": np.nan,
                         "Note": note or "no forecast data"})
            continue

        sav  = rd["savings_forecast"].values
        cap  = np.clip(rd["capture_rate"].values, 0, 1) * 100
        mae  = rd["abs_forecast_error"].values

        sfc  = float(np.mean(sav))
        slo, shi = bootstrap_ci(sav, np.mean, N_BOOTSTRAP)
        clo, chi = bootstrap_ci(cap, np.mean, N_BOOTSTRAP)

        rows.append({
            "Region":                 rlabel(region),
            "Archetype":              CH3_REGIONS[region]["archetype"],
            "N Days":                 len(rd),
            "Forecast Savings (%)":   round(sfc, 1),
            "FC Savings 95% CI Lo":   round(slo, 1),
            "FC Savings 95% CI Hi":   round(shi, 1),
            "Optimal Savings (%)":    round(float(np.mean(rd["savings_optimal"].values)), 1),

            "Capture Rate (%)":       round(float(np.mean(cap)), 1),
            "CR 95% CI Lo":           round(clo, 1),
            "CR 95% CI Hi":           round(chi, 1),
            "Mean Horizon (h)":       round(float(rd["horizon_h"].mean()), 1),
            "Forecast MAE (lbs/MWh)": round(float(np.mean(mae)), 0),
            "Note":                   note,
        })

        record_number(SECTION_TAG, f"{rshort(region)} forecast savings %", sfc, ".1f")
        record_number(SECTION_TAG, f"{rshort(region)} capture rate %",
                      float(np.mean(cap)), ".1f")
        record_number(SECTION_TAG, f"{rshort(region)} forecast MAE",
                      float(np.mean(mae)), ".0f")
        record_number(SECTION_TAG, f"{rshort(region)} mean horizon h",
                      float(rd["horizon_h"].mean()), ".1f")

    return pd.DataFrame(rows)


def plot_savings_comparison(summary: pd.DataFrame):
    regions = list(CH3_REGIONS.keys())
    reg_lookup = {row["Region"]: row for _, row in summary.iterrows()}

    sav_fc, sav_opt = [], []
    ci_lo, ci_hi, colors, has_data, labels = [], [], [], [], []

    for region in regions:
        row = reg_lookup.get(rlabel(region), {})
        n   = row.get("N Days", 0)
        fc  = row.get("Forecast Savings (%)", 0) or 0
        sav_fc.append(fc)

        sav_opt.append(row.get("Optimal Savings (%)", 0) or 0)
        lo = (fc - row.get("FC Savings 95% CI Lo", fc)) if n > 0 else 0
        hi = (row.get("FC Savings 95% CI Hi", fc) - fc) if n > 0 else 0
        ci_lo.append(max(lo, 0)); ci_hi.append(max(hi, 0))
        colors.append(rcolor(region) if n > 0 else "#eeeeee")
        has_data.append(n > 0)
        labels.append(f"{rshort(region)}\n{CH3_REGIONS[region]['archetype']}")

    x = np.arange(len(regions)); w = 0.25
    with thesis_style():
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.bar(x - w/2, sav_opt, w, color="#dddddd", label="Optimal (hindsight)", zorder=2)
        ax.bar(x + w/2, sav_fc,  w, color=colors,    label="Forecast (day-ahead)", zorder=3)
        ax.errorbar(x + w/2, sav_fc, yerr=[ci_lo, ci_hi],
                    fmt="none", color="black", capsize=3, linewidth=1.0, zorder=4)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("Mean Daily Savings vs. Baseline (%)")
        patches = [mpatches.Patch(color="#dddddd", label="Optimal (hindsight)"),
                   mpatches.Patch(color="#555555", label="Forecast day-ahead (95% CI)")]
        ax.legend(handles=patches, fontsize=9, loc="upper right")
        for xi, (h, fc_v) in enumerate(zip(has_data, sav_fc)):
            if not h:
                ax.text(xi, 0.3, "no data", ha="center", va="bottom",
                        fontsize=7, color="#999", rotation=90)
        fig.tight_layout()
        save_fig(fig, "fig_forecast_savings")


def plot_capture_rate(summary: pd.DataFrame):
    regions = list(CH3_REGIONS.keys())
    reg_lookup = {row["Region"]: row for _, row in summary.iterrows()}
    caps, clo_l, chi_l, colors, has_data, labels = [], [], [], [], [], []
    for region in regions:
        row = reg_lookup.get(rlabel(region), {})
        n   = row.get("N Days", 0)
        cap = row.get("Capture Rate (%)", 0) or 0
        clo = row.get("CR 95% CI Lo", cap) or cap
        chi = row.get("CR 95% CI Hi", cap) or cap
        caps.append(cap if n > 0 else 0)
        clo_l.append(max(cap - clo, 0) if n > 0 else 0)
        chi_l.append(max(chi - cap, 0) if n > 0 else 0)
        colors.append(rcolor(region) if n > 0 else "#dddddd")
        has_data.append(n > 0)
        labels.append(rshort(region))
    x = np.arange(len(regions))
    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.bar(x, caps, color=colors, alpha=0.9, zorder=3)
        ax.errorbar(x, caps, yerr=[clo_l, chi_l],
                    fmt="none", color="black", capsize=4, linewidth=1.2, zorder=4)
        ax.axhline(100, color="#2ca02c", linewidth=1.0, linestyle="--",
                   label="Perfect capture", alpha=0.7)
        ax.axhline(50,  color="#d62728", linewidth=0.8, linestyle=":",
                   label="50% capture",   alpha=0.6)
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylabel("Capture Rate (%) — Forecast / Optimal savings")
        ax.set_ylim(0, 120); ax.legend(fontsize=9)
        fig.tight_layout()
        save_fig(fig, "fig_forecast_capture_rate")


def plot_error_dist(sim_df: pd.DataFrame):
    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 4))
        positions, data, tick_labels, vcolors = [], [], [], []
        for i, region in enumerate(CH3_REGIONS):
            rd = sim_df[sim_df["region"] == region]
            if len(rd) == 0: continue
            positions.append(i)
            data.append(rd["forecast_error"].values)
            tick_labels.append(rshort(region))
            vcolors.append(rcolor(region))
        if not data: return
        parts = ax.violinplot(data, positions=positions, showmedians=True,
                              showextrema=False, widths=0.65)
        for body, col in zip(parts["bodies"], vcolors):
            body.set_facecolor(col); body.set_alpha(0.6)
        parts["cmedians"].set_color("black"); parts["cmedians"].set_linewidth(1.5)
        ax.axhline(0, color="black", linewidth=0.9, linestyle="--", alpha=0.7)
        ax.set_xticks(positions); ax.set_xticklabels(tick_labels, fontsize=10)
        ax.set_ylabel("Forecast Error (lbs CO₂/MWh)\n(predicted − actual at chosen window)")
        fig.tight_layout()
        save_fig(fig, "fig_forecast_error_dist")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n── Day-Ahead Forecast Scheduling Evaluation ──")
    print("  Method: use last forecast before midnight → pick best 2-hr window")

    fc_path = _forecast_path()
    if fc_path is None:
        print("\n  ✗ data_forecast.parquet not found."); return

    fc_regions = _discover_regions(fc_path)
    available  = [r for r in CH3_REGIONS if r in fc_regions]
    missing    = [r for r in CH3_REGIONS if r not in fc_regions]
    if missing:
        print(f"\n  ⚠ No forecast data for: {missing}")
    if not available:
        print("  ✗ No regions available. Exiting."); return

    # Load actuals + compute thresholds once
    df_5min = load_5min()
    if ANALYSIS_YEARS:
        df_5min = df_5min[df_5min["year"].isin(ANALYSIS_YEARS)].copy()

    coverage_notes = {r: "no forecast data" for r in missing}
    all_results = []

    for region in available:
        print(f"\n── {rshort(region)} ──")

        try:
            fc_df = _load_forecast_region(fc_path, region)
        except RuntimeError as e:
            print(f"  ✗ {e}"); coverage_notes[region] = "load error"; continue

        print(f"  Forecast rows: {len(fc_df):,}")

        decisions = build_day_ahead_decisions(fc_df, region)
        del fc_df; gc.collect()

        if decisions.empty:
            print(f"  ⚠ No decisions"); coverage_notes[region] = "no decisions"; continue

        n_actual = df_5min[df_5min["region"] == region]["date"].nunique()
        coverage = len(decisions) / n_actual if n_actual > 0 else 0
        print(f"  Days with forecast: {len(decisions):,}/{n_actual}  "
              f"({coverage:.0%})  mean horizon: {decisions['horizon_h'].mean():.1f}h")

        if coverage < MIN_FORECAST_COVERAGE:
            print(f"  ⚠ Below coverage threshold — excluding")
            coverage_notes[region] = f"low coverage ({coverage:.0%})"
            continue

        coverage_notes[region] = f"{coverage:.0%} day coverage, " \
                                  f"mean horizon {decisions['horizon_h'].mean():.1f}h"

        result = evaluate_decisions(df_5min, decisions, region)
        if result.empty:
            print(f"  ⚠ No matched days"); continue

        print(f"  ✓ {len(result):,} matched days  "
              f"mean forecast savings: {result['savings_forecast'].mean():.1f}%")
        all_results.append(result)

    if not all_results:
        print("\n  ✗ No results from any region."); return

    sim_df = pd.concat(all_results, ignore_index=True)
    print(f"\n  Total region-days: {len(sim_df):,}")

    summary = build_summary(sim_df, coverage_notes)
    print("\n" + summary[["Region", "N Days", "Forecast Savings (%)",
                           "Optimal Savings (%)",
                           "Capture Rate (%)", "Mean Horizon (h)",
                           "Forecast MAE (lbs/MWh)"]].to_string(index=False))

    save_table(summary, "table_forecast_eval_summary",
               caption="Day-Ahead Forecast Scheduling: Savings by Region")
    sim_df.to_csv(TABLES_DIR / "table_forecast_eval_days.csv", index=False)
    print(f"  💾 table_forecast_eval_days.csv")

    plot_savings_comparison(summary)
    plot_capture_rate(summary)
    plot_error_dist(sim_df)

    record_number(SECTION_TAG, "Regions evaluated", len(sim_df["region"].unique()))
    record_number(SECTION_TAG, "Overall mean forecast savings %",
                  float(sim_df["savings_forecast"].mean()), ".1f")
    record_number(SECTION_TAG, "Overall mean capture rate %",
                  float(np.clip(sim_df["capture_rate"], 0, 1).mean() * 100), ".1f")

    export_numbers()
    print("\n✅ ch3_forecast_eval.py complete.")
    print("\n  Coverage notes:")
    for r in CH3_REGIONS:
        print(f"    {rshort(r):10s}: {coverage_notes.get(r, 'evaluated')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)