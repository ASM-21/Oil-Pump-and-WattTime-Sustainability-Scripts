"""
ch3_tod_annual.py — Fixed Time-of-Day (Annual Best Hour) Scheduling Analysis

Simulates a 2-hr reference job starting at the single best annual hour for each
region (no real-time signal — pure time-of-day heuristic). Benchmarks against
baseline (uniform random) and optimal (perfect hindsight).

The "annual best hour" is the shift-window start hour h that minimizes the mean
2-hr rolling-window MOER across all days and years in the dataset. This mirrors
the value that would appear in Table 3-3 of the thesis.

Outputs:
    Tables:
        table_tod_annual_savings.csv/md  — savings %, capture rate, CI by region
    Figures:
        fig_tod_annual_savings.png/pdf   — bar chart of savings % by region
    Numbers appended to ch3_numbers.md

Usage:
    python ch3_tod_annual.py
    python ch3_tod_annual.py --recompute   # ignore cache
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, run_scheduling_sim, compute_thresholds, simulate_day,
    bootstrap_ci,
    CH3_REGIONS, REGION_COLORS, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    N_BOOTSTRAP, CHARACTERIZATION_YEARS,
    rlabel, rshort, rcolor,
    TABLES_DIR, FIGURES_DIR,
)

# =============================================================================
# CONFIG
# =============================================================================

# If you have already run Table 3-3 and want to lock in specific hours, enter
# them here (integer hour, 24-hr, within shift window 6–17).
# Set to None for any region to derive from data instead.
ANNUAL_BEST_HOUR_OVERRIDE = {
    "BPA":                None,   # ← fill in from Table 3-3, or leave None
    "CAISO_NORTH":        None,
    "ERCOT_NORTHCENTRAL": None,
    "ISONE_CT":           None,
    "MISO_INDIANAPOLIS":  None,
    "SPP_KANSAS":         None,
}

# Years to include in the analysis
ANALYSIS_YEARS = CHARACTERIZATION_YEARS   # e.g. [2021, 2022, 2023, 2024]

SECTION_TAG = "TOD-Annual"

# =============================================================================
# STEP 1 — Derive annual best hours from data
# =============================================================================

def compute_annual_best_hours(df_5min: pd.DataFrame) -> dict:
    """
    For each region, find the shift-window start hour h (6 ≤ h < 18) that
    minimizes the mean 2-hr rolling-window MOER across all days in df_5min.

    Returns dict: {region: best_hour (int)}
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)  # 24
    best_hours = {}

    win = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].copy()

    for region in CH3_REGIONS:
        rd = win[win["region"] == region].sort_values("point_time_local")
        hour_means = {}   # {start_hour: [mean_moer_per_window, ...]}

        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            n = len(vals)
            if n < job_intervals:
                continue
            # Build mapping from start-interval-index → start_hour
            hours = ddf["hour"].values
            for i in range(n - job_intervals + 1):
                h = int(hours[i])
                window_mean = float(vals[i:i + job_intervals].mean())
                if h not in hour_means:
                    hour_means[h] = []
                hour_means[h].append(window_mean)

        if not hour_means:
            print(f"  ⚠ No data for {region} — skipping best-hour computation")
            continue

        # Best hour = argmin of grand mean across all daily windows starting at h
        best_h = min(hour_means, key=lambda h: np.mean(hour_means[h]))
        best_hours[region] = best_h
        grand_mean = np.mean(hour_means[best_h])
        print(f"  {rshort(region):10s}  best hour = {best_h:02d}:00  "
              f"(mean MOER {grand_mean:,.0f} {SIGNAL_UNIT}, "
              f"n={len(hour_means[best_h])} windows)")

    return best_hours


# =============================================================================
# STEP 2 — Daily fixed-TOD simulation
# =============================================================================

