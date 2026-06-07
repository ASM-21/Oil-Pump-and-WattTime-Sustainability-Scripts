"""
ch3_extended_production_queue.py — What happens with a real batch of 50 parts?

Simulates production queues of varying size under different scheduling strategies.
Shows green-window saturation, per-job savings decay, and the throughput-carbon tradeoff.

Research question:
    "Your analysis assumes one job at a time. How do savings scale with a
    real production queue?"

Outputs:
    Figures:
        fig_ext_queue_saturation.png/pdf
        fig_ext_queue_strategies.png/pdf
        fig_ext_queue_throughput.png/pdf
    Tables:
        table_ext_queue_results.csv/md

Usage:
    python ch3_extended_production_queue.py
    python ch3_extended_production_queue.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min,
    compute_thresholds,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

JOB_DURATION_HOURS = 0.5  # 30-min per part (typical CNC cycle)
BATCH_SIZES = [1, 5, 10, 20, 40]
JOB_INTERVALS = int(JOB_DURATION_HOURS * INTERVALS_PER_HOUR)  # 6 intervals


# =============================================================================
# QUEUE SIMULATION
# =============================================================================

def simulate_queue(day_values, n_jobs, job_intervals, green_threshold, red_threshold):
    """
    Simulate scheduling n_jobs on a single day under three strategies:

    Strategy 1 — Fixed start: All jobs begin at interval 0 (start of shift)
    Strategy 2 — Delayed start: Wait for first green, then run sequentially
    Strategy 3 — Green-only: Only run during green intervals; pause otherwise
    Strategy 4 — Green-preferred: Run during green/yellow; pause during red

    Returns dict with per-strategy metrics.
    """
    n = len(day_values)
    total_needed = n_jobs * job_intervals

    if n < job_intervals:
        return None

    green_mask = day_values <= green_threshold
    yellow_mask = (day_values > green_threshold) & (day_values < red_threshold)
    red_mask = day_values >= red_threshold

    results = {}

    # --- Strategy 1: Fixed start (baseline) ---
    end_idx = min(total_needed, n)
    s1_moer = float(np.mean(day_values[:end_idx]))
    s1_jobs_completed = min(n_jobs, n // job_intervals)
    s1_completion_interval = min(total_needed, n)
    results["fixed"] = {
        "mean_moer": s1_moer,
        "jobs_completed": s1_jobs_completed,
        "completion_interval": s1_completion_interval,
        "idle_intervals": 0,
    }

    # --- Strategy 2: Delayed start (first green, then sequential) ---
    first_green = np.where(green_mask)[0]
    if len(first_green) > 0:
        start = first_green[0]
    else:
        # Fallback to first yellow
        first_yellow = np.where(yellow_mask)[0]
        start = first_yellow[0] if len(first_yellow) > 0 else 0

    end_idx = min(start + total_needed, n)
    s2_vals = day_values[start:end_idx]
    s2_moer = float(np.mean(s2_vals)) if len(s2_vals) > 0 else float(np.mean(day_values[:total_needed]))
    s2_jobs = len(s2_vals) // job_intervals
    results["delayed"] = {
        "mean_moer": s2_moer,
        "jobs_completed": min(s2_jobs, n_jobs),
        "completion_interval": end_idx,
        "idle_intervals": start,  # waited this long
    }

    # --- Strategy 3: Green-only (pause during yellow/red) ---
    s3_intervals_used = []
    for i in range(n):
        if green_mask[i]:
            s3_intervals_used.append(i)
            if len(s3_intervals_used) >= total_needed:
                break

    if len(s3_intervals_used) > 0:
        s3_moer = float(np.mean(day_values[s3_intervals_used]))
        s3_jobs = len(s3_intervals_used) // job_intervals
        s3_completion = s3_intervals_used[-1] + 1 if s3_intervals_used else n
        s3_idle = s3_completion - len(s3_intervals_used)
    else:
        s3_moer = float(np.mean(day_values[:total_needed]))
        s3_jobs = 0
        s3_completion = n
        s3_idle = n

    results["green_only"] = {
        "mean_moer": s3_moer,
        "jobs_completed": min(s3_jobs, n_jobs),
        "completion_interval": s3_completion,
        "idle_intervals": s3_idle,
    }

    # --- Strategy 4: Green-preferred (run green+yellow, pause red) ---
    s4_intervals_used = []
    for i in range(n):
        if green_mask[i] or yellow_mask[i]:
            s4_intervals_used.append(i)
            if len(s4_intervals_used) >= total_needed:
                break

    if len(s4_intervals_used) > 0:
        s4_moer = float(np.mean(day_values[s4_intervals_used]))
        s4_jobs = len(s4_intervals_used) // job_intervals
        s4_completion = s4_intervals_used[-1] + 1
        s4_idle = s4_completion - len(s4_intervals_used)
    else:
        s4_moer = float(np.mean(day_values[:total_needed]))
        s4_jobs = 0
        s4_completion = n
        s4_idle = n

    results["green_preferred"] = {
        "mean_moer": s4_moer,
        "jobs_completed": min(s4_jobs, n_jobs),
        "completion_interval": s4_completion,
        "idle_intervals": s4_idle,
    }

    return results


def run_queue_analysis(df_5min, thresholds, recompute=False):
    """Run queue simulation across all regions, batch sizes, and days."""
    print("\n── Queue simulation ──")

    cache_tag = "ext_queue_sim"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    thresh_dict = {
        r["region"]: (r["green_threshold"], r["red_threshold"])
        for _, r in thresholds.iterrows()
    }

    results = []
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        gt, rt = thresh_dict[region]

        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")

        day_count = 0
        for date, ddf in rd.groupby("date"):
            vals = ddf.sort_values("point_time_local")["value"].values
            if len(vals) < JOB_INTERVALS * 2:
                continue

            for batch_size in BATCH_SIZES:
                sim = simulate_queue(vals, batch_size, JOB_INTERVALS, gt, rt)
                if sim is None:
                    continue

                baseline_moer = sim["fixed"]["mean_moer"]
                for strategy, metrics in sim.items():
                    savings = (baseline_moer - metrics["mean_moer"]) / baseline_moer * 100 if baseline_moer > 0 else 0
                    completion_hours = metrics["completion_interval"] / INTERVALS_PER_HOUR
                    idle_hours = metrics["idle_intervals"] / INTERVALS_PER_HOUR

                    results.append({
                        "region": region, "date": date,
                        "batch_size": batch_size, "strategy": strategy,
                        "mean_moer": metrics["mean_moer"],
                        "savings_vs_fixed_pct": savings if strategy != "fixed" else 0,
                        "jobs_completed": metrics["jobs_completed"],
                        "completion_hours": completion_hours,
                        "idle_hours": idle_hours,
                    })

            day_count += 1
            if day_count % 200 == 0:
                print(f"    {region}: {day_count} days...")

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 2})
    print(f"  ✅ Queue sim: {len(df):,} results")
    return df


# =============================================================================
# FIGURES
# =============================================================================

def plot_queue_saturation(queue_df):
    """Per-job savings vs batch size, one line per region (delayed start strategy)."""
    print("\n── Fig: Queue saturation ──")

    delayed = queue_df[queue_df["strategy"] == "delayed"]
    summary = delayed.groupby(["region", "batch_size"])["savings_vs_fixed_pct"].mean().reset_index()

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for region in CH3_REGIONS:
            rd = summary[summary["region"] == region].sort_values("batch_size")
            if len(rd) == 0:
                continue
            ax.plot(rd["batch_size"], rd["savings_vs_fixed_pct"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=8, linewidth=2, label=rshort(region))

        ax.set_xlabel(f"Batch Size (×{JOB_DURATION_HOURS}hr jobs)")
        ax.set_ylabel("Mean Savings vs Fixed Start (%)")
        ax.set_xticks(BATCH_SIZES)
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

        save_fig(fig, "fig_ext_queue_saturation")

    # Record saturation numbers
    single_job = summary[summary["batch_size"] == 1]
    big_batch = summary[summary["batch_size"] == BATCH_SIZES[-1]]
    for region in CH3_REGIONS:
        s1 = single_job[single_job["region"] == region]["savings_vs_fixed_pct"].values
        sb = big_batch[big_batch["region"] == region]["savings_vs_fixed_pct"].values
        if len(s1) > 0 and len(sb) > 0 and s1[0] > 0:
            retained = sb[0] / s1[0] * 100
            record_number("Queue", f"{rshort(region)} retained at batch={BATCH_SIZES[-1]}", retained, ".0f")


def plot_queue_strategies(queue_df):
    """Compare strategies at batch size 20."""
    print("\n── Fig: Queue strategies ──")

    b20 = queue_df[queue_df["batch_size"] == 20]
    if len(b20) == 0:
        b20 = queue_df[queue_df["batch_size"] == BATCH_SIZES[-2]]

    summary = b20.groupby(["region", "strategy"])["savings_vs_fixed_pct"].mean().reset_index()

    strategies = ["delayed", "green_preferred", "green_only"]
    strat_labels = ["Delayed Start", "Green+Yellow", "Green Only"]
    strat_colors = ["#4575b4", "#fc8d59", "#2ca02c"]

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 5))
        regions = list(CH3_REGIONS.keys())
        x = np.arange(len(regions))
        w = 0.25

        for j, (strat, label, color) in enumerate(zip(strategies, strat_labels, strat_colors)):
            vals = []
            for region in regions:
                rd = summary[(summary["region"] == region) & (summary["strategy"] == strat)]
                vals.append(rd["savings_vs_fixed_pct"].values[0] if len(rd) > 0 else 0)
            ax.bar(x + j * w, vals, w, label=label, color=color, edgecolor="white")

        ax.set_xticks(x + w)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("Savings vs Fixed Start (%)")
        ax.set_title(f"Scheduling Strategies (batch = 20 × {JOB_DURATION_HOURS}hr jobs)")
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

        save_fig(fig, "fig_ext_queue_strategies")


def plot_throughput_tradeoff(queue_df):
    """Scatter: carbon savings vs idle time for each strategy × batch size."""
    print("\n── Fig: Throughput tradeoff ──")

    summary = queue_df[queue_df["strategy"] != "fixed"].groupby(
        ["region", "batch_size", "strategy"]
    ).agg(
        savings=("savings_vs_fixed_pct", "mean"),
        idle=("idle_hours", "mean"),
    ).reset_index()

    strat_markers = {"delayed": "o", "green_preferred": "s", "green_only": "^"}

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharex=True, sharey=True)
        axes = axes.flatten()

        for i, region in enumerate(CH3_REGIONS):
            ax = axes[i]
            rd = summary[summary["region"] == region]

            for strat, marker in strat_markers.items():
                sd = rd[rd["strategy"] == strat].sort_values("batch_size")
                if len(sd) == 0:
                    continue
                ax.scatter(sd["idle"], sd["savings"], marker=marker, s=sd["batch_size"] * 5 + 20,
                           color=rcolor(region), alpha=0.7, label=strat if i == 0 else "")

            ax.set_title(rshort(region), fontsize=11)
            if i >= 3:
                ax.set_xlabel("Mean Idle Time (hours)")
            if i % 3 == 0:
                ax.set_ylabel("Carbon Savings (%)")

        axes[0].legend(fontsize=8)
        plt.tight_layout()
        save_fig(fig, "fig_ext_queue_throughput")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()
    thresholds = compute_thresholds(df_5min)

    queue_df = run_queue_analysis(df_5min, thresholds, recompute=recompute)
    save_table(
        queue_df.groupby(["region", "batch_size", "strategy"]).agg({
            "savings_vs_fixed_pct": "mean",
            "completion_hours": "mean",
            "idle_hours": "mean",
            "jobs_completed": "mean",
        }).round(2).reset_index(),
        "table_ext_queue_results",
        "Production queue scheduling results by strategy and batch size."
    )

    plot_queue_saturation(queue_df)
    plot_queue_strategies(queue_df)
    plot_throughput_tradeoff(queue_df)

    export_numbers()
    print("\n✅ Production queue analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
