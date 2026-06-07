"""
ch3_s3_constraints.py — Section 3.5 figures and tables.

Outputs:
    Figures:
        fig_3_8_duration_sensitivity.png/pdf — Savings vs job duration × region
        fig_3_9_flexibility_value.png/pdf    — Savings vs scheduling window (1–7 days)
    Tables:
        table_3_6_duration_savings.csv/md    — Average savings by job duration

Usage:
    python ch3_s3_constraints.py
    python ch3_s3_constraints.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, load_hourly,
    run_scheduling_sim, compute_thresholds, simulate_day,
    CH3_REGIONS, REGION_COLORS, REGION_MARKERS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    DURATION_SWEEP_HOURS, FLEXIBILITY_DAYS,
    TL_STRATEGY, ALL_TL_STRATEGIES,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ FIGURE CONFIG ▼▼▼
# =============================================================================

FIG_3_8 = {
    "figsize":        (9, 5),
    "linewidth":      2.0,
    "marker_size":    7,
    "title":          "",
    "xlabel":         "Job Duration (hours)",
    "ylabel":         "Traffic Light Savings (%)",
    # Vertical annotation lines for manufacturing examples
    "annotate_examples": True,
    "examples": {
        0.5: "CNC cycle",
        2.0: "AM print",
        8.0: "Full shift",
    },
    "example_color":  "#999999",
    "example_ls":     ":",
}

FIG_3_9 = {
    "figsize":        (9, 5),
    "linewidth":      2.0,
    "marker_size":    7,
    "title":          "",
    "xlabel":         "Scheduling Window (days)",
    "ylabel":         "Additional Savings vs. Single-Day (%)",
}

# ▲▲▲ END FIGURE CONFIG ▲▲▲
# =============================================================================


# =============================================================================
# DURATION SENSITIVITY ANALYSIS
# =============================================================================

def sweep_durations(
    df_5min: pd.DataFrame,
    thresholds: pd.DataFrame,
    recompute: bool = False,
) -> pd.DataFrame:
    """
    Run scheduling sim for each duration in DURATION_SWEEP_HOURS.
    Returns DataFrame with columns: region, duration_h, savings_tl_pct, savings_optimal_pct.
    """
    print("\n── Duration sensitivity sweep ──")
    
    cache_tag = "s3_duration_sweep"
    if not recompute:
        cached = load_cache(cache_tag, {"durations": DURATION_SWEEP_HOURS})
        if cached is not None:
            return cached
    
    all_results = []
    
    for dur in DURATION_SWEEP_HOURS:
        print(f"  Simulating {dur}h jobs...")
        sim = run_scheduling_sim(
            df_5min,
            job_duration_hours=dur,
            thresholds=thresholds,
            use_cache=False,     # don't cache each sub-run separately
            cache_tag=f"dur_{dur}",
        )
        
        # Aggregate per region
        for region in CH3_REGIONS:
            rd = sim[sim["region"] == region]
            if len(rd) == 0:
                continue
            all_results.append({
                "region":            region,
                "duration_h":        dur,
                "savings_tl_pct":    rd["savings_tl_pct"].mean(),
                "savings_fg_pct":    rd["savings_fg_pct"].mean(),
                "savings_pg_pct":    rd["savings_pg_pct"].mean(),
                "savings_bg_pct":    rd["savings_bg_pct"].mean(),
                "savings_mg_pct":    rd["savings_mg_pct"].mean(),
                "savings_optimal_pct": rd["savings_optimal_pct"].mean(),
                "capture_rate":      rd["capture_rate"].mean(),
                "n_days":            len(rd),
            })
    
    sweep_df = pd.DataFrame(all_results)
    save_cache(sweep_df, cache_tag, {"durations": DURATION_SWEEP_HOURS})
    
    return sweep_df


def plot_fig_3_8(sweep_df: pd.DataFrame):
    """Line plot: TL savings (%) vs duration for each region."""
    print("\n── Fig 3-8: Duration sensitivity ──")
    cfg = FIG_3_8
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        for region in CH3_REGIONS:
            rd = sweep_df[sweep_df["region"] == region].sort_values("duration_h")
            if len(rd) == 0:
                continue
            ax.plot(rd["duration_h"], rd["savings_tl_pct"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=cfg["marker_size"], linewidth=cfg["linewidth"],
                    label=rshort(region))
        
        # Manufacturing example annotations
        if cfg["annotate_examples"]:
            for dur, label in cfg["examples"].items():
                ax.axvline(dur, color=cfg["example_color"],
                           linestyle=cfg["example_ls"], linewidth=0.8)
                # Place label at top of plot area
                ax.text(dur, ax.get_ylim()[1] * 0.98, f" {label}",
                        fontsize=8, color=cfg["example_color"],
                        va="top", rotation=90, ha="left")
        
        ax.set_xlabel(cfg["xlabel"])
        ax.set_ylabel(cfg["ylabel"])
        ax.set_xticks(DURATION_SWEEP_HOURS)
        ax.legend(loc="upper right", fontsize=9)
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_8_duration_sensitivity")
    
    return fig


def build_table_3_6(sweep_df: pd.DataFrame) -> pd.DataFrame:
    """Average scheduling savings by job duration across all regions."""
    print("\n── Table 3-6: Duration savings ──")
    
    examples = {0.5: "Oil pump CNC cycle", 1.0: "Short batch job",
                2.0: "AM print / medium batch", 4.0: "Half-shift batch",
                8.0: "Full-shift continuous process"}
    
    # Average across all regions for each duration
    avg = sweep_df.groupby("duration_h").agg({
        "savings_tl_pct":      "mean",
        "savings_optimal_pct": "mean",
    }).reset_index()
    
    # Retained % relative to 0.5h
    ref_savings = avg.loc[avg["duration_h"] == 0.5, "savings_tl_pct"].values
    ref_val = ref_savings[0] if len(ref_savings) > 0 else 1.0
    
    rows = []
    for _, r in avg.iterrows():
        dur = r["duration_h"]
        retained = r["savings_tl_pct"] / ref_val * 100 if ref_val > 0 else 100
        rows.append({
            "Duration":              f"{dur:.1f} h",
            "Avg Savings (%)":       round(r["savings_tl_pct"], 1),
            "Manufacturing Example": examples.get(dur, ""),
            "Savings Retained (%)":  round(retained, 0),
        })
        record_number("Table 3-6", f"{dur}h avg savings %",
                      r["savings_tl_pct"], ".1f")
    
    table = pd.DataFrame(rows)
    save_table(table, "table_3_6_duration_savings",
               "Table 3-6. Average scheduling savings by job duration across all regions.")
    return table


# =============================================================================
# FLEXIBILITY VALUE (MULTI-DAY SCHEDULING)
# =============================================================================

def analyze_flexibility(
    df_5min: pd.DataFrame,
    thresholds: pd.DataFrame,
    recompute: bool = False,
) -> pd.DataFrame:
    """
    Compare savings with 1-day vs N-day scheduling windows.
    
    For each region, for each sliding N-day window:
    - 1-day baseline: best green-start 2h window within each day, averaged
    - N-day flexible: pick the best single day in the window
    
    Reports the incremental savings from multi-day flexibility.
    """
    print("\n── Flexibility value analysis ──")
    
    cache_tag = "s3_flexibility"
    if not recompute:
        cached = load_cache(cache_tag, {"days": FLEXIBILITY_DAYS})
        if cached is not None:
            return cached
    
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    thresh_dict = {
        row["region"]: (row["green_threshold"], row["red_threshold"])
        for _, row in thresholds.iterrows()
    }
    
    results = []
    
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        green_t, red_t = thresh_dict[region]
        
        rd = df_5min[
            (df_5min["region"] == region) &
            (df_5min["hour"] >= DAY_SHIFT_START) &
            (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")
        
        dates = sorted(rd["date"].unique())
        
        # First compute single-day TL MOER for each date (the 1-day baseline)
        day_tl_moers = {}
        for date in dates:
            day_df = rd[rd["date"] == date].sort_values("point_time_local")
            values = day_df["value"].values
            if len(values) < job_intervals:
                continue
            # FIX: removed day_hours arg; select result key via TL_STRATEGY
            result = simulate_day(values, job_intervals, green_t, red_t)
            if result:
                tl_key = f"tl_{TL_STRATEGY}_moer"
                day_tl_moers[date] = result[tl_key]
        
        # For each flexibility window size
        for window in FLEXIBILITY_DAYS:
            window_savings = []
            
            for i in range(len(dates) - window + 1):
                window_dates = dates[i:i+window]
                
                # Single-day average (no flexibility)
                single_day_vals = [day_tl_moers[d] for d in window_dates
                                   if d in day_tl_moers]
                if len(single_day_vals) < window * 0.8:
                    continue
                single_day_mean = np.mean(single_day_vals)
                
                # Flexible: pick the best (lowest MOER) single day in the window
                if single_day_vals:
                    flexible_mean = np.min(single_day_vals)
                    
                    if single_day_mean > 0:
                        incremental = (single_day_mean - flexible_mean) / single_day_mean * 100
                    else:
                        incremental = 0
                    
                    window_savings.append(incremental)
            
            if window_savings:
                results.append({
                    "region":            region,
                    "flexibility_days":  window,
                    "mean_savings_pct":  np.mean(window_savings),
                    "std_savings_pct":   np.std(window_savings),
                    "n_windows":         len(window_savings),
                })
    
    flex_df = pd.DataFrame(results)
    save_cache(flex_df, cache_tag, {"days": FLEXIBILITY_DAYS})
    
    return flex_df


def plot_fig_3_9(flex_df: pd.DataFrame):
    """Line plot: additional savings from multi-day flexibility."""
    print("\n── Fig 3-9: Flexibility value ──")
    cfg = FIG_3_9
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        for region in CH3_REGIONS:
            rd = flex_df[flex_df["region"] == region].sort_values("flexibility_days")
            if len(rd) == 0:
                continue
            ax.plot(rd["flexibility_days"], rd["mean_savings_pct"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=cfg["marker_size"], linewidth=cfg["linewidth"],
                    label=rshort(region))
            # Optional: error bands
            ax.fill_between(
                rd["flexibility_days"],
                rd["mean_savings_pct"] - rd["std_savings_pct"],
                rd["mean_savings_pct"] + rd["std_savings_pct"],
                alpha=0.1, color=rcolor(region),
            )
        
        ax.set_xlabel(cfg["xlabel"])
        ax.set_ylabel(cfg["ylabel"])
        ax.set_xticks(FLEXIBILITY_DAYS)
        ax.legend(loc="upper left", fontsize=9)
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_9_flexibility_value")
    
    return fig


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    
    df_5min = load_5min()
    thresholds = compute_thresholds(df_5min)
    
    # --- Duration sensitivity ---
    sweep_df = sweep_durations(df_5min, thresholds, recompute=recompute)
    plot_fig_3_8(sweep_df)
    build_table_3_6(sweep_df)
    
    # --- Flexibility value ---
    flex_df = analyze_flexibility(df_5min, thresholds, recompute=recompute)
    plot_fig_3_9(flex_df)
    
    export_numbers()
    print("\n✅ Section 3.5 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)