def simulate_fixed_tod(df_5min: pd.DataFrame, best_hours: dict) -> pd.DataFrame:
    """
    For every (region, date), start the 2-hr job at the fixed annual best hour.
    Compare against baseline and optimal from simulate_day().

    Returns long DataFrame with one row per (region, date).
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)

    # Reuse canonical thresholds for baseline/optimal (needed by simulate_day)
    thresholds = compute_thresholds(df_5min)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    win = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].copy()

    if ANALYSIS_YEARS:
        win = win[win["year"].isin(ANALYSIS_YEARS)]

    records = []
    for region, best_h in best_hours.items():
        if region not in td:
            continue
        gt, rt = td[region]
        rd = win[win["region"] == region].sort_values("point_time_local")

        skipped = 0
        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            hours = ddf["hour"].values

            # ── baseline + optimal from canonical simulate_day ──────────────
            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None:
                skipped += 1
                continue

            # ── fixed-TOD window: first interval where hour == best_h ───────
            idx = np.where(hours == best_h)[0]
            if len(idx) == 0:
                skipped += 1
                continue
            start = idx[0]
            if start + job_intervals > len(vals):
                skipped += 1
                continue

            tod_moer = float(vals[start:start + job_intervals].mean())
            baseline = sim["baseline_moer"]
            optimal  = sim["optimal_moer"]

            savings_tod     = (baseline - tod_moer) / baseline * 100 if baseline > 0 else 0.0
            savings_optimal = (baseline - optimal)  / baseline * 100 if baseline > 0 else 0.0
            capture_rate    = savings_tod / savings_optimal if savings_optimal > 0 else (1.0 if savings_tod >= 0 else 0.0)

            records.append({
                "region":          region,
                "date":            date,
                "year":            int(ddf["year"].iloc[0]),
                "month":           int(ddf["month"].iloc[0]),
                "season":          ddf["season"].iloc[0],
                "best_hour":       best_h,
                "tod_moer":        tod_moer,
                "baseline_moer":   baseline,
                "optimal_moer":    optimal,
                "savings_tod_pct": savings_tod,
                "savings_opt_pct": savings_optimal,
                "capture_rate":    capture_rate,
            })

        print(f"  {rshort(region):10s}  {len([r for r in records if r['region']==region]):,} days "
              f"simulated  ({skipped} skipped)")

    return pd.DataFrame(records)


# =============================================================================
# STEP 3 — Summary table
# =============================================================================

def build_summary_table(sim_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        if len(rd) == 0:
            continue

        best_h = int(rd["best_hour"].iloc[0])
        n_days = len(rd)

        sav   = rd["savings_tod_pct"].values
        cap   = rd["capture_rate"].values
        opt   = rd["savings_opt_pct"].values

        sav_mean = float(np.mean(sav))
        cap_mean = float(np.mean(np.clip(cap, 0, 1)) * 100)
        opt_mean = float(np.mean(opt))

        sav_lo, sav_hi = bootstrap_ci(sav, np.mean, N_BOOTSTRAP)
        cap_lo, cap_hi = bootstrap_ci(np.clip(cap, 0, 1) * 100, np.mean, N_BOOTSTRAP)

        rows.append({
            "Region":             rlabel(region),
            "Archetype":          CH3_REGIONS[region]["archetype"],
            "Best Hour":          f"{best_h:02d}:00",
            "TOD Savings (%)":    round(sav_mean, 1),
            "95% CI Lower":       round(sav_lo, 1),
            "95% CI Upper":       round(sav_hi, 1),
            "Optimal Savings (%)":round(opt_mean, 1),
            "Capture Rate (%)":   round(cap_mean, 1),
            "CR 95% CI Lower":    round(cap_lo, 1),
            "CR 95% CI Upper":    round(cap_hi, 1),
            "N Days":             n_days,
        })

        record_number(SECTION_TAG, f"{rshort(region)} TOD savings %", sav_mean, ".1f")
        record_number(SECTION_TAG, f"{rshort(region)} capture rate %", cap_mean, ".1f")
        record_number(SECTION_TAG, f"{rshort(region)} best hour", best_h, "d")

    return pd.DataFrame(rows)


# =============================================================================
# STEP 4 — Figure: savings bar chart
# =============================================================================

def plot_tod_savings(summary: pd.DataFrame):
    regions  = list(CH3_REGIONS.keys())
    region_rows = {
        row["Region"]: row
        for _, row in summary.iterrows()
    }

    # Re-index by canonical CH3_REGIONS order
    ordered = [
        region_rows[rlabel(r)]
        for r in regions
        if rlabel(r) in region_rows
    ]
    if not ordered:
        print("  ⚠ No data to plot")
        return

    labels       = [r["Region"].split("(")[0].strip() for r in ordered]
    tod_savings  = [r["TOD Savings (%)"] for r in ordered]
    opt_savings  = [r["Optimal Savings (%)"] for r in ordered]
    ci_lo        = [r["TOD Savings (%)"] - r["95% CI Lower"] for r in ordered]
    ci_hi        = [r["95% CI Upper"] - r["TOD Savings (%)"] for r in ordered]
    best_hours   = [r["Best Hour"] for r in ordered]
    colors       = [rcolor(r) for r in regions if rlabel(r) in region_rows]

    x = np.arange(len(ordered))
    w = 0.35

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 5))

        # Optimal savings (background / reference)
        ax.bar(x - w/2, opt_savings, width=w, color="#cccccc", label="Optimal (hindsight)",
               zorder=2, alpha=0.85)

        # TOD savings
        bars = ax.bar(x + w/2, tod_savings, width=w, color=colors, label="Fixed TOD",
                      zorder=3)

        # Error bars on TOD
        ax.errorbar(x + w/2, tod_savings,
                    yerr=[ci_lo, ci_hi],
                    fmt="none", color="black", capsize=4, linewidth=1.2, zorder=4)

        # Annotate best hour above each TOD bar
        for xi, (bar, bh) in enumerate(zip(bars, best_hours)):
            ax.text(xi + w/2, bar.get_height() + max(ci_hi) + 0.3,
                    bh, ha="center", va="bottom", fontsize=8, style="italic")

        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
        ax.set_ylabel("Mean Daily Savings vs. Baseline (%)")
        ax.set_xlabel("")

        patch_opt = mpatches.Patch(color="#cccccc", label="Optimal (hindsight)")
        patch_tod = mpatches.Patch(color="#555555", label="Fixed TOD (annual best hour, 95% CI)")
        ax.legend(handles=[patch_opt, patch_tod], fontsize=9, loc="upper right")
        ax.set_title("")

        fig.tight_layout()
        save_fig(fig, "fig_tod_annual_savings")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n── TOD Annual Best Hour Analysis ──")

    # Load data
    df_5min = load_5min()
    if ANALYSIS_YEARS:
        df_5min = df_5min[df_5min["year"].isin(ANALYSIS_YEARS)].copy()
        print(f"  Filtered to years: {ANALYSIS_YEARS}")

    # ── Best hours ───────────────────────────────────────────────────────────
    print("\n[1] Computing annual best hours...")
    derived_hours = compute_annual_best_hours(df_5min)

    # Apply overrides where specified
    best_hours = {}
    for region in CH3_REGIONS:
        override = ANNUAL_BEST_HOUR_OVERRIDE.get(region)
        if override is not None:
            best_hours[region] = override
            print(f"  {rshort(region):10s}  best hour = {override:02d}:00  [OVERRIDE from Table 3-3]")
        elif region in derived_hours:
            best_hours[region] = derived_hours[region]
        else:
            print(f"  ⚠ {region} excluded (no data + no override)")

    # ── Simulation ───────────────────────────────────────────────────────────
    print("\n[2] Running fixed-TOD simulation...")
    sim_df = simulate_fixed_tod(df_5min, best_hours)

    if sim_df.empty:
        print("  ✗ No simulation results — check data and best_hours.")
        return

    print(f"\n  Total region-days simulated: {len(sim_df):,}")

    # ── Summary table ────────────────────────────────────────────────────────
    print("\n[3] Building summary table...")
    summary = build_summary_table(sim_df)
    print(summary.to_string(index=False))
    save_table(summary, "table_tod_annual_savings",
               caption="Fixed Time-of-Day (Annual Best Hour) Scheduling: Savings vs. Baseline")

    # ── Figure ───────────────────────────────────────────────────────────────
    print("\n[4] Plotting...")
    plot_tod_savings(summary)

    export_numbers()
    print("\n✅ ch3_tod_annual.py complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)