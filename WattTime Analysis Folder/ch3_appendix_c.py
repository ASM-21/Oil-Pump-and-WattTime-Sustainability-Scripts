"""
ch3_appendix_c.py — Appendix C supplementary figures and tables.

The chapter references "Appendix C" for:
  1. Green window duration distributions
  2. State transition probabilities (green↔yellow↔red)
  3. Year-over-year stability detail by region-season
  4. Shift-constrained savings by region

Outputs:
    Figures (individual panels for PowerPoint assembly):
        app_c_green_duration_{region}.png/pdf
        app_c_transitions_{region}.png/pdf
        app_c_stability_heatmap.png/pdf
        app_c_shift_savings.png/pdf
    Tables:
        app_c_green_window_stats.csv/md
        app_c_transition_matrix.csv/md
        app_c_stability_detail.csv/md
        app_c_shift_savings.csv/md

Usage:
    python ch3_appendix_c.py
    python ch3_appendix_c.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_panel, save_table, record_number, export_numbers,
    load_5min,
    run_scheduling_sim, compute_thresholds, simulate_day,
    compute_stability_scores, analyze_green_windows,
    CH3_REGIONS, REGION_COLORS, TRAFFIC_LIGHT_COLORS,
    SEASON_ORDER, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR,
)


# =============================================================================
# ▼▼▼ FIGURE CONFIG ▼▼▼
# =============================================================================

FIG_GREEN_DUR = {
    "figsize":  (7, 4),
    "bins":     30,
    "xlabel":   "Green Window Duration (hours)",
    "ylabel":   "Count",
}

FIG_TRANSITIONS = {
    "figsize": (5, 4),
    "cmap":    "YlGnBu",
}

FIG_STABILITY = {
    "figsize": (8, 4),
    "cmap":    "RdYlGn",
    "vmin":    0.3,
    "vmax":    1.0,
}

FIG_SHIFT = {
    "figsize": (9, 5),
}

# ▲▲▲ END FIGURE CONFIG ▲▲▲
# =============================================================================


# =============================================================================
# 1. GREEN WINDOW DURATION DISTRIBUTIONS (per region)
# =============================================================================

def plot_green_durations(df_5min: pd.DataFrame, thresholds: pd.DataFrame):
    """Histogram of continuous green window durations for each region."""
    print("\n── Appendix C: Green window duration distributions ──")
    cfg = FIG_GREEN_DUR
    
    thresh_dict = {r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()}
    
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        gt = thresh_dict[region]
        rd = df_5min[df_5min["region"] == region].sort_values("point_time_local").copy()
        rd["is_green"] = rd["value"] <= gt
        
        # Collect all green window durations
        durations = []
        for _, day_df in rd.groupby("date"):
            rl = 0
            for g in day_df["is_green"].values:
                if g:
                    rl += 1
                else:
                    if rl > 0:
                        durations.append(rl / INTERVALS_PER_HOUR)
                    rl = 0
            if rl > 0:
                durations.append(rl / INTERVALS_PER_HOUR)
        
        if not durations:
            continue
        
        durations = np.array(durations)
        
        with thesis_style():
            fig, ax = plt.subplots(figsize=cfg["figsize"])
            ax.hist(durations, bins=cfg["bins"], color=rcolor(region),
                    alpha=0.7, edgecolor="white")
            
            # Mark 2-hour threshold
            ax.axvline(2.0, color="#d62728", linestyle="--", linewidth=1.5)
            pct_gt2 = (durations >= 2).mean() * 100
            ax.text(2.1, ax.get_ylim()[1] * 0.9,
                    f"{pct_gt2:.0f}% ≥ 2h", fontsize=10, color="#d62728")
            
            ax.set_xlabel(cfg["xlabel"])
            ax.set_ylabel(cfg["ylabel"])
            ax.set_title(f"{rlabel(region)}", fontweight="bold")
            
            save_panel(fig, "app_c_green_duration", rshort(region))


# =============================================================================
# 2. STATE TRANSITION PROBABILITIES
# =============================================================================

def compute_transitions(df_5min: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """
    Compute hour-to-hour transition probabilities between G/Y/R states.
    P(next_state | current_state) for each region.
    """
    print("\n── Appendix C: State transitions ──")
    
    thresh_dict = {
        r["region"]: (r["green_threshold"], r["red_threshold"])
        for _, r in thresholds.iterrows()
    }
    
    all_results = []
    
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        gt, rt = thresh_dict[region]
        
        rd = df_5min[df_5min["region"] == region].sort_values("point_time_local").copy()
        
        # Assign buckets
        rd["bucket"] = "yellow"
        rd.loc[rd["value"] <= gt, "bucket"] = "green"
        rd.loc[rd["value"] >= rt, "bucket"] = "red"
        
        # Compute transitions (consecutive 5-min intervals within same day)
        for _, day_df in rd.groupby("date"):
            buckets = day_df["bucket"].values
            for i in range(len(buckets) - 1):
                all_results.append({
                    "region":     region,
                    "from_state": buckets[i],
                    "to_state":   buckets[i + 1],
                })
    
    trans_df = pd.DataFrame(all_results)
    
    # Compute probabilities per region
    summary_rows = []
    for region in CH3_REGIONS:
        rd = trans_df[trans_df["region"] == region]
        if len(rd) == 0:
            continue
        
        for from_s in ["green", "yellow", "red"]:
            from_data = rd[rd["from_state"] == from_s]
            total = len(from_data)
            if total == 0:
                continue
            for to_s in ["green", "yellow", "red"]:
                count = len(from_data[from_data["to_state"] == to_s])
                summary_rows.append({
                    "region":      region,
                    "from":        from_s,
                    "to":          to_s,
                    "probability": count / total,
                    "count":       count,
                })
    
    summary = pd.DataFrame(summary_rows)
    save_table(summary, "app_c_transition_matrix",
               "Appendix C. State transition probabilities (5-min intervals).")
    return summary


def plot_transitions(trans_df: pd.DataFrame):
    """Heatmap of transition probabilities per region."""
    cfg = FIG_TRANSITIONS
    states = ["green", "yellow", "red"]
    
    for region in CH3_REGIONS:
        rd = trans_df[trans_df["region"] == region]
        if len(rd) == 0:
            continue
        
        # Build matrix
        matrix = np.zeros((3, 3))
        for i, fs in enumerate(states):
            for j, ts in enumerate(states):
                row = rd[(rd["from"] == fs) & (rd["to"] == ts)]
                if len(row) > 0:
                    matrix[i, j] = row["probability"].values[0]
        
        with thesis_style():
            fig, ax = plt.subplots(figsize=cfg["figsize"])
            im = ax.imshow(matrix, cmap=cfg["cmap"], vmin=0, vmax=1, aspect="auto")
            
            ax.set_xticks(range(3))
            ax.set_yticks(range(3))
            ax.set_xticklabels([s.capitalize() for s in states])
            ax.set_yticklabels([s.capitalize() for s in states])
            ax.set_xlabel("Next State")
            ax.set_ylabel("Current State")
            ax.set_title(rshort(region), fontweight="bold")
            
            # Annotate
            for i in range(3):
                for j in range(3):
                    ax.text(j, i, f"{matrix[i,j]:.2f}",
                            ha="center", va="center", fontsize=11,
                            color="white" if matrix[i,j] > 0.5 else "black")
            
            fig.colorbar(im, ax=ax, label="P(transition)", shrink=0.8)
            save_panel(fig, "app_c_transitions", rshort(region))


# =============================================================================
# 3. STABILITY SCORE HEATMAP
# =============================================================================

def plot_stability_heatmap(stab_df: pd.DataFrame):
    """Heatmap: stability score by region × season."""
    print("\n── Appendix C: Stability heatmap ──")
    cfg = FIG_STABILITY
    
    pivot = stab_df.pivot(index="region", columns="season", values="stability_score")
    pivot = pivot.reindex(index=CH3_REGIONS.keys(), columns=SEASON_ORDER)
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        im = ax.imshow(pivot.values, cmap=cfg["cmap"],
                        vmin=cfg["vmin"], vmax=cfg["vmax"], aspect="auto")
        
        ax.set_xticks(range(len(SEASON_ORDER)))
        ax.set_xticklabels([s.capitalize() for s in SEASON_ORDER])
        ax.set_yticks(range(len(CH3_REGIONS)))
        ax.set_yticklabels([CH3_REGIONS[r]["archetype"] for r in CH3_REGIONS])
        
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                v = pivot.iloc[i, j]
                if pd.notna(v):
                    ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                            fontsize=10, fontweight="bold",
                            color="white" if v < 0.6 else "black")
        
        fig.colorbar(im, ax=ax, label="Stability Score (min Pearson r)",
                     shrink=0.8)
        save_fig(fig, "app_c_stability_heatmap")


# =============================================================================
# 4. SHIFT-CONSTRAINED SAVINGS
# =============================================================================

def analyze_shift_savings(df_5min: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """TL savings for 1st/2nd/3rd shift per region."""
    print("\n── Appendix C: Shift-constrained savings ──")
    
    shifts = {
        "1st (07–15)": (7, 15),
        "2nd (15–23)": (15, 23),
        "3rd (23–07)": (23, 7),
    }
    
    ji = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"]) for _, r in thresholds.iterrows()}
    # FIX: resolve result key once based on TL_STRATEGY
    tl_key = "tl_first_green_moer" if TL_STRATEGY == "first_green" else "tl_mean_green_moer"
    
    results = []
    for shift_name, (ss, se) in shifts.items():
        for region in CH3_REGIONS:
            if region not in td: continue
            gt, rt = td[region]
            rd = df_5min[df_5min["region"] == region].copy()
            
            if ss > se:  # crosses midnight
                sd = rd[(rd["hour"] >= ss) | (rd["hour"] < se)]
            else:
                sd = rd[(rd["hour"] >= ss) & (rd["hour"] < se)]
            
            daily_sav = []
            for _, ddf in sd.groupby("date"):
                ddf = ddf.sort_values("point_time_local")
                # FIX: removed day_hours arg; use tl_key instead of hardcoded key
                r = simulate_day(ddf["value"].values, ji, gt, rt)
                if r and r["baseline_moer"] > 0:
                    b  = r["baseline_moer"]
                    tl = r[tl_key]
                    daily_sav.append((b - tl) / b * 100)
            
            if daily_sav:
                results.append({
                    "shift": shift_name, "region": region,
                    "mean_savings_pct": np.mean(daily_sav),
                    "std_savings_pct":  np.std(daily_sav),
                    "n_days":           len(daily_sav),
                })
    
    shift_df = pd.DataFrame(results)
    save_table(shift_df, "app_c_shift_savings",
               "Appendix C. Shift-constrained traffic light savings.")
    
    # Summary for Section 3.5.3 prose
    if len(shift_df) > 0:
        for shift_name in shifts:
            sd = shift_df[shift_df["shift"] == shift_name]
            if len(sd) > 0:
                record_number("Section 3.5.3",
                              f"{shift_name} mean TL savings %",
                              sd["mean_savings_pct"].mean(), ".1f")
    
    return shift_df


def plot_shift_savings(shift_df: pd.DataFrame):
    """Grouped bar: shift savings per region."""
    cfg = FIG_SHIFT
    
    if len(shift_df) == 0:
        print("  ⚠️  No shift data to plot")
        return
    
    shifts = sorted(shift_df["shift"].unique())
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        x = np.arange(len(CH3_REGIONS))
        w = 0.25
        
        for i, shift in enumerate(shifts):
            sd = shift_df[shift_df["shift"] == shift]
            vals = []
            for region in CH3_REGIONS:
                rd = sd[sd["region"] == region]
                vals.append(rd["mean_savings_pct"].values[0] if len(rd) > 0 else 0)
            
            ax.bar(x + i * w, vals, w, label=shift, edgecolor="white", linewidth=0.5)
        
        ax.set_xticks(x + w)
        ax.set_xticklabels([rshort(r) for r in CH3_REGIONS])
        ax.set_ylabel("Traffic Light Savings (%)")
        ax.legend(fontsize=9)
        
        save_fig(fig, "app_c_shift_savings")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    
    df_5min = load_5min()
    thresholds = compute_thresholds(df_5min)
    
    # 1. Green window durations
    gw_df = analyze_green_windows(df_5min, thresholds)
    save_table(gw_df, "app_c_green_window_stats",
               "Appendix C. Green window duration statistics.")
    plot_green_durations(df_5min, thresholds)
    
    # 2. State transitions
    trans_df = compute_transitions(df_5min, thresholds)
    plot_transitions(trans_df)
    
    # 3. Stability
    stab_df = compute_stability_scores(df_5min)
    save_table(stab_df.drop(columns=["best_hours_by_year"], errors="ignore"),
               "app_c_stability_detail",
               "Appendix C. Year-over-year stability scores.")
    plot_stability_heatmap(stab_df)
    
    # 4. Shift savings
    shift_df = analyze_shift_savings(df_5min, thresholds)
    plot_shift_savings(shift_df)
    
    export_numbers()
    print("\n✅ Appendix C complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)