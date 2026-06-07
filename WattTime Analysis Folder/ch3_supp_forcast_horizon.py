"""
ch3_supp_forecast_horizon.py — Forecast horizon vs. scheduling savings.

Uses actual WattTime forecast data (point_time = target UTC,
generated_at = issue UTC, horizon_h = lead time in hours) to evaluate
how savings change as the decision lead time increases from 1h to 72h.

For each lead time L and each 5-min shift-window interval:
  - "Valid" forecasts are those issued at or before decision_time
    (decision_time = shift_start - L hours)
  - Equivalent condition: horizon_h >= (point_time - shift_start) + L
  - Among valid forecasts, take the most recent (smallest horizon_h)
  - Build forecast MOER array for the shift window
  - Select the 2h window with lowest forecast mean MOER
  - Evaluate actual MOER at that window vs. actual baseline

Performance design:
  - Forecast parquet is loaded ONCE per region using a broad horizon_h
    filter (via pyarrow predicate pushdown), then all lead times are
    processed from that single load.
  - Best-forecast selection is fully vectorized (no per-day loops during
    the forecast selection step).

Outputs (to ch3supp/):
    Tables:
        table_supp_forecast_summary.csv / .md
        table_supp_forecast_breakeven.csv / .md
    Figures:
        fig_supp_forecast_value_curve.png / .pdf
"""

import argparse
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import pyarrow.parquet as pq
import pyarrow.compute as pc
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci, compute_thresholds,
    get_run_dir,
    CH3_REGIONS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rshort, rcolor, rmarker,
    save_cache, load_cache,
)
from config import REGIONS as ALL_REGIONS

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
LEAD_TIMES_HOURS = [1, 2, 4, 6, 8, 12, 24]

# Shift window duration (hours) — used to bound the horizon filter
SHIFT_DURATION_H = DAY_SHIFT_END - DAY_SHIFT_START   # 12h

# Horizon filter: load rows with horizon_h in [MIN_HORIZON, MAX_HORIZON].
# MIN_HORIZON = smallest lead time (1h).
# MAX_HORIZON = largest lead time + shift duration + small buffer.
# This covers all lead times in a single regional load.
HORIZON_MIN = min(LEAD_TIMES_HOURS) - 0.1
HORIZON_MAX = max(LEAD_TIMES_HOURS) + SHIFT_DURATION_H + 1.0

# Min fraction of shift-window intervals that must have forecast coverage
MIN_COVERAGE = 0.80

CACHE_VERSION = 3

SUPP_DIR     = Path(__file__).parent / "ch3supp"
SUPP_FIGURES = SUPP_DIR / "figures"
SUPP_TABLES  = SUPP_DIR / "tables"
SUPP_NUMBERS = SUPP_DIR / "ch3_supp_numbers.md"
# ▲▲▲ END CONFIG ▲▲▲

ch3_common.FIGURES_DIR  = SUPP_FIGURES
ch3_common.TABLES_DIR   = SUPP_TABLES
ch3_common.NUMBERS_FILE = SUPP_NUMBERS
SUPP_FIGURES.mkdir(parents=True, exist_ok=True)
SUPP_TABLES.mkdir(parents=True, exist_ok=True)

REGION_TZ = {r: ALL_REGIONS[r]["timezone"] for r in CH3_REGIONS if r in ALL_REGIONS}


# =============================================================================
# FORECAST LOADING — once per region, all lead times
# =============================================================================

def load_forecast_region(forecast_path: Path, region: str,
                         pt_min: pd.Timestamp,
                         pt_max: pd.Timestamp) -> pd.DataFrame:
    """
    Load forecast rows for one region using pyarrow predicate pushdown on:
      - region
      - horizon_h in [HORIZON_MIN, HORIZON_MAX]
      - point_time in [pt_min - buffer, pt_max]

    Returns a DataFrame with UTC-aware point_time and generated_at.
    """
    buffer = pd.Timedelta(hours=HORIZON_MAX + 1)

    # Only filter by region in pyarrow — horizon_h lacks row-group stats
    # for predicate pushdown. horizon_h and point_time filtered in pandas.
    filters = [("region", "=", region)]
    try:
        table = pq.read_table(
            forecast_path,
            columns=["point_time", "generated_at", "value"],
            filters=filters,
        )
    except Exception as e:
        raise RuntimeError(
            f"pyarrow region filter failed for '{region}': {e}"
        ) from e

    df = table.to_pandas()
    del table

    df["point_time"]   = pd.to_datetime(df["point_time"],   utc=True)
    df["generated_at"] = pd.to_datetime(df["generated_at"], utc=True)
    df["value"]        = df["value"].astype("float32")

    # Compute horizon_h from timestamps, then filter to needed range
    df["horizon_h"] = (
        (df["point_time"] - df["generated_at"]).dt.total_seconds() / 3600
    ).astype("float32")
    df = df[(df["horizon_h"] >= HORIZON_MIN) & (df["horizon_h"] <= HORIZON_MAX)]

    # point_time range filter
    t_lo = pt_min - buffer
    df   = df[(df["point_time"] >= t_lo) & (df["point_time"] <= pt_max)]

    return df


