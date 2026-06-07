"""
ch3_fig_green_window_runlength.py — Green Window Run-Length Distribution

Boxplot of consecutive green-period lengths by archetype.
Green = MOER < P25 threshold (operating-window percentile, same as ch3_s2).

Outputs:
    ch3_outputs/figures/fig_green_window_runlength.png/pdf
    ch3_outputs/tables/table_green_window_runlength.csv/md

Usage:
    python ch3_fig_green_window_runlength.py
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, compute_thresholds,
    CH3_REGIONS, CHARACTERIZATION_YEARS, INTERVALS_PER_HOUR,
    rshort, rcolor,
)

# =============================================================================
# CONFIG
# =============================================================================
ANALYSIS_YEARS = CHARACTERIZATION_YEARS
SECTION_TAG    = "Green-Window-RunLength"

# Archetype display names (thesis naming)
ARCHETYPE_LABELS = {
    "BPA":                "Hydro-baseload",
    "CAISO_NORTH":        "Solar-dominated",
    "ERCOT_NORTHCENTRAL": "Wind-gas mix",
    "ISONE_CT":           "Gas-nuclear Mix",
    "MISO_INDIANAPOLIS":  "Fossil-Heavy",
    "SPP_KANSAS":         "Wind-dominated",
}


# =============================================================================
# RUN-LENGTH EXTRACTION
# =============================================================================

def extract_run_lengths(boolean_series: np.ndarray) -> np.ndarray:
    """
    Given a boolean array, return lengths (in intervals) of all consecutive
    True runs.  A run must be at least 1 interval long.
    """
    if len(boolean_series) == 0:
        return np.array([])
    # Pad with False on both ends to catch runs at boundaries
    padded = np.concatenate([[False], boolean_series, [False]])
    diff   = np.diff(padded.astype(int))
    starts = np.where(diff == 1)[0]
    ends   = np.where(diff == -1)[0]
    return (ends - starts).astype(float)


def compute_run_lengths(df_5min: pd.DataFrame) -> dict:
    """
    Returns {region: np.ndarray of run lengths in hours}.
    Uses operating-window P25 threshold from compute_thresholds.
    Runs are extracted from the full dataset (not just shift window) to
    capture runs that span shift boundaries — but only green intervals
    within the data's time coverage are used.
    """
    thresholds = compute_thresholds(df_5min)
    td = {r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()}

    run_lengths = {}
    for region in CH3_REGIONS:
        if region not in td:
            run_lengths[region] = np.array([])
            continue
        gt = td[region]

        rd = df_5min[df_5min["region"] == region].sort_values("point_time_local")
        if ANALYSIS_YEARS:
            rd = rd[rd["year"].isin(ANALYSIS_YEARS)]

        is_green = (rd["value"].values <= gt)
        runs_intervals = extract_run_lengths(is_green)
        # Convert 5-min intervals → hours
        runs_hours = runs_intervals / INTERVALS_PER_HOUR
        run_lengths[region] = runs_hours

        print(f"  {rshort(region):10s}  {len(runs_hours):,} runs  "
              f"median={np.median(runs_hours):.2f}h  "
              f"p90={np.percentile(runs_hours, 90):.2f}h")

    return run_lengths


# =============================================================================
# SUMMARY TABLE
# =============================================================================

def build_table(run_lengths: dict) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        rl = run_lengths.get(region, np.array([]))
        if len(rl) == 0:
            continue
        arch  = ARCHETYPE_LABELS.get(region, region)
        mean_ = float(np.mean(rl))
        med_  = float(np.median(rl))
        p90_  = float(np.percentile(rl, 90))
        frac_ = float(np.mean(rl >= 2.0))

        rows.append({
            "Archetype":             arch,
            "Region":                rshort(region),
            "Mean Run Length (h)":   round(mean_, 2),
            "Median Run Length (h)": round(med_,  2),
            "P90 Run Length (h)":    round(p90_,  2),
            "Fraction ≥ 2h":         round(frac_, 3),
            "N Runs":                len(rl),
        })

        record_number(SECTION_TAG, f"{rshort(region)} median green run h", med_,  ".2f")
        record_number(SECTION_TAG, f"{rshort(region)} p90 green run h",    p90_,  ".2f")
        record_number(SECTION_TAG, f"{rshort(region)} fraction runs ≥2h",  frac_, ".3f")

    return pd.DataFrame(rows)


# =============================================================================
# FIGURE
# =============================================================================

def plot_mean_duration(run_lengths: dict):
    """
    Bar chart: mean green window duration per archetype with 95% CI error bars.
    Ordered by mean duration ascending.
    """
    from ch3_common import bootstrap_ci, N_BOOTSTRAP

    # Compute stats
    stats = {}
    for region, rl in run_lengths.items():
        if len(rl) < 2:
            continue
        mean_ = float(np.mean(rl))
        lo, hi = bootstrap_ci(rl, np.mean, N_BOOTSTRAP)
        stats[region] = {"mean": mean_, "lo": lo, "hi": hi}

    # Order by mean ascending
    ordered = sorted(stats, key=lambda r: stats[r]["mean"])
    labels  = [ARCHETYPE_LABELS.get(r, rshort(r)) for r in ordered]
    means   = [stats[r]["mean"] for r in ordered]
    ci_lo   = [stats[r]["mean"] - stats[r]["lo"] for r in ordered]
    ci_hi   = [stats[r]["hi"] - stats[r]["mean"] for r in ordered]
    colors  = [rcolor(r) for r in ordered]

    x = np.arange(len(ordered))

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        bars = ax.bar(x, means, color=colors, alpha=0.85, width=0.55, zorder=3)
        ax.errorbar(x, means, yerr=[ci_lo, ci_hi],
                    fmt="none", color="black", capsize=5,
                    linewidth=1.4, zorder=4)

        # 2-hour reference line
        ax.axhline(2.0, color="#333333", linewidth=1.2, linestyle="--",
                   alpha=0.8, label="2-hr job duration")

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10, rotation=15, ha="right")
        ax.set_ylabel("Mean Green Window Duration (hours)", fontsize=11)
        ax.set_xlabel("")
        ax.legend(fontsize=9, loc="upper left")
        ax.set_ylim(0, max(means) * 1.3)

        fig.tight_layout()
        save_fig(fig, "fig_green_window_runlength")


# =============================================================================
# MAIN
# =============================================================================

def main():
    init()
    print("\n── Green Window Run-Length Distribution ──")

    df_5min = load_5min()
    if ANALYSIS_YEARS:
        df_5min = df_5min[df_5min["year"].isin(ANALYSIS_YEARS)].copy()

    print("\n  Extracting run lengths...")
    run_lengths = compute_run_lengths(df_5min)

    print("\n  Building summary table...")
    table = build_table(run_lengths)
    print(table.to_string(index=False))
    save_table(table, "table_green_window_runlength",
               caption="Green window run-length statistics by archetype (MOER < P25 threshold).")

    print("\n  Plotting...")
    plot_mean_duration(run_lengths)

    export_numbers()
    print("\n✅ Done.")


if __name__ == "__main__":
    main()