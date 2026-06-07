"""
ch3_supp_green_windows.py — Green window frequency and inter-arrival (Section 2.3).

Characterizes how often green windows occur, gap between them, and explains
the ERCOT backfire mechanistically via a duration-filtered trigger.

Outputs (ch3supp/):
    Tables:
        table_supp_gw_daily_stats.csv / .md
        table_supp_gw_second_chance.csv / .md
    Figures:
        fig_supp_gw_daily_count.png / .pdf
        fig_supp_gw_start_hours.png / .pdf
        fig_supp_gw_ercot_filter.png / .pdf

Usage:
    python ch3_supp_green_windows.py
    python ch3_supp_green_windows.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci, compute_thresholds,
    CH3_REGIONS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    rshort, rcolor, rmarker,
    save_cache, load_cache,
)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
ERCOT_REGION     = "ERCOT_NORTHCENTRAL"
SECOND_CHANCE_WINDOWS = [1, 2, 4]   # hours to look for next window
CACHE_VERSION    = 1

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
# GREEN WINDOW IDENTIFICATION
# =============================================================================

def identify_windows(vals, green_threshold, shift_start=DAY_SHIFT_START):
    """
    Find contiguous green intervals in vals (5-min resolution, shift window).
    Returns list of dicts: {start_idx, end_idx, duration_intervals, start_hour}
    """
    windows = []
    n = len(vals)
    i = 0
    while i < n:
        if vals[i] <= green_threshold:
            j = i
            while j < n and vals[j] <= green_threshold:
                j += 1
            duration = j - i
            start_hour = shift_start + i / INTERVALS_PER_HOUR
            windows.append({
                "start_idx":          i,
                "end_idx":            j - 1,
                "duration_intervals": duration,
                "duration_min":       duration * 5,
                "start_hour":         start_hour,
            })
            i = j
        else:
            i += 1
    return windows


# =============================================================================
# DAILY STATISTICS AND SECOND CHANCE
# =============================================================================

def compute_green_window_stats(df_5min, thresholds, recompute=False):
    cache_tag    = "supp_gw_stats"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    td = {r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()}
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    daily_rows  = []
    detail_rows = []   # one row per window instance

    for region in CH3_REGIONS:
        gt = td.get(region, np.inf)
        rd = window[window["region"] == region].sort_values("point_time_local")

        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            wins = identify_windows(vals, gt)
            n_wins = len(wins)

            daily_rows.append({
                "region":       region,
                "region_short": rshort(region),
                "date":         date,
                "n_windows":    n_wins,
                "has_any":      n_wins > 0,
            })

            for w in wins:
                detail_rows.append({
                    "region":      region,
                    "date":        date,
                    "start_hour":  w["start_hour"],
                    "duration_min": w["duration_min"],
                })

    daily_df  = pd.DataFrame(daily_rows)
    detail_df = pd.DataFrame(detail_rows)
    result    = {"daily": daily_df, "detail": detail_df}
    save_cache(daily_df, cache_tag, cache_params)
    save_cache(detail_df, cache_tag + "_detail", cache_params)
    return result


def compute_second_chance(daily_df, detail_df, thresholds):
    """
    For days with at least one green window, what is the probability that
    another window of at least 30 minutes starts within N hours of the first?
    """
    td  = {r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()}
    rows = []
    for region in CH3_REGIONS:
        days_with_window = daily_df[
            (daily_df["region"] == region) & (daily_df["n_windows"] >= 1)
        ]["date"].values

        region_detail = detail_df[detail_df["region"] == region]

        for horizon_h in SECOND_CHANCE_WINDOWS:
            count_success = 0
            for date in days_with_window:
                day_wins = region_detail[region_detail["date"] == date]
                if len(day_wins) == 0:
                    continue
                first_end_h = (day_wins["start_hour"].min() +
                               day_wins.loc[day_wins["start_hour"].idxmin(),
                                           "duration_min"] / 60)
                later_wins = day_wins[
                    (day_wins["start_hour"] > first_end_h) &
                    (day_wins["start_hour"] <= first_end_h + horizon_h) &
                    (day_wins["duration_min"] >= 30)
                ]
                if len(later_wins) > 0:
                    count_success += 1

            rows.append({
                "region":          region,
                "region_short":    rshort(region),
                "horizon_hours":   horizon_h,
                "prob_second":     count_success / len(days_with_window)
                                   if len(days_with_window) > 0 else np.nan,
                "n_days_with_win": len(days_with_window),
            })

    return pd.DataFrame(rows)


def aggregate_daily_stats(daily_df):
    rows = []
    for region in CH3_REGIONS:
        rd = daily_df[daily_df["region"] == region]
        if len(rd) == 0:
            continue
        nc = rd["n_windows"]
        rows.append({
            "region":        region,
            "region_short":  rshort(region),
            "mean_windows":  round(float(nc.mean()), 2),
            "median_windows": float(nc.median()),
            "pct_0_windows": round((nc == 0).mean() * 100, 1),
            "pct_1_window":  round((nc == 1).mean() * 100, 1),
            "pct_2plus":     round((nc >= 2).mean() * 100, 1),
            "n_days":        len(rd),
        })
    return pd.DataFrame(rows)


# =============================================================================
# ERCOT DURATION-FILTERED TRIGGER
# =============================================================================

def ercot_duration_filter_sim(df_5min, thresholds, recompute=False):
    """
    Compare ERCOT traffic light savings: first-green vs. duration-filtered
    (only trigger on windows with >= job_duration remaining).
    """
    cache_tag    = "supp_gw_ercot_filter"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td  = {r["region"]: (r["green_threshold"], r["red_threshold"])
           for _, r in thresholds.iterrows()}
    gt, rt = td.get(ERCOT_REGION, (np.inf, np.inf))

    window = df_5min[
        (df_5min["region"] == ERCOT_REGION) &
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    results = []
    for date, ddf in window.groupby("date"):
        vals = ddf.sort_values("point_time_local")["value"].values
        if len(vals) < job_intervals:
            continue

        sim = simulate_day(vals, job_intervals, gt, rt)
        if sim is None or sim["baseline_moer"] <= 0:
            continue

        baseline = sim["baseline_moer"]
        first_green_moer = sim["tl_first_green_moer"]

        # Duration-filtered: find first green start where the window has
        # at least job_intervals consecutive green intervals
        n_win = len(vals) - job_intervals + 1
        sm    = vals[:n_win]
        dur_filtered_moer = baseline   # fallback

        for i in range(n_win):
            if sm[i] <= gt:
                # Check if job_intervals consecutive green from this start
                if np.all(vals[i: i + job_intervals] <= gt):
                    dur_filtered_moer = float(np.mean(vals[i: i + job_intervals]))
                    break

        def sv(m): return (baseline - m) / baseline * 100

        results.append({
            "date":                date,
            "baseline_moer":       baseline,
            "first_green_savings": sv(first_green_moer),
            "dur_filtered_savings": sv(dur_filtered_moer),
        })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, cache_params)
    return df


# =============================================================================
# FIGURES
# =============================================================================

def plot_daily_count(daily_df):
    print("\n── Fig: Daily green window count ──")
    regions = list(CH3_REGIONS.keys())

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        data = [daily_df[daily_df["region"] == r]["n_windows"].values
                for r in regions]
        labels = [rshort(r) for r in regions]
        colors = [rcolor(r) for r in regions]

        bp = ax.boxplot(data, labels=labels, patch_artist=True,
                        medianprops={"color": "black", "linewidth": 1.5},
                        flierprops={"marker": ".", "markersize": 3, "alpha": 0.4})
        for patch, col in zip(bp["boxes"], colors):
            patch.set_facecolor(col)
            patch.set_alpha(0.6)

        ax.set_ylabel("Daily Green Window Count (shift window)")
        ax.set_xlabel("Archetype")
        fig.suptitle("Distribution of Daily Green Window Count per Archetype", fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_gw_daily_count")


def plot_start_hours(detail_df):
    print("\n── Fig: Window start-hour distribution ──")
    regions = list(CH3_REGIONS.keys())

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(13, 8), sharey=False)
        axes = axes.flatten()

        bins = np.arange(DAY_SHIFT_START, DAY_SHIFT_END + 1)

        for ax, region in zip(axes, regions):
            rd = detail_df[detail_df["region"] == region]
            if len(rd) == 0:
                ax.set_visible(False)
                continue
            ax.hist(rd["start_hour"].values, bins=bins,
                    color=rcolor(region), alpha=0.75, edgecolor="white")
            ax.set_title(rshort(region), fontsize=11)
            ax.set_xlabel("Green Window Start Hour")
            ax.set_ylabel("Count")
            ax.set_xlim(DAY_SHIFT_START, DAY_SHIFT_END)

        fig.suptitle("Green Window Start-Hour Distribution by Archetype", fontsize=12)
        fig.tight_layout()
        save_fig(fig, "fig_supp_gw_start_hours")


def plot_ercot_filter(ercot_df):
    print("\n── Fig: ERCOT duration-filtered trigger ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(8, 5))

        lo1, hi1 = bootstrap_ci(ercot_df["first_green_savings"].values)
        lo2, hi2 = bootstrap_ci(ercot_df["dur_filtered_savings"].values)
        m1 = ercot_df["first_green_savings"].mean()
        m2 = ercot_df["dur_filtered_savings"].mean()

        bars = ax.bar(["First Green\n(standard)", "Duration-Filtered\n(sustained window)"],
                      [m1, m2],
                      color=["#2ca02c", "#0077BB"], alpha=0.8, width=0.4,
                      yerr=[[m1 - lo1, m2 - lo2], [hi1 - m1, hi2 - m2]],
                      capsize=5)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_ylabel("Mean Savings vs. Baseline (%)")
        fig.suptitle(
            f"ERCOT N-Central: First-Green vs. Duration-Filtered Trigger\n"
            f"Duration filter: only trigger on windows with full {int(REFERENCE_JOB_HOURS)}h remaining",
            fontsize=11
        )
        fig.tight_layout()
        save_fig(fig, "fig_supp_gw_ercot_filter")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Green Window Frequency and Inter-Arrival")
    print("="*60)

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)

    print("\n── Computing green window statistics ──")
    result     = compute_green_window_stats(df_5min, thresholds, recompute)

    if isinstance(result, dict):
        daily_df  = result["daily"]
        detail_df = result["detail"]
    else:
        daily_df  = result
        detail_df = load_cache("supp_gw_stats_detail", {"v": CACHE_VERSION})

    agg_daily  = aggregate_daily_stats(daily_df)
    second_ch  = compute_second_chance(daily_df, detail_df, thresholds)

    print("\n── Running ERCOT duration-filter comparison ──")
    ercot_df   = ercot_duration_filter_sim(df_5min, thresholds, recompute)

    save_table(agg_daily.round(2), "table_supp_gw_daily_stats",
               caption="Daily green window count statistics by archetype.")
    save_table(second_ch.round(3), "table_supp_gw_second_chance",
               caption=(
                   "Probability of a second green window (>=30 min) starting "
                   "within N hours of the first, given at least one window exists that day."
               ))

    plot_daily_count(daily_df)
    plot_start_hours(detail_df)
    plot_ercot_filter(ercot_df)

    sec = "Supp: Green Windows"
    for _, row in agg_daily.iterrows():
        record_number(sec, f"{row['region_short']} mean daily windows",
                      row["mean_windows"], ".2f")
        record_number(sec, f"{row['region_short']} pct days 0 windows",
                      row["pct_0_windows"], ".1f")
    if len(ercot_df) > 0:
        record_number(sec, "ERCOT first-green savings",
                      ercot_df["first_green_savings"].mean(), ".1f")
        record_number(sec, "ERCOT duration-filtered savings",
                      ercot_df["dur_filtered_savings"].mean(), ".1f")
    export_numbers()
    print("\n✅ ch3_supp_green_windows complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