# =============================================================================
# VECTORIZED FORECAST SELECTION
# =============================================================================

def select_best_forecast(fc_df: pd.DataFrame,
                         tz: str,
                         lead_hours: float) -> pd.DataFrame:
    """
    For a given lead time, select the best (most recent valid) forecast for
    every 5-min shift-window interval, across all days, in one vectorized pass.

    "Valid" = issued at or before decision_time = shift_start - lead_hours.
    Equivalent horizon condition: horizon_h >= (point_time - shift_start) + lead_hours

    Returns DataFrame with columns [point_time_local (naive), fc_value].
    """
    fc = fc_df.copy()

    # Convert UTC point_time to local tz-aware, then to naive for easy ops
    fc["pt_local"] = fc["point_time"].dt.tz_convert(tz)

    # Keep only shift-window target times
    h = fc["pt_local"].dt.hour
    fc = fc[(h >= DAY_SHIFT_START) & (h < DAY_SHIFT_END)].copy()
    if len(fc) == 0:
        return pd.DataFrame(columns=["point_time_local", "fc_value"])

    # Shift start for each row's local date (vectorized)
    # normalize() → midnight in local tz, then add shift_start offset
    fc["shift_start_local"] = (
        fc["pt_local"].dt.normalize()
        + pd.Timedelta(hours=DAY_SHIFT_START)
    )
    fc["shift_start_utc"] = fc["shift_start_local"].dt.tz_convert("UTC")

    # Minimum acceptable horizon for this row given lead_hours
    offset_h = (fc["point_time"] - fc["shift_start_utc"]).dt.total_seconds() / 3600
    fc["min_horizon"] = (offset_h + lead_hours).astype("float32")

    # Keep rows where the forecast was actually available at decision_time
    fc = fc[fc["horizon_h"] >= fc["min_horizon"]]
    if len(fc) == 0:
        return pd.DataFrame(columns=["point_time_local", "fc_value"])

    # For each UTC target interval, keep the row with the smallest horizon_h
    # (most recent forecast that was still available at decision_time)
    idx_min  = fc.groupby("point_time")["horizon_h"].idxmin()
    fc_best  = fc.loc[idx_min][["pt_local", "value"]].copy()
    fc_best["pt_local_naive"] = fc_best["pt_local"].dt.tz_localize(None)
    fc_best = fc_best.rename(columns={"value": "fc_value"})

    return fc_best[["pt_local_naive", "fc_value"]]


# =============================================================================
# SIMULATION
# =============================================================================

