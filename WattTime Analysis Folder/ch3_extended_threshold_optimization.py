"""
ch3_extended_threshold_optimization.py — Is P25/P75 optimal or just a round number?

Sweeps green/red threshold percentiles to find the Pareto frontier of
carbon savings vs production feasibility. Tests binary vs ternary systems
and seasonal vs annual calibration.

Research question:
    "What's the optimal traffic light calibration, and is there a universal
    split or does each region need its own?"

Outputs:
    Figures:
        fig_ext_pareto_frontier.png/pdf
        fig_ext_threshold_heatmap.png/pdf
        fig_ext_binary_vs_ternary.png/pdf
        fig_ext_seasonal_thresholds.png/pdf
    Tables:
        table_ext_threshold_sweep.csv/md
        table_ext_threshold_optima.csv/md

Usage:
    python ch3_extended_threshold_optimization.py
    python ch3_extended_threshold_optimization.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min,
    simulate_day,
    CH3_REGIONS, REGION_COLORS, SEASON_ORDER, SEASON_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

GREEN_SWEEP = list(range(10, 55, 5))   # P10 to P50
RED_SWEEP = list(range(50, 95, 5))     # P50 to P90
BINARY_THRESHOLD_PCT = 50              # For 2-tier test

FIG_PARETO = {"figsize": (10, 5)}
FIG_HEATMAP = {"figsize": (8, 6)}
FIG_BINARY = {"figsize": (9, 5)}
FIG_SEASONAL = {"figsize": (10, 5)}


# =============================================================================
# THRESHOLD SWEEP
# =============================================================================

def run_threshold_sweep(df_5min, recompute=False):
    """
    For each (green_pct, red_pct) combination, compute:
    - Mean TL savings
    - Mean green hours per day
    - % days with contiguous green window >= job duration
    - Mean wait time to first green
    """
    print("\n── Threshold sweep ──")

    cache_tag = "ext_threshold_sweep"
    params = {"green": GREEN_SWEEP, "red": RED_SWEEP, "v": 3}
    if not recompute:
        cached = load_cache(cache_tag, params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"

    results = []
    total_combos = len(GREEN_SWEEP) * len(RED_SWEEP) * len(CH3_REGIONS)
    done = 0

    for region in CH3_REGIONS:
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")
        region_vals = rd["value"].values

        # Precompute per-day data
        day_groups = []
        for date, ddf in rd.groupby("date"):
            vals = ddf.sort_values("point_time_local")["value"].values
            if len(vals) >= job_intervals:
                day_groups.append(vals)

        for green_pct in GREEN_SWEEP:
            for red_pct in RED_SWEEP:
                if green_pct >= red_pct:
                    continue

                gt = np.percentile(region_vals, green_pct)
                rt = np.percentile(region_vals, red_pct)

                day_savings = []
                day_green_hours = []
                day_has_contiguous = []
                day_wait_intervals = []

                for vals in day_groups:
                    sim = simulate_day(vals, job_intervals, gt, rt)
                    if sim is None:
                        continue

                    baseline = sim["baseline_moer"]
                    tl_moer = sim[tl_key]
                    if baseline > 0:
                        day_savings.append((baseline - tl_moer) / baseline * 100)

                    # Green hours
                    green_mask = vals <= gt
                    day_green_hours.append(green_mask.sum() / INTERVALS_PER_HOUR)

                    # Contiguous green >= job duration
                    max_run = 0
                    current_run = 0
                    first_green_idx = None
                    for i, g in enumerate(green_mask):
                        if g:
                            current_run += 1
                            if first_green_idx is None:
                                first_green_idx = i
                            max_run = max(max_run, current_run)
                        else:
                            current_run = 0
                    day_has_contiguous.append(max_run >= job_intervals)
                    day_wait_intervals.append(first_green_idx if first_green_idx is not None else len(vals))

                if len(day_savings) < 30:
                    continue

                results.append({
                    "region": region,
                    "green_pct": green_pct,
                    "red_pct": red_pct,
                    "green_threshold": gt,
                    "red_threshold": rt,
                    "mean_savings_pct": np.mean(day_savings),
                    "mean_green_hours": np.mean(day_green_hours),
                    "pct_days_contiguous": np.mean(day_has_contiguous) * 100,
                    "mean_wait_minutes": np.mean(day_wait_intervals) * 5,
                    "n_days": len(day_savings),
                })

                done += 1
                if done % 50 == 0:
                    print(f"    {done}/{total_combos} combos...")

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, params)
    print(f"  ✅ Sweep complete: {len(df):,} valid combinations")
    return df


def plot_pareto_frontier(sweep_df):
    """Savings vs green hours/day with Pareto frontier highlighted."""
    print("\n── Fig: Pareto frontier ──")

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 9), sharex=True, sharey=True)
        axes = axes.flatten()

        for i, region in enumerate(CH3_REGIONS):
            ax = axes[i]
            rd = sweep_df[sweep_df["region"] == region]
            if len(rd) == 0:
                ax.set_title(rshort(region))
                continue

            # Scatter all combos
            sc = ax.scatter(rd["mean_green_hours"], rd["mean_savings_pct"],
                            c=rd["pct_days_contiguous"], cmap="RdYlGn",
                            vmin=0, vmax=100, s=30, alpha=0.7, edgecolor="none")

            # Highlight P25/P75
            canonical = rd[(rd["green_pct"] == GREEN_PERCENTILE) & (rd["red_pct"] == RED_PERCENTILE)]
            if len(canonical) > 0:
                ax.scatter(canonical["mean_green_hours"], canonical["mean_savings_pct"],
                           color="black", s=100, marker="*", zorder=5, label="P25/P75")

            # Pareto frontier (non-dominated points)
            sorted_rd = rd.sort_values("mean_green_hours")
            pareto_x, pareto_y = [], []
            max_sav = -1
            for _, row in sorted_rd.iterrows():
                if row["mean_savings_pct"] > max_sav:
                    max_sav = row["mean_savings_pct"]
                    pareto_x.append(row["mean_green_hours"])
                    pareto_y.append(row["mean_savings_pct"])
            ax.plot(pareto_x, pareto_y, "k--", linewidth=1, alpha=0.6)

            ax.set_title(rshort(region), fontsize=11)
            if i >= 3:
                ax.set_xlabel("Green Hours / Day")
            if i % 3 == 0:
                ax.set_ylabel("TL Savings (%)")

        # Colorbar
        cbar = fig.colorbar(sc, ax=axes, shrink=0.6, pad=0.02)
        cbar.set_label("% Days with Contiguous Green ≥ 2hr")

        save_fig(fig, "fig_ext_pareto_frontier")


def plot_threshold_heatmap(sweep_df):
    """Heatmap: green_pct × red_pct → savings for each region."""
    print("\n── Fig: Threshold heatmap ──")

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 9))
        axes = axes.flatten()

        for i, region in enumerate(CH3_REGIONS):
            ax = axes[i]
            rd = sweep_df[sweep_df["region"] == region]
            if len(rd) == 0:
                ax.set_title(rshort(region))
                continue

            pivot = rd.pivot_table(index="green_pct", columns="red_pct",
                                   values="mean_savings_pct", aggfunc="first")
            pivot = pivot.sort_index(ascending=False)

            im = ax.imshow(pivot.values, cmap="YlGnBu", aspect="auto",
                           extent=[pivot.columns.min() - 2.5, pivot.columns.max() + 2.5,
                                   pivot.index.min() - 2.5, pivot.index.max() + 2.5])

            # Mark P25/P75
            if GREEN_PERCENTILE in pivot.index and RED_PERCENTILE in pivot.columns:
                ax.plot(RED_PERCENTILE, GREEN_PERCENTILE, "r*", markersize=15, zorder=5)

            ax.set_title(rshort(region), fontsize=11)
            ax.set_xlabel("Red Percentile")
            ax.set_ylabel("Green Percentile")

        fig.colorbar(im, ax=axes, shrink=0.6, pad=0.02, label="TL Savings (%)")
        save_fig(fig, "fig_ext_threshold_heatmap")


# =============================================================================
# BINARY VS TERNARY
# =============================================================================

def compare_binary_vs_ternary(df_5min, sweep_df):
    """Compare 2-tier (green/red only) vs 3-tier (green/yellow/red)."""
    print("\n── Binary vs ternary comparison ──")

    rows = []
    for region in CH3_REGIONS:
        rd = sweep_df[sweep_df["region"] == region]
        if len(rd) == 0:
            continue

        # Ternary: P25/P75 (canonical)
        ternary = rd[(rd["green_pct"] == GREEN_PERCENTILE) & (rd["red_pct"] == RED_PERCENTILE)]
        # Binary: P50/P50 (same threshold for both)
        binary = rd[(rd["green_pct"] == BINARY_THRESHOLD_PCT) & (rd["red_pct"] == BINARY_THRESHOLD_PCT + 5)]
        # If exact binary not available, find closest
        if len(binary) == 0:
            binary = rd[rd["green_pct"] == rd["red_pct"] - 5]
            if len(binary) > 0:
                binary = binary.iloc[[0]]

        if len(ternary) > 0:
            t_sav = ternary["mean_savings_pct"].values[0]
            t_green = ternary["mean_green_hours"].values[0]
        else:
            t_sav, t_green = 0, 0

        if len(binary) > 0:
            b_sav = binary["mean_savings_pct"].values[0]
            b_green = binary["mean_green_hours"].values[0]
        else:
            b_sav, b_green = 0, 0

        improvement = t_sav - b_sav
        rows.append({
            "region": region,
            "binary_savings_pct": b_sav,
            "ternary_savings_pct": t_sav,
            "ternary_improvement_pct": improvement,
            "binary_green_hours": b_green,
            "ternary_green_hours": t_green,
        })
        record_number("Thresholds", f"{rshort(region)} ternary vs binary improvement",
                      improvement, ".2f")

    table = pd.DataFrame(rows)
    save_table(table, "table_ext_binary_vs_ternary",
               "Binary (P50 split) vs ternary (P25/P75) traffic light comparison.")
    return table


def plot_binary_vs_ternary(bin_df):
    """Grouped bar comparing binary and ternary savings."""
    print("\n── Fig: Binary vs ternary ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=FIG_BINARY["figsize"])
        regions = list(CH3_REGIONS.keys())
        x = np.arange(len(regions))
        w = 0.35

        ax.bar(x - w / 2, bin_df.set_index("region").reindex(regions)["binary_savings_pct"],
               w, label="Binary (P50)", color="#fc8d59", edgecolor="white")
        ax.bar(x + w / 2, bin_df.set_index("region").reindex(regions)["ternary_savings_pct"],
               w, label="Ternary (P25/P75)", color="#91bfdb", edgecolor="white")

        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("Mean TL Savings (%)")
        ax.legend(fontsize=10)
        ax.set_ylim(bottom=0)

        save_fig(fig, "fig_ext_binary_vs_ternary")


# =============================================================================
# SEASONAL VS ANNUAL THRESHOLDS
# =============================================================================

def compare_seasonal_vs_annual(df_5min, recompute=False):
    """Test whether seasonal recalibration of thresholds improves savings."""
    print("\n── Seasonal vs annual thresholds ──")

    cache_tag = "ext_seasonal_thresh"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"

    results = []
    for region in CH3_REGIONS:
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")
        if len(rd) < 1000:
            continue

        # Annual thresholds
        annual_gt = rd["value"].quantile(GREEN_PERCENTILE / 100)
        annual_rt = rd["value"].quantile(RED_PERCENTILE / 100)

        # Seasonal thresholds
        seasonal_thresholds = {}
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) > 100:
                seasonal_thresholds[season] = (
                    sd["value"].quantile(GREEN_PERCENTILE / 100),
                    sd["value"].quantile(RED_PERCENTILE / 100),
                )

        # Simulate each day under both threshold schemes
        for date, ddf in rd.groupby("date"):
            ddf = ddf.sort_values("point_time_local")
            vals = ddf["value"].values
            if len(vals) < job_intervals:
                continue
            season = ddf["season"].iloc[0]

            # Annual
            sim_ann = simulate_day(vals, job_intervals, annual_gt, annual_rt)
            if sim_ann is None or sim_ann["baseline_moer"] <= 0:
                continue
            b = sim_ann["baseline_moer"]
            sav_ann = (b - sim_ann[tl_key]) / b * 100

            # Seasonal
            if season in seasonal_thresholds:
                s_gt, s_rt = seasonal_thresholds[season]
                sim_sea = simulate_day(vals, job_intervals, s_gt, s_rt)
                if sim_sea is not None:
                    sav_sea = (b - sim_sea[tl_key]) / b * 100
                else:
                    sav_sea = sav_ann
            else:
                sav_sea = sav_ann

            results.append({
                "region": region, "date": date, "season": season,
                "savings_annual_pct": sav_ann,
                "savings_seasonal_pct": sav_sea,
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 2})
    return df


def plot_seasonal_vs_annual(seasonal_df):
    """Bar chart: annual vs seasonal threshold savings by region."""
    print("\n── Fig: Seasonal vs annual thresholds ──")

    summary = seasonal_df.groupby("region").agg({
        "savings_annual_pct": "mean",
        "savings_seasonal_pct": "mean",
    }).reindex(CH3_REGIONS.keys())

    with thesis_style():
        fig, ax = plt.subplots(figsize=FIG_SEASONAL["figsize"])
        regions = list(CH3_REGIONS.keys())
        x = np.arange(len(regions))
        w = 0.35

        ax.bar(x - w / 2, summary["savings_annual_pct"], w,
               label="Annual thresholds", color="#fc8d59", edgecolor="white")
        ax.bar(x + w / 2, summary["savings_seasonal_pct"], w,
               label="Seasonal thresholds", color="#91bfdb", edgecolor="white")

        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("Mean TL Savings (%)")
        ax.legend(fontsize=10)
        ax.set_ylim(bottom=0)

        # Annotate improvement
        for i, region in enumerate(regions):
            ann = summary.loc[region, "savings_annual_pct"]
            sea = summary.loc[region, "savings_seasonal_pct"]
            diff = sea - ann
            if abs(diff) > 0.05:
                ax.text(i + w / 2, sea + 0.1, f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}",
                        ha="center", fontsize=8, color="green" if diff > 0 else "red")

        save_fig(fig, "fig_ext_seasonal_thresholds")

    for region in CH3_REGIONS:
        ann = summary.loc[region, "savings_annual_pct"]
        sea = summary.loc[region, "savings_seasonal_pct"]
        record_number("Thresholds", f"{rshort(region)} seasonal improvement ppts", sea - ann, ".2f")


# =============================================================================
# REGION-SPECIFIC OPTIMA & "LAZY OPERATOR" TEST
# =============================================================================

def find_optima_and_penalty(sweep_df):
    """
    For each region, find the Pareto-optimal threshold (max savings with
    >=80% days having contiguous green). Compare to universal P25/P75.
    """
    print("\n── Region-specific optima ──")

    rows = []
    for region in CH3_REGIONS:
        rd = sweep_df[sweep_df["region"] == region]
        if len(rd) == 0:
            continue

        # Filter to feasible: >=80% days have contiguous green window
        feasible = rd[rd["pct_days_contiguous"] >= 80]
        if len(feasible) == 0:
            feasible = rd  # fallback if nothing meets criterion

        # Best feasible
        best_idx = feasible["mean_savings_pct"].idxmax()
        best = feasible.loc[best_idx]

        # Canonical P25/P75
        canonical = rd[(rd["green_pct"] == GREEN_PERCENTILE) & (rd["red_pct"] == RED_PERCENTILE)]
        canonical_sav = canonical["mean_savings_pct"].values[0] if len(canonical) > 0 else 0

        penalty = best["mean_savings_pct"] - canonical_sav

        rows.append({
            "region": region,
            "optimal_green_pct": best["green_pct"],
            "optimal_red_pct": best["red_pct"],
            "optimal_savings_pct": best["mean_savings_pct"],
            "optimal_green_hours": best["mean_green_hours"],
            "canonical_savings_pct": canonical_sav,
            "penalty_ppts": penalty,
        })
        record_number("Thresholds",
                      f"{rshort(region)} optimal split P{int(best['green_pct'])}/P{int(best['red_pct'])}",
                      best["mean_savings_pct"], ".2f")
        record_number("Thresholds", f"{rshort(region)} P25/P75 penalty (ppts)", penalty, ".2f")

    table = pd.DataFrame(rows)
    save_table(table, "table_ext_threshold_optima",
               "Region-specific optimal thresholds vs universal P25/P75.")

    max_penalty = table["penalty_ppts"].abs().max()
    record_number("Thresholds", "Max penalty of universal P25/P75 (ppts)", max_penalty, ".2f")
    return table


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()

    # Main sweep
    sweep_df = run_threshold_sweep(df_5min, recompute=recompute)
    plot_pareto_frontier(sweep_df)
    plot_threshold_heatmap(sweep_df)

    # Binary vs ternary
    bin_df = compare_binary_vs_ternary(df_5min, sweep_df)
    plot_binary_vs_ternary(bin_df)

    # Seasonal vs annual
    seasonal_df = compare_seasonal_vs_annual(df_5min, recompute=recompute)
    plot_seasonal_vs_annual(seasonal_df)

    # Optima and penalty
    find_optima_and_penalty(sweep_df)

    export_numbers()
    print("\n✅ Threshold optimization complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
