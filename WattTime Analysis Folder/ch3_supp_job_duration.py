"""
ch3_supp_job_duration.py — Scheduling savings as a function of job duration.

Quantifies how carbon savings decay as job duration increases, across all six
grid archetypes and four scheduling heuristics. The key practical question:
at what job length does scheduling stop being worthwhile?

Durations evaluated: 0.25, 0.5, 1, 2 (thesis baseline), 4 hours.

Design notes:
  - Thresholds (P25/P75) computed once from full-period operating-window data,
    consistent with the main thesis simulation.
  - Best hours (annual + seasonal TOD) recomputed per duration: a 15-min job
    may have a different optimal start hour than a 4-hour job.
  - Traffic light uses the fixed threshold but fires a job of length d.
  - Forecast = perfect oracle (lowest d-minute window, actuals).
  - "Best practical" = max savings among annual_tod, seasonal_tod, traffic_light
    (excludes oracle, which is not actionable).

Outputs:
    Tables:
        table_supp_duration_savings.csv / .md
        table_supp_duration_crossover.csv / .md   (2% threshold + ERCOT TL zero-crossing)
    Figures:
        fig_supp_duration_main.png / .pdf          (savings decay curves, all archetypes)
        fig_supp_duration_ercot.png / .pdf         (ERCOT detail: all heuristics)

Usage:
    python ch3_supp_job_duration.py
    python ch3_supp_job_duration.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci, compute_thresholds,
    CH3_REGIONS, REGION_COLORS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    save_cache, load_cache,
)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
JOB_DURATIONS_HOURS = [0.25, 0.5, 1.0, 2.0, 3.0, 4.0]   # hours
ERCOT_REGION        = "ERCOT_NORTHCENTRAL"

METHODS = ["annual_tod", "seasonal_tod", "traffic_light", "forecast"]
METHOD_LABELS = {
    "annual_tod":    "Annual TOD",
    "seasonal_tod":  "Seasonal TOD",
    "traffic_light": "Traffic Light",
    "forecast":      "Forecast",
}
METHOD_COLORS = {
    "annual_tod":    "#0077BB",
    "seasonal_tod":  "#EE7733",
    "traffic_light": "#2ca02c",
    "forecast":      "#AA3377",
}

CACHE_VERSION = 1

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


# =============================================================================
# PARAMETER COMPUTATION PER DURATION
# =============================================================================

def compute_best_hours(df_5min: pd.DataFrame, job_hours: float) -> dict:
    """
    For each region, find the shift-window hour that minimizes mean MOER
    over a job of length job_hours.

    Returns dict: region -> {annual_best_hour, seasonal_best_hours}

    The best hour is evaluated by aligning to hour boundaries within the valid
    start range [shift_start, shift_end - job_hours).
    """
    job_intervals = int(job_hours * INTERVALS_PER_HOUR)
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]
    # Last valid start hour: must fit entirely within shift
    max_start_hour = DAY_SHIFT_END - job_hours   # e.g. 4h job: last start = 14:00

    result = {}
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        if len(rd) == 0:
            continue

        # For each day, compute rolling mean starting at each hour-aligned index,
        # then average across all days to get a mean profile
        hour_savings = {}
        for date, ddf in rd.groupby("date"):
            vals = ddf.sort_values("point_time_local")["value"].values
            if len(vals) < job_intervals:
                continue
            for h in range(DAY_SHIFT_START, int(max_start_hour) + 1):
                idx = (h - DAY_SHIFT_START) * INTERVALS_PER_HOUR
                if idx + job_intervals > len(vals):
                    continue
                w = float(np.mean(vals[idx: idx + job_intervals]))
                hour_savings.setdefault(h, []).append(w)

        if not hour_savings:
            continue

        hour_means = {h: np.mean(v) for h, v in hour_savings.items()}
        annual_best = min(hour_means, key=hour_means.get)

        seasonal_best = {}
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                seasonal_best[season] = annual_best
                continue
            sh_savings = {}
            for date, ddf in sd.groupby("date"):
                vals = ddf.sort_values("point_time_local")["value"].values
                if len(vals) < job_intervals:
                    continue
                for h in range(DAY_SHIFT_START, int(max_start_hour) + 1):
                    idx = (h - DAY_SHIFT_START) * INTERVALS_PER_HOUR
                    if idx + job_intervals > len(vals):
                        continue
                    w = float(np.mean(vals[idx: idx + job_intervals]))
                    sh_savings.setdefault(h, []).append(w)
            if sh_savings:
                sh_means = {h: np.mean(v) for h, v in sh_savings.items()}
                seasonal_best[season] = min(sh_means, key=sh_means.get)
            else:
                seasonal_best[season] = annual_best

        result[region] = {
            "annual_best_hour":    annual_best,
            "seasonal_best_hours": seasonal_best,
        }
    return result


def tod_moer(day_values: np.ndarray, best_hour: int,
             job_intervals: int):
    idx = (best_hour - DAY_SHIFT_START) * INTERVALS_PER_HOUR
    if idx < 0 or idx + job_intervals > len(day_values):
        return None
    return float(np.mean(day_values[idx: idx + job_intervals]))


# =============================================================================
# SIMULATION PER DURATION
# =============================================================================

def run_duration_sim(df_5min: pd.DataFrame, thresholds: pd.DataFrame,
                     job_hours: float, recompute: bool = False) -> pd.DataFrame:
    """
    Run all 4 heuristics for one job duration across all regions and days.
    Thresholds are fixed (full-period). Best hours are recomputed for job_hours.
    """
    dur_tag      = f"{int(job_hours * 60)}min"
    cache_tag    = f"supp_duration_{dur_tag}"
    cache_params = {"job_hours": job_hours, "v": CACHE_VERSION}

    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(job_hours * INTERVALS_PER_HOUR)
    tl_key        = f"tl_{TL_STRATEGY}_moer"

    # Thresholds dict: region -> (green, red)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    # Best hours for this duration
    best_hours = compute_best_hours(df_5min, job_hours)

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    results = []
    for region in CH3_REGIONS:
        if region not in td or region not in best_hours:
            continue
        gt, rt   = td[region]
        annual_h = best_hours[region]["annual_best_hour"]
        season_h = best_hours[region]["seasonal_best_hours"]

        rd = window[window["region"] == region].sort_values("point_time_local")

        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            if len(vals) < job_intervals:
                continue

            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None:
                continue

            baseline = sim["baseline_moer"]
            if baseline <= 0:
                continue

            season     = ddf["season"].iloc[0]
            sh         = season_h.get(season, annual_h)
            m_annual   = tod_moer(vals, annual_h, job_intervals) or baseline
            m_seasonal = tod_moer(vals, sh,       job_intervals) or baseline
            m_tl       = sim[tl_key]
            m_forecast = sim["optimal_moer"]

            def sv(m): return (baseline - m) / baseline * 100

            results.append({
                "region":                 region,
                "date":                   date,
                "year":                   ddf["year"].iloc[0],
                "season":                 season,
                "job_hours":              job_hours,
                "baseline_moer":          baseline,
                "savings_annual_tod":     sv(m_annual),
                "savings_seasonal_tod":   sv(m_seasonal),
                "savings_traffic_light":  sv(m_tl),
                "savings_forecast":       sv(m_forecast),
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, cache_params)
    print(f"  {dur_tag:8s}  {len(df):,} region-days")
    return df


# =============================================================================
# AGGREGATION
# =============================================================================

def aggregate_duration_results(all_sim: pd.DataFrame) -> pd.DataFrame:
    """
    Mean savings ± 95% CI per (region, job_hours, method).
    Also computes best_practical = max of tod/tl methods (not oracle).
    """
    rows = []
    practical_methods = ["annual_tod", "seasonal_tod", "traffic_light"]

    for region in CH3_REGIONS:
        for job_hours in JOB_DURATIONS_HOURS:
            sub = all_sim[
                (all_sim["region"] == region) &
                (all_sim["job_hours"] == job_hours)
            ]
            if len(sub) < 10:
                continue

            method_savings = {}
            for method in METHODS:
                col  = f"savings_{method}"
                vals = sub[col].dropna().values
                mn   = float(np.mean(vals))
                lo, hi = bootstrap_ci(vals)
                method_savings[method] = mn
                rows.append({
                    "region":       region,
                    "region_short": rshort(region),
                    "job_hours":    job_hours,
                    "method":       method,
                    "mean_savings": mn,
                    "ci_lo":        lo,
                    "ci_hi":        hi,
                    "n_days":       len(vals),
                })

            # Best practical entry
            best_method = max(practical_methods, key=lambda m: method_savings.get(m, -999))
            best_val    = method_savings.get(best_method, np.nan)
            lo, hi      = bootstrap_ci(sub[f"savings_{best_method}"].dropna().values)
            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "job_hours":    job_hours,
                "method":       "best_practical",
                "mean_savings": best_val,
                "ci_lo":        lo,
                "ci_hi":        hi,
                "n_days":       len(sub),
            })

    return pd.DataFrame(rows)


def build_summary_table(agg: pd.DataFrame) -> pd.DataFrame:
    """
    Region × duration table showing optimal %, best practical method, best practical %.
    """
    rows = []
    for region in CH3_REGIONS:
        for job_hours in JOB_DURATIONS_HOURS:
            sub = agg[(agg["region"] == region) & (agg["job_hours"] == job_hours)]
            if len(sub) == 0:
                continue

            opt_row = sub[sub["method"] == "forecast"]
            bp_row  = sub[sub["method"] == "best_practical"]

            if len(opt_row) == 0 or len(bp_row) == 0:
                continue

            # Which practical method achieved best_practical?
            practical = ["annual_tod", "seasonal_tod", "traffic_light"]
            prac_vals = {
                m: sub.loc[sub["method"] == m, "mean_savings"].values
                for m in practical
            }
            best_m = max(practical, key=lambda m: prac_vals[m][0] if len(prac_vals[m]) > 0 else -999)

            rows.append({
                "region":            rshort(region),
                "job_hours":         job_hours,
                "optimal_pct":       round(float(opt_row["mean_savings"].values[0]), 1),
                "best_practical":    METHOD_LABELS[best_m],
                "best_practical_pct": round(float(bp_row["mean_savings"].values[0]), 1),
            })

    return pd.DataFrame(rows)


# =============================================================================
# FIGURES
# =============================================================================

def plot_duration_main(agg: pd.DataFrame):
    """
    Line plot: x = job duration, y = best practical savings %.
    One line per archetype with shaded 95% CI.
    """
    print("\n── Fig: Duration savings curves (best practical) ──")
    bp = agg[agg["method"] == "best_practical"].sort_values("job_hours")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5.5))

        for region in CH3_REGIONS:
            rd   = bp[bp["region"] == region]
            if len(rd) == 0:
                continue
            x, y = rd["job_hours"].values, rd["mean_savings"].values
            lo,hi= rd["ci_lo"].values, rd["ci_hi"].values
            ax.plot(x, y, color=rcolor(region), marker=rmarker(region),
                    markersize=7, linewidth=2, label=rshort(region), zorder=3)
            ax.fill_between(x, lo, hi, color=rcolor(region), alpha=0.12, zorder=2)

        ax.axhline(0, color="black", linewidth=0.7)
        ax.set_xlabel("Job Duration (hours)")
        ax.set_ylabel("Best Practical Savings vs. Baseline (%)")
        ax.set_xticks(JOB_DURATIONS_HOURS)
        ax.set_xticklabels(["0.25h", "0.5h", "1h", "2h", "3h", "4h"])
        ax.set_xlim(0.1, 4.5)
        ax.legend(fontsize=9, loc="upper right")
        fig.suptitle(
            "Scheduling Savings vs. Job Duration\n"
            "Best practical heuristic per archetype, 95% CI shaded",
            fontsize=11
        )
        fig.tight_layout()
        save_fig(fig, "fig_supp_duration_main")


def plot_duration_by_region(agg: pd.DataFrame):
    """
    2x3 grid of panels, one per archetype.
    Each panel shows all 4 heuristics across job durations.
    """
    print("\n── Fig: Duration by region (all heuristics) ──")
    regions = list(CH3_REGIONS.keys())

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 9), sharey=False)
        axes = axes.flatten()

        for ax, region in zip(axes, regions):
            rd = agg[agg["region"] == region].sort_values("job_hours")
            if len(rd) == 0:
                ax.set_visible(False)
                continue

            for method in METHODS:
                md = rd[rd["method"] == method]
                if len(md) == 0:
                    continue
                x, y = md["job_hours"].values, md["mean_savings"].values
                lo,hi= md["ci_lo"].values, md["ci_hi"].values
                ax.plot(x, y, color=METHOD_COLORS[method], marker="o",
                        markersize=5, linewidth=1.8,
                        label=METHOD_LABELS[method])
                ax.fill_between(x, lo, hi,
                                color=METHOD_COLORS[method], alpha=0.10)

            ax.axhline(0, color="black", linewidth=0.7)
            ax.set_title(rshort(region), fontsize=11)
            ax.set_xticks(JOB_DURATIONS_HOURS)
            ax.set_xticklabels(["0.25h", "0.5h", "1h", "2h", "3h", "4h"], fontsize=7)
            ax.set_xlabel("Job Duration (hours)", fontsize=9)
            ax.set_ylabel("Savings (%)", fontsize=9)

        # Single shared legend below the grid
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=4,
                   fontsize=10, bbox_to_anchor=(0.5, -0.02))

        fig.suptitle(
            "Scheduling Savings by Job Duration and Heuristic\n"
            "All archetypes, 95% CI shaded",
            fontsize=12
        )
        fig.tight_layout(rect=[0, 0.04, 1, 1])
        save_fig(fig, "fig_supp_duration_by_region")


# =============================================================================
# RECORD KEY NUMBERS
# =============================================================================

def record_key_numbers(agg: pd.DataFrame):
    sec = "Supp: Job Duration"

    for job_hours in JOB_DURATIONS_HOURS:
        bp = agg[(agg["method"] == "best_practical") & (agg["job_hours"] == job_hours)]
        for _, row in bp.iterrows():
            record_number(sec,
                          f"{row['region_short']} best practical @ {job_hours}h",
                          row["mean_savings"], ".1f")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Job Duration Sensitivity")
    print(f"  Durations: {JOB_DURATIONS_HOURS} hours")
    print("="*60)

    df_5min = load_5min()

    # Thresholds computed once from full-period operating-window data
    print("\n── Computing thresholds (full period) ──")
    thresholds = compute_thresholds(df_5min)

    # Simulate each duration
    print("\n── Running simulations ──")
    all_frames = []
    for job_hours in JOB_DURATIONS_HOURS:
        sim = run_duration_sim(df_5min, thresholds, job_hours, recompute=recompute)
        all_frames.append(sim)

    all_sim = pd.concat(all_frames, ignore_index=True)
    print(f"\n  Total region-days: {len(all_sim):,}")

    # Aggregate
    print("\n── Aggregating ──")
    agg = aggregate_duration_results(all_sim)

    # Summary table
    summary = build_summary_table(agg)
    save_table(
        summary,
        "table_supp_duration_savings",
        caption=(
            "Mean scheduling savings by archetype and job duration. "
            "Forecast = perfect oracle (lowest d-min window). "
            "Best practical = highest savings among annual TOD, seasonal TOD, "
            "and traffic light."
        )
    )

    # Figures
    plot_duration_main(agg)
    plot_duration_by_region(agg)

    # Numbers
    record_key_numbers(agg)
    export_numbers()

    print("\n✅ ch3_supp_job_duration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true",
                        help="Ignore cached results and recompute simulations")
    args = parser.parse_args()
    main(recompute=args.recompute)