def run_forecast_sim_region(actuals_window: pd.DataFrame,
                             fc_best: pd.DataFrame,
                             thresholds: pd.DataFrame,
                             region: str,
                             lead_hours: float) -> list:
    """
    For one (region, lead_time): merge forecast values onto actuals,
    then run per-day simulation. Returns list of result dicts.
    """
    if fc_best is None or len(fc_best) == 0:
        return []

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td  = {r["region"]: (r["green_threshold"], r["red_threshold"])
           for _, r in thresholds.iterrows()}
    gt, rt = td.get(region, (np.inf, np.inf))

    rd = actuals_window[actuals_window["region"] == region].copy()
    rd = rd.sort_values("point_time_local")

    # Merge forecast values onto actuals
    rd = rd.merge(
        fc_best.rename(columns={"pt_local_naive": "point_time_local"}),
        on="point_time_local",
        how="left",
    )

    results = []
    for date, ddf in rd.groupby("date"):
        actual_vals = ddf["value"].values
        fc_vals     = ddf["fc_value"].values.astype("float64")

        if len(actual_vals) < job_intervals:
            continue

        # Coverage check
        coverage = np.mean(~np.isnan(fc_vals))
        if coverage < MIN_COVERAGE:
            continue

        # Fill NaN gaps (DST edges, occasional missing intervals)
        if np.any(np.isnan(fc_vals)):
            fc_s = pd.Series(fc_vals).ffill().bfill()
            fc_vals = fc_s.values

        sim = simulate_day(actual_vals, job_intervals, gt, rt)
        if sim is None or sim["baseline_moer"] <= 0:
            continue

        baseline = sim["baseline_moer"]
        optimal  = sim["optimal_moer"]

        # Best 2h window by forecast
        n_win = len(fc_vals) - job_intervals + 1
        if n_win <= 0:
            continue
        cs       = np.concatenate([[0], np.cumsum(fc_vals)])
        fc_wm    = (cs[job_intervals:] - cs[:n_win]) / job_intervals
        best_idx = int(np.argmin(fc_wm))

        if best_idx + job_intervals > len(actual_vals):
            continue

        actual_moer = float(np.mean(actual_vals[best_idx: best_idx + job_intervals]))
        savings     = (baseline - actual_moer) / baseline * 100
        capture     = ((baseline - actual_moer) / (baseline - optimal) * 100
                       if (baseline - optimal) > 0 else 100.0)

        # MAE between forecast and actual MOER across the full shift window
        # (not just the selected window) — measures forecast accuracy directly
        n_common = min(len(fc_vals), len(actual_vals))
        mae      = float(np.mean(np.abs(fc_vals[:n_common] - actual_vals[:n_common])))

        # Also compute MAE just for the selected 2h window
        fc_window     = fc_vals[best_idx: best_idx + job_intervals]
        actual_window = actual_vals[best_idx: best_idx + job_intervals]
        mae_window    = float(np.mean(np.abs(fc_window - actual_window)))

        # Regret: how much worse is forecast-selected window vs actual optimal?
        # = 0 when forecast picks the right window; rises as forecast degrades
        regret     = actual_moer - optimal
        regret_pct = regret / baseline * 100 if baseline > 0 else 0.0

        results.append({
            "region":        region,
            "date":          date,
            "year":          ddf["year"].iloc[0],
            "season":        ddf["season"].iloc[0],
            "lead_hours":    lead_hours,
            "baseline_moer": baseline,
            "optimal_moer":  optimal,
            "forecast_moer": actual_moer,
            "savings_pct":   savings,
            "capture_rate":  capture,
            "mae_shift":     mae,
            "mae_window":    mae_window,
            "regret":        regret,      # lbs/MWh above optimal
            "regret_pct":    regret_pct,  # % of baseline
        })
    return results


