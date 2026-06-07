"""
ch3_extended_shift_flexibility.py — How much does extending operating hours help?

Systematically varies operating window size to quantify the marginal value of
each additional hour of flexibility. Identifies the minimum viable window
for statistically significant savings.

Research question:
    "How much scheduling opportunity do you gain by extending your operating
    hours, and what's the minimum window where scheduling matters?"

Outputs:
    Figures:
        fig_ext_window_savings_curve.png/pdf
        fig_ext_marginal_hour_value.png/pdf
        fig_ext_named_shifts.png/pdf
    Tables:
        table_ext_shift_flexibility.csv/md

Usage:
    python ch3_extended_shift_flexibility.py
    python ch3_extended_shift_flexibility.py --recompute
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

# Window sizes to test (hours)
WINDOW_SIZES = [6, 8, 10, 12, 14, 16, 20, 24]

# Named shift patterns for the comparison chart
NAMED_SHIFTS = {
    "1st shift (06-14)":    (6, 14),
    "Extended day (06-18)": (6, 18),
    "2-shift (06-22)":      (6, 22),
    "3-shift (24/7)":       (0, 24),
    "2nd shift (14-22)":    (14, 22),
    "Night (22-06)":        (22, 6),   # crosses midnight
}

# For window sweep, center windows on midday
WINDOW_CENTER_HOUR = 12


# =============================================================================
# WINDOW SWEEP
# =============================================================================

def run_window_sweep(df_5min, recompute=False):
    """
    For each window size, compute thresholds WITHIN that window and run TL sim.
    """
    print("\n── Window size sweep ──")

    cache_tag = "ext_window_sweep"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 3})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"

    results = []
    for window_hours in WINDOW_SIZES:
        # Center window on midday
        half = window_hours / 2
        w_start = max(0, int(WINDOW_CENTER_HOUR - half))
        w_end = min(24, int(WINDOW_CENTER_HOUR + half))

        # Special case: 24-hour window
        if window_hours >= 24:
            w_start, w_end = 0, 24

        print(f"  Window: {w_start:02d}:00-{w_end:02d}:00 ({window_hours}h)")

        for region in CH3_REGIONS:
            if w_end > w_start:
                rd = df_5min[
                    (df_5min["region"] == region)
                    & (df_5min["hour"] >= w_start)
                    & (df_5min["hour"] < w_end)
                ].sort_values("point_time_local")
            else:
                # Midnight crossing
                rd = df_5min[
                    (df_5min["region"] == region)
                    & ((df_5min["hour"] >= w_start) | (df_5min["hour"] < w_end))
                ].sort_values("point_time_local")

            if len(rd) < 1000:
                continue

            # Compute thresholds WITHIN this window
            gt = rd["value"].quantile(GREEN_PERCENTILE / 100)
            rt = rd["value"].quantile(RED_PERCENTILE / 100)

            day_savings = []
            for date, ddf in rd.groupby("date"):
                ddf = ddf.sort_values("point_time_local")
                vals = ddf["value"].values
                if len(vals) < job_intervals:
                    continue

                sim = simulate_day(vals, job_intervals, gt, rt)
                if sim is None:
                    continue
                b = sim["baseline_moer"]
                if b > 0:
                    day_savings.append((b - sim[tl_key]) / b * 100)

            if len(day_savings) < 30:
                continue

            ci_lo, ci_hi = bootstrap_ci(np.array(day_savings))
            sig = ci_lo > 0  # statistically significant if CI doesn't include 0

            results.append({
                "region": region,
                "window_hours": window_hours,
                "window_start": w_start,
                "window_end": w_end,
                "mean_savings_pct": np.mean(day_savings),
                "std_savings_pct": np.std(day_savings),
                "ci_lo": ci_lo, "ci_hi": ci_hi,
                "significant": sig,
                "green_threshold": gt,
                "red_threshold": rt,
                "n_days": len(day_savings),
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 3})
    print(f"  ✅ Sweep complete: {len(df):,} results")
    return df


def plot_window_savings_curve(sweep_df):
    """Line plot: TL savings vs window size, one line per region."""
    print("\n── Fig: Window savings curve ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for region in CH3_REGIONS:
            rd = sweep_df[sweep_df["region"] == region].sort_values("window_hours")
            if len(rd) == 0:
                continue
            ax.plot(rd["window_hours"], rd["mean_savings_pct"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=8, linewidth=2, label=rshort(region))
            ax.fill_between(rd["window_hours"], rd["ci_lo"], rd["ci_hi"],
                            color=rcolor(region), alpha=0.08)

        ax.set_xlabel("Operating Window (hours)")
        ax.set_ylabel("Mean TL Savings (%)")
        ax.set_xticks(WINDOW_SIZES)
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

        # Mark the canonical 12-hour window
        ax.axvline(12, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.text(12.3, ax.get_ylim()[1] * 0.95, "Canonical\n(12h)", fontsize=8, color="gray")

        save_fig(fig, "fig_ext_window_savings_curve")

    # Record key numbers
    for region in CH3_REGIONS:
        rd = sweep_df[sweep_df["region"] == region]
        r8 = rd[rd["window_hours"] == 8]
        r12 = rd[rd["window_hours"] == 12]
        r24 = rd[rd["window_hours"] == 24]
        if len(r8) > 0 and len(r12) > 0:
            gain = r12["mean_savings_pct"].values[0] - r8["mean_savings_pct"].values[0]
            record_number("Shifts", f"{rshort(region)} 8h→12h improvement (ppts)", gain, ".2f")
        if len(r12) > 0 and len(r24) > 0:
            gain = r24["mean_savings_pct"].values[0] - r12["mean_savings_pct"].values[0]
            record_number("Shifts", f"{rshort(region)} 12h→24h improvement (ppts)", gain, ".2f")


def plot_marginal_hour_value(sweep_df):
    """Incremental savings per additional operating hour."""
    print("\n── Fig: Marginal hour value ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for region in CH3_REGIONS:
            rd = sweep_df[sweep_df["region"] == region].sort_values("window_hours")
            if len(rd) < 2:
                continue

            hours = rd["window_hours"].values
            savings = rd["mean_savings_pct"].values
            marginal = np.diff(savings) / np.diff(hours)
            midpoints = (hours[:-1] + hours[1:]) / 2

            ax.plot(midpoints, marginal, color=rcolor(region), marker=rmarker(region),
                    markersize=7, linewidth=1.8, label=rshort(region))

        ax.axhline(0, color="gray", linewidth=0.5)
        ax.set_xlabel("Operating Window (hours)")
        ax.set_ylabel("Marginal Savings per Hour (ppts/hr)")
        ax.legend(fontsize=9)

        save_fig(fig, "fig_ext_marginal_hour_value")


# =============================================================================
# NAMED SHIFT COMPARISON
# =============================================================================

def run_named_shifts(df_5min, recompute=False):
    """Run TL sim for each named shift pattern."""
    print("\n── Named shift patterns ──")

    cache_tag = "ext_named_shifts"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"

    results = []
    for shift_name, (s_start, s_end) in NAMED_SHIFTS.items():
        print(f"  {shift_name}")
        crosses_midnight = s_start > s_end

        for region in CH3_REGIONS:
            if crosses_midnight:
                rd = df_5min[
                    (df_5min["region"] == region)
                    & ((df_5min["hour"] >= s_start) | (df_5min["hour"] < s_end))
                ]
            else:
                rd = df_5min[
                    (df_5min["region"] == region)
                    & (df_5min["hour"] >= s_start)
                    & (df_5min["hour"] < s_end)
                ]
            rd = rd.sort_values("point_time_local")

            if len(rd) < 1000:
                continue

            gt = rd["value"].quantile(GREEN_PERCENTILE / 100)
            rt = rd["value"].quantile(RED_PERCENTILE / 100)

            day_savings = []
            for date, ddf in rd.groupby("date"):
                ddf = ddf.sort_values("point_time_local")
                vals = ddf["value"].values
                if len(vals) < job_intervals:
                    continue
                sim = simulate_day(vals, job_intervals, gt, rt)
                if sim is None:
                    continue
                b = sim["baseline_moer"]
                if b > 0:
                    day_savings.append((b - sim[tl_key]) / b * 100)

            if len(day_savings) < 30:
                continue

            results.append({
                "shift_name": shift_name,
                "region": region,
                "start_hour": s_start,
                "end_hour": s_end,
                "window_hours": (s_end - s_start) % 24 if crosses_midnight else (s_end - s_start),
                "mean_savings_pct": np.mean(day_savings),
                "n_days": len(day_savings),
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 2})
    return df


def plot_named_shifts(shift_df):
    """Grouped bar: savings by named shift pattern and region."""
    print("\n── Fig: Named shifts ──")

    # Order shifts logically
    shift_order = [
        "Night (22-06)", "1st shift (06-14)", "Extended day (06-18)",
        "2nd shift (14-22)", "2-shift (06-22)", "3-shift (24/7)",
    ]

    with thesis_style():
        fig, ax = plt.subplots(figsize=(12, 5))
        regions = list(CH3_REGIONS.keys())
        n_r = len(regions)
        shifts_present = [s for s in shift_order if s in shift_df["shift_name"].unique()]
        n_s = len(shifts_present)
        w = 0.8 / n_r
        x = np.arange(n_s)

        for j, region in enumerate(regions):
            vals = []
            for shift in shifts_present:
                rd = shift_df[(shift_df["region"] == region) & (shift_df["shift_name"] == shift)]
                vals.append(rd["mean_savings_pct"].values[0] if len(rd) > 0 else 0)
            ax.bar(x + j * w, vals, w, label=rshort(region),
                   color=rcolor(region), edgecolor="white", alpha=0.85)

        ax.set_xticks(x + (n_r - 1) * w / 2)
        ax.set_xticklabels(shifts_present, fontsize=8, rotation=30, ha="right")
        ax.set_ylabel("Mean TL Savings (%)")
        ax.legend(fontsize=8, ncol=3)
        ax.set_ylim(bottom=0)

        save_fig(fig, "fig_ext_named_shifts")


# =============================================================================
# MINIMUM VIABLE WINDOW
# =============================================================================

def find_minimum_viable_window(sweep_df):
    """Find smallest window with statistically significant savings per region."""
    print("\n── Minimum viable window ──")

    for region in CH3_REGIONS:
        rd = sweep_df[sweep_df["region"] == region].sort_values("window_hours")
        sig = rd[rd["significant"]]
        if len(sig) > 0:
            min_window = sig["window_hours"].iloc[0]
            record_number("Shifts", f"{rshort(region)} minimum viable window (hrs)", min_window, "d")
        else:
            record_number("Shifts", f"{rshort(region)} minimum viable window", "none found")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()

    # Window sweep
    sweep_df = run_window_sweep(df_5min, recompute=recompute)
    plot_window_savings_curve(sweep_df)
    plot_marginal_hour_value(sweep_df)
    find_minimum_viable_window(sweep_df)

    # Named shifts
    shift_df = run_named_shifts(df_5min, recompute=recompute)
    plot_named_shifts(shift_df)

    # Save combined table
    save_table(sweep_df, "table_ext_shift_flexibility",
               "TL savings by operating window size.")

    export_numbers()
    print("\n✅ Shift flexibility analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
