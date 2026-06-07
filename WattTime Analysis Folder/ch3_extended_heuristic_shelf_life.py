"""
ch3_extended_heuristic_shelf_life.py — How long before a scheduling rule goes stale?

Tests heuristic longevity by training thresholds on one year and evaluating
on later years. Tracks threshold drift, degradation direction, and structural breaks.

Research question:
    "If I build a scheduling rule this year, how often do I need to update it?"

Outputs:
    Figures:
        fig_ext_shelf_life_curve.png/pdf
        fig_ext_threshold_drift.png/pdf
        fig_ext_degradation_direction.png/pdf
    Tables:
        table_ext_shelf_life_matrix.csv/md

Usage:
    python ch3_extended_heuristic_shelf_life.py
    python ch3_extended_heuristic_shelf_life.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min,
    simulate_day, bootstrap_ci,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

TRAIN_YEARS = [2022, 2023, 2024]
TEST_YEARS = [2022, 2023, 2024]
ROLLING_WINDOW_DAYS = 90  # For structural break detection


# =============================================================================
# CROSS-YEAR EVALUATION
# =============================================================================

def compute_shelf_life_matrix(df_5min, recompute=False):
    """
    For each (train_year, test_year) pair:
    - Compute thresholds from train_year
    - Run TL sim on test_year with those thresholds
    - Compare to "fresh" thresholds from test_year
    """
    print("\n── Shelf life matrix ──")

    cache_tag = "ext_shelf_life"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 3})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START)
        & (df_5min["hour"] < DAY_SHIFT_END)
    ]

    results = []
    for region in CH3_REGIONS:
        rd = window[window["region"] == region].sort_values("point_time_local")
        available_years = sorted(rd["year"].unique())

        for train_year in TRAIN_YEARS:
            if train_year not in available_years:
                continue
            train_data = rd[rd["year"] == train_year]
            gt_stale = train_data["value"].quantile(GREEN_PERCENTILE / 100)
            rt_stale = train_data["value"].quantile(RED_PERCENTILE / 100)

            for test_year in TEST_YEARS:
                if test_year not in available_years:
                    continue
                test_data = rd[rd["year"] == test_year]

                # Fresh thresholds from test year
                gt_fresh = test_data["value"].quantile(GREEN_PERCENTILE / 100)
                rt_fresh = test_data["value"].quantile(RED_PERCENTILE / 100)

                stale_savings, fresh_savings = [], []
                for date, ddf in test_data.groupby("date"):
                    ddf = ddf.sort_values("point_time_local")
                    vals = ddf["value"].values
                    if len(vals) < job_intervals:
                        continue

                    sim_stale = simulate_day(vals, job_intervals, gt_stale, rt_stale)
                    sim_fresh = simulate_day(vals, job_intervals, gt_fresh, rt_fresh)
                    if sim_stale is None or sim_fresh is None:
                        continue
                    b = sim_stale["baseline_moer"]
                    if b <= 0:
                        continue

                    stale_savings.append((b - sim_stale[tl_key]) / b * 100)
                    fresh_savings.append((b - sim_fresh[tl_key]) / b * 100)

                if len(stale_savings) < 30:
                    continue

                mean_stale = np.mean(stale_savings)
                mean_fresh = np.mean(fresh_savings)
                retained = mean_stale / mean_fresh * 100 if mean_fresh > 0 else 100
                lag = test_year - train_year

                # Degradation direction: stale thresholds more conservative or aggressive?
                # Conservative: gt_stale > gt_fresh (fewer hours labeled green → missed opportunities)
                # Aggressive: gt_stale < gt_fresh (more hours labeled green → worse windows used)
                conservative = gt_stale > gt_fresh

                ci_lo, ci_hi = bootstrap_ci(np.array(stale_savings) / np.array(fresh_savings) * 100
                                            if mean_fresh > 0 else np.ones(len(stale_savings)) * 100)

                results.append({
                    "region": region, "train_year": train_year, "test_year": test_year,
                    "lag_years": lag,
                    "stale_savings_pct": mean_stale,
                    "fresh_savings_pct": mean_fresh,
                    "retained_pct": retained,
                    "retained_ci_lo": ci_lo, "retained_ci_hi": ci_hi,
                    "gt_stale": gt_stale, "rt_stale": rt_stale,
                    "gt_fresh": gt_fresh, "rt_fresh": rt_fresh,
                    "gt_drift": gt_fresh - gt_stale,
                    "rt_drift": rt_fresh - rt_stale,
                    "degradation_direction": "conservative" if conservative else "aggressive",
                    "n_days": len(stale_savings),
                })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 3})
    print(f"  ✅ Computed {len(df):,} train×test pairs")
    return df


def plot_shelf_life_curve(shelf_df):
    """Line plot: retained savings vs lag years, one line per region."""
    print("\n── Fig: Shelf life curve ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for region in CH3_REGIONS:
            rd = shelf_df[shelf_df["region"] == region]
            if len(rd) == 0:
                continue
            # Average retained across all train years for each lag
            by_lag = rd.groupby("lag_years").agg(
                retained=("retained_pct", "mean"),
                ci_lo=("retained_ci_lo", "mean"),
                ci_hi=("retained_ci_hi", "mean"),
            ).sort_index()

            ax.plot(by_lag.index, by_lag["retained"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=8, linewidth=2, label=rshort(region))
            ax.fill_between(by_lag.index, by_lag["ci_lo"], by_lag["ci_hi"],
                            color=rcolor(region), alpha=0.1)

        ax.axhline(100, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.axhline(80, color="red", linestyle=":", linewidth=0.8, alpha=0.5)
        ax.set_xlabel("Lag (years since threshold computation)")
        ax.set_ylabel("Retained Savings (% of fresh)")
        ax.set_xticks([0, 1, 2])
        ax.set_ylim(50, 115)
        ax.legend(fontsize=9)

        save_fig(fig, "fig_ext_shelf_life_curve")

    # Record numbers
    for lag in [1, 2]:
        lag_data = shelf_df[shelf_df["lag_years"] == lag]
        if len(lag_data) > 0:
            mean_ret = lag_data["retained_pct"].mean()
            record_number("Shelf life", f"Mean retained % at {lag}-year lag", mean_ret, ".0f")
            worst = lag_data.groupby("region")["retained_pct"].mean()
            record_number("Shelf life", f"Worst region at {lag}-year lag",
                          f"{rshort(worst.idxmin())} ({worst.min():.0f}%)")


def plot_threshold_drift(shelf_df):
    """Show P25/P75 thresholds by year for each region."""
    print("\n── Fig: Threshold drift ──")

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=True)
        axes = axes.flatten()

        for i, region in enumerate(CH3_REGIONS):
            ax = axes[i]
            # Get fresh thresholds by year (train_year == test_year)
            rd = shelf_df[(shelf_df["region"] == region) & (shelf_df["lag_years"] == 0)]
            if len(rd) == 0:
                ax.set_title(rshort(region))
                continue

            years = rd["train_year"].values
            gt_vals = rd["gt_fresh"].values
            rt_vals = rd["rt_fresh"].values

            ax.bar(years - 0.15, gt_vals, 0.3, color="#2ca02c", alpha=0.7, label="P25 (green)")
            ax.bar(years + 0.15, rt_vals, 0.3, color="#d62728", alpha=0.7, label="P75 (red)")

            # Annotate drift
            if len(years) >= 2:
                gt_drift = gt_vals[-1] - gt_vals[0]
                rt_drift = rt_vals[-1] - rt_vals[0]
                ax.text(0.05, 0.95, f"ΔG: {gt_drift:+.0f}\nΔR: {rt_drift:+.0f}",
                        transform=ax.transAxes, fontsize=8, va="top",
                        color="green" if gt_drift < 0 else "red")

            ax.set_title(rshort(region), fontsize=11)
            ax.set_xticks(years)
            if i >= 3:
                ax.set_xlabel("Year")
            if i % 3 == 0:
                ax.set_ylabel(f"Threshold ({SIGNAL_UNIT})")
            if i == 0:
                ax.legend(fontsize=8)

        plt.tight_layout()
        save_fig(fig, "fig_ext_threshold_drift")

    # Record drift rates
    for region in CH3_REGIONS:
        rd = shelf_df[(shelf_df["region"] == region) & (shelf_df["lag_years"] == 0)].sort_values("train_year")
        if len(rd) >= 2:
            gt_drift_per_yr = (rd["gt_fresh"].iloc[-1] - rd["gt_fresh"].iloc[0]) / (len(rd) - 1)
            record_number("Shelf life", f"{rshort(region)} P25 drift per year", gt_drift_per_yr, ".0f")


def plot_degradation_direction(shelf_df):
    """Show whether stale thresholds fail conservatively or aggressively."""
    print("\n── Fig: Degradation direction ──")

    stale_only = shelf_df[shelf_df["lag_years"] > 0]
    if len(stale_only) == 0:
        print("  ⚠️ No stale data to analyze")
        return

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        summary = stale_only.groupby("region")["degradation_direction"].apply(
            lambda x: (x == "conservative").mean() * 100
        ).reindex(CH3_REGIONS.keys())

        regions = list(CH3_REGIONS.keys())
        x = np.arange(len(regions))

        bars = ax.bar(x, summary.values, color=[rcolor(r) for r in regions], edgecolor="white")
        ax.axhline(50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("% Cases: Conservative Degradation")
        ax.set_ylim(0, 100)

        for bar, val in zip(bars, summary.values):
            label = "Safe" if val > 60 else "Mixed" if val > 40 else "Risky"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                    f"{val:.0f}%\n({label})", ha="center", fontsize=8)

        save_fig(fig, "fig_ext_degradation_direction")

    overall_conservative = (stale_only["degradation_direction"] == "conservative").mean() * 100
    record_number("Shelf life", "Overall % conservative degradation", overall_conservative, ".0f")


# =============================================================================
# STRUCTURAL BREAK DETECTION
# =============================================================================

def detect_structural_breaks(df_5min):
    """Rolling 90-day thresholds — flag >10% shifts."""
    print("\n── Structural break detection ──")

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START)
        & (df_5min["hour"] < DAY_SHIFT_END)
    ]

    breaks_found = 0
    for region in CH3_REGIONS:
        rd = window[window["region"] == region].sort_values("point_time_local")
        rd_daily = rd.groupby("date")["value"].agg(["mean", "median"]).reset_index()
        rd_daily = rd_daily.sort_values("date")

        # Rolling P25
        rolling_p25 = rd_daily["median"].rolling(ROLLING_WINDOW_DAYS, min_periods=30).quantile(0.25)
        if len(rolling_p25.dropna()) < 2:
            continue

        # Check for >10% jumps
        pct_change = rolling_p25.pct_change(periods=ROLLING_WINDOW_DAYS).abs()
        big_shifts = pct_change[pct_change > 0.10].dropna()

        if len(big_shifts) > 0:
            breaks_found += len(big_shifts)
            record_number("Shelf life", f"{rshort(region)} structural breaks detected", len(big_shifts), "d")
        else:
            record_number("Shelf life", f"{rshort(region)} structural breaks detected", 0, "d")

    record_number("Shelf life", "Total structural breaks across all regions", breaks_found, "d")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()

    shelf_df = compute_shelf_life_matrix(df_5min, recompute=recompute)
    save_table(shelf_df, "table_ext_shelf_life_matrix",
               "Heuristic shelf life: retained savings by train/test year.")

    plot_shelf_life_curve(shelf_df)
    plot_threshold_drift(shelf_df)
    plot_degradation_direction(shelf_df)
    detect_structural_breaks(df_5min)

    export_numbers()
    print("\n✅ Heuristic shelf life analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