def run_all_simulations(df_5min: pd.DataFrame,
                        forecast_path: Path,
                        thresholds: pd.DataFrame,
                        recompute: bool = False) -> pd.DataFrame:
    """
    Outer loop: one region at a time. For each region:
      1. Load forecast rows once (broad horizon_h filter).
      2. For each lead time: vectorized selection + simulation.
      3. Cache per (region, lead_time).
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].sort_values("point_time_local")

    # UTC time range for forecast loading
    all_dates = window["date"].dropna().unique()
    pt_min    = pd.Timestamp(str(all_dates.min())).tz_localize("UTC")
    pt_max    = pd.Timestamp(str(all_dates.max())).tz_localize("UTC") + pd.Timedelta(days=1)

    all_results = []

    for region in CH3_REGIONS:
        tz = REGION_TZ.get(region)
        if tz is None:
            print(f"  ⚠️  No timezone for {region}")
            continue

        # Check if all lead times for this region are already cached
        all_cached = []
        if not recompute:
            for lead_hours in LEAD_TIMES_HOURS:
                tag    = f"supp_fcast_v4_{region}_{int(lead_hours)}h"
                cached = load_cache(tag, {"v": CACHE_VERSION})
                if cached is not None:
                    all_cached.append(cached)
            if len(all_cached) == len(LEAD_TIMES_HOURS):
                print(f"  {rshort(region):10s}  all lead times cached")
                all_results.extend(all_cached)
                continue

        # Load forecast once for this region
        print(f"\n  {rshort(region):10s}  loading forecast "
              f"(horizon {HORIZON_MIN:.0f}–{HORIZON_MAX:.0f}h)...")
        try:
            fc_df = load_forecast_region(forecast_path, region, pt_min, pt_max)
        except Exception as e:
            print(f"    ⚠️  Load failed: {e}")
            continue
        print(f"    {len(fc_df):,} rows loaded")

        if len(fc_df) == 0:
            print(f"    ⚠️  No forecast rows after filtering — skipping region")
            continue

        max_horizon = float(fc_df["horizon_h"].max())
        print(f"    Max available horizon: {max_horizon:.1f}h")

        actuals_region = window[window["region"] == region]

        for lead_hours in LEAD_TIMES_HOURS:
            if lead_hours >= max_horizon:
                print(f"    {lead_hours}h  skipped (exceeds max horizon {max_horizon:.0f}h)")
                continue
            tag    = f"supp_fcast_v4_{region}_{int(lead_hours)}h"
            params = {"v": CACHE_VERSION}

            if not recompute:
                cached = load_cache(tag, params)
                if cached is not None:
                    print(f"    {lead_hours}h  cached ({len(cached)} days)")
                    all_results.append(cached)
                    continue

            print(f"    {lead_hours}h  selecting forecasts...", end=" ", flush=True)
            fc_best = select_best_forecast(fc_df, tz, lead_hours)
            print(f"{len(fc_best):,} intervals covered", end=" | ", flush=True)

            results = run_forecast_sim_region(
                actuals_region, fc_best, thresholds, region, lead_hours
            )
            print(f"{len(results)} days simulated")

            if results:
                df_r = pd.DataFrame(results)
                save_cache(df_r, tag, params)
                all_results.append(df_r)

        del fc_df   # release memory before next region

    return pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()


# =============================================================================
# SEASONAL TOD REFERENCE
# =============================================================================

def compute_seasonal_tod_savings(df_5min: pd.DataFrame,
                                 thresholds: pd.DataFrame) -> dict:
    print("\n── Seasonal TOD reference savings ──")
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    tod_savings = {}
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        seasonal_best = {}
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                continue
            hm = sd.groupby("hour")["value"].mean()
            seasonal_best[season] = int(hm.idxmin())

        daily = []
        gt, rt = td.get(region, (np.inf, np.inf))
        for date, ddf in rd.groupby("date"):
            vals   = ddf.sort_values("point_time_local")["value"].values
            season = ddf["season"].iloc[0]
            bh     = seasonal_best.get(season)
            if bh is None or len(vals) < job_intervals:
                continue
            idx = (bh - DAY_SHIFT_START) * INTERVALS_PER_HOUR
            if idx + job_intervals > len(vals):
                continue
            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None or sim["baseline_moer"] <= 0:
                continue
            m_tod   = float(np.mean(vals[idx: idx + job_intervals]))
            daily.append((sim["baseline_moer"] - m_tod) / sim["baseline_moer"] * 100)

        tod_savings[region] = float(np.mean(daily)) if daily else np.nan
        print(f"  {rshort(region):10s}  {tod_savings[region]:.1f}%")

    return tod_savings


def compute_optimal_refs(df_5min: pd.DataFrame,
                         thresholds: pd.DataFrame) -> dict:
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]
    refs = {}
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        gt, rt = td.get(region, (np.inf, np.inf))
        opt = []
        for date, ddf in rd.groupby("date"):
            vals = ddf.sort_values("point_time_local")["value"].values
            sim  = simulate_day(vals, job_intervals, gt, rt)
            if sim is None or sim["baseline_moer"] <= 0:
                continue
            opt.append(
                (sim["baseline_moer"] - sim["optimal_moer"])
                / sim["baseline_moer"] * 100
            )
        refs[region] = float(np.mean(opt)) if opt else np.nan
    return refs


# =============================================================================
# AGGREGATION + BREAK-EVEN
# =============================================================================

def aggregate_results(all_sim: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        for lead_hours in LEAD_TIMES_HOURS:
            sub = all_sim[
                (all_sim["region"] == region) &
                (all_sim["lead_hours"] == lead_hours)
            ]
            if len(sub) < 10:
                continue
            sv       = sub["savings_pct"].values
            cap      = sub["capture_rate"].values
            mae_s    = sub["mae_shift"].values    if "mae_shift"  in sub.columns else np.array([np.nan])
            mae_w    = sub["mae_window"].values   if "mae_window" in sub.columns else np.array([np.nan])
            reg      = sub["regret"].values       if "regret"     in sub.columns else np.array([np.nan])
            reg_pct  = sub["regret_pct"].values   if "regret_pct" in sub.columns else np.array([np.nan])
            lo, hi         = bootstrap_ci(sv)
            mae_lo, mae_hi = bootstrap_ci(mae_s)
            reg_lo, reg_hi = bootstrap_ci(reg)
            rows.append({
                "region":          region,
                "region_short":    rshort(region),
                "lead_hours":      lead_hours,
                "mean_savings":    float(np.mean(sv)),
                "ci_lo":           lo,
                "ci_hi":           hi,
                "mean_capture":    float(np.mean(cap)),
                "mean_mae_shift":  float(np.mean(mae_s)),
                "mae_ci_lo":       mae_lo,
                "mae_ci_hi":       mae_hi,
                "mean_mae_window": float(np.mean(mae_w)),
                "mean_regret":     float(np.mean(reg)),
                "regret_ci_lo":    reg_lo,
                "regret_ci_hi":    reg_hi,
                "mean_regret_pct": float(np.mean(reg_pct)),
                "n_days":          len(sub),
            })
    return pd.DataFrame(rows)


def find_breakeven_horizons(agg: pd.DataFrame,
                            tod_ref: dict) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        tod     = tod_ref.get(region, np.nan)
        rd      = agg[agg["region"] == region].sort_values("lead_hours")
        breakeven = np.nan
        for _, row in rd.iterrows():
            if row["mean_savings"] >= tod:
                breakeven = row["lead_hours"]
                break
        rows.append({
            "region":           region,
            "region_short":     rshort(region),
            "seasonal_tod_pct": tod,
            "breakeven_hours":  breakeven,
        })
    return pd.DataFrame(rows)


# =============================================================================
# FIGURE
# =============================================================================

def plot_forecast_value_curve(agg: pd.DataFrame, *args, **kwargs):
    """
    Two-panel figure.
    Panel A (primary): Scheduling regret = actual MOER at forecast-selected window
                       minus actual optimal MOER. Zero = perfect window selection.
                       Rising regret at longer lead times shows forecast degradation.
    Panel B (secondary): Raw MAE for reference.

    x-axis: lead time, longest on left, shortest on right.
    """
    print("\n── Fig: Scheduling regret + MAE vs lead time ──")

    available = sorted(agg["lead_hours"].unique(), reverse=True)

    has_regret = "mean_regret" in agg.columns and agg["mean_regret"].notna().any()
    has_mae    = "mean_mae_shift" in agg.columns and agg["mean_mae_shift"].notna().any()

    ncols = 2 if (has_regret and has_mae) else 1
    with thesis_style():
        fig, axes = plt.subplots(1, ncols, figsize=(9 * ncols, 5.5))
        if ncols == 1:
            axes = [axes]
        ax_reg = axes[0]
        ax_mae = axes[1] if ncols == 2 else None

        for region in CH3_REGIONS:
            rd  = (agg[agg["region"] == region]
                   .sort_values("lead_hours", ascending=False)
                   .set_index("lead_hours")
                   .reindex(available))
            col  = rcolor(region)
            mark = rmarker(region)
            lbl  = rshort(region)
            x    = available

            if has_regret:
                y   = rd["mean_regret"].values
                lo  = rd["regret_ci_lo"].values
                hi  = rd["regret_ci_hi"].values
                ax_reg.plot(x, y, color=col, marker=mark, markersize=7,
                            linewidth=2, label=lbl, zorder=3)
                ax_reg.fill_between(x, lo, hi, color=col, alpha=0.12, zorder=2)

            if has_mae and ax_mae is not None:
                y2  = rd["mean_mae_shift"].values
                lo2 = rd["mae_ci_lo"].values
                hi2 = rd["mae_ci_hi"].values
                ax_mae.plot(x, y2, color=col, marker=mark, markersize=7,
                            linewidth=2, label=lbl, zorder=3)
                ax_mae.fill_between(x, lo2, hi2, color=col, alpha=0.12, zorder=2)

        x_pad = (available[0] - available[-1]) * 0.08
        for ax in axes:
            ax.set_xlim(available[0] + x_pad, available[-1] - x_pad)
            ax.set_xticks(available)
            ax.set_xticklabels([f"{h}h" for h in available])
            ax.set_xlabel("Forecast Lead Time (hours ahead)")
            ax.legend(fontsize=9, loc="upper left")

        if has_regret:
            ax_reg.axhline(0, color="black", linewidth=0.7)
            ax_reg.set_ylabel(f"Scheduling Regret ({SIGNAL_UNIT})")
            ax_reg.set_title(
                "Scheduling Regret vs. Lead Time\n"
                "(Forecast-selected window minus actual optimal; 0 = perfect)"
            )

        if has_mae and ax_mae is not None:
            ax_mae.set_ylabel(f"MAE: Forecast vs Actual MOER ({SIGNAL_UNIT})")
            ax_mae.set_title("Forecast MAE vs. Lead Time")

        fig.suptitle(
            "Forecast Quality and Scheduling Value vs. Lead Time\n"
            "95% CI shaded; longer lead time on left",
            fontsize=11
        )
        fig.tight_layout()
        save_fig(fig, "fig_supp_forecast_value_curve")



# =============================================================================
# TABLES + NUMBERS
# =============================================================================

def build_summary_table(agg, optimal_ref, tod_ref):
    rows = []
    for region in CH3_REGIONS:
        opt = optimal_ref.get(region, np.nan)
        tod = tod_ref.get(region, np.nan)
        for lead_hours in LEAD_TIMES_HOURS:
            sub = agg[(agg["region"] == region) & (agg["lead_hours"] == lead_hours)]
            if len(sub) == 0:
                continue
            rows.append({
                "region":          rshort(region),
                "lead_hours":      lead_hours,
                "savings_pct":     round(sub["mean_savings"].values[0], 1),
                "ci_lo":           round(sub["ci_lo"].values[0], 1),
                "ci_hi":           round(sub["ci_hi"].values[0], 1),
                "capture_rate":    round(sub["mean_capture"].values[0], 1),
                "seasonal_tod":    round(tod, 1) if not np.isnan(tod) else "",
                "optimal_ceiling": round(opt, 1) if not np.isnan(opt) else "",
                "n_days":          sub["n_days"].values[0],
            })
    return pd.DataFrame(rows)


def record_key_numbers(agg, tod_ref, breakeven):
    sec = "Supp: Forecast Horizon"
    for region in CH3_REGIONS:
        s = rshort(region)
        for lh in [1, 24]:
            sub = agg[(agg["region"] == region) & (agg["lead_hours"] == lh)]
            if len(sub):
                record_number(sec, f"{s} savings @ {lh}h lead",
                              sub["mean_savings"].values[0], ".1f")
        tod = tod_ref.get(region, np.nan)
        if not np.isnan(tod):
            record_number(sec, f"{s} seasonal TOD ref", tod, ".1f")
        be = breakeven.loc[breakeven["region"] == region, "breakeven_hours"]
        if len(be) and not np.isnan(be.values[0]):
            record_number(sec, f"{s} break-even (h)", be.values[0], ".0f")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Forecast Horizon vs. Scheduling Savings")
    print(f"  Lead times: {LEAD_TIMES_HOURS}h")
    print(f"  Horizon filter: {HORIZON_MIN:.0f}–{HORIZON_MAX:.0f}h  |  Lead times: {LEAD_TIMES_HOURS}h")
    print("="*60)

    forecast_path = get_run_dir() / "processed" / "data_forecast.parquet"
    if not forecast_path.exists():
        raise FileNotFoundError(f"Forecast parquet not found: {forecast_path}")

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)
    tod_ref    = compute_seasonal_tod_savings(df_5min, thresholds)
    optimal_ref = compute_optimal_refs(df_5min, thresholds)

    print("\n── Running simulations ──")
    all_sim = run_all_simulations(df_5min, forecast_path, thresholds,
                                  recompute=recompute)

    if len(all_sim) == 0:
        print("⚠️  No simulation results — check forecast data coverage.")
        return

    print(f"\n  Total region-days: {len(all_sim):,}")

    agg       = aggregate_results(all_sim)
    breakeven = find_breakeven_horizons(agg, tod_ref)

    print("\nBreak-even horizons:")
    print(breakeven[["region_short","seasonal_tod_pct","breakeven_hours"]].to_string(index=False))

    summary = build_summary_table(agg, optimal_ref, tod_ref)
    save_table(summary, "table_supp_forecast_summary",
               caption=(
                   "Mean forecast scheduling savings and capture rate by archetype "
                   "and lead time. Capture rate = (baseline - forecast_selected) / "
                   "(baseline - optimal) * 100. Seasonal TOD = calendar-based "
                   "reference savings. Optimal = perfect foresight ceiling."
               ))
    save_table(breakeven.round(2), "table_supp_forecast_breakeven",
               caption=(
                   "Break-even forecast horizon per archetype: shortest lead time "
                   "where forecast savings exceed seasonal TOD savings."
               ))

    plot_forecast_value_curve(agg)

    record_key_numbers(agg, tod_ref, breakeven)
    export_numbers()

    print("\n✅ ch3_supp_forecast_horizon complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)