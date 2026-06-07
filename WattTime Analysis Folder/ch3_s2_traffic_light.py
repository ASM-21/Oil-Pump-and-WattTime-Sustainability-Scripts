"""
ch3_s2_traffic_light.py — Section 3.4 figures and tables.

Outputs:
    Figures:
        fig_3_4_traffic_light_heatmap.png/pdf — P(green/yellow/red) by hour, 6 regions
        fig_3_5_savings_comparison.png/pdf    — Baseline vs TL vs Optimal + capture rate
        fig_3_6_threshold_vs_time.png/pdf     — Threshold rules vs time-based rules
        fig_3_7_holdout_validation.png/pdf    — Predicted vs actual (train→holdout)
        fig_spp_histogram.png/pdf             — SPP MOER distribution (bimodal)
    Tables:
        table_3_4_thresholds.csv/md           — Traffic light thresholds
        table_3_5_savings.csv/md              — Traffic light savings performance

Usage:
    python ch3_s2_traffic_light.py
    python ch3_s2_traffic_light.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy import stats as sp_stats

from ch3_common import (
    init, thesis_style, save_fig, save_panel, save_table, record_number, export_numbers,
    load_5min, load_hourly,
    run_scheduling_sim, compute_thresholds, simulate_day,
    compute_stability_scores, analyze_green_windows,
    compute_annual_tonnes, bootstrap_ci,
    CH3_REGIONS, REGION_COLORS, REGION_MARKERS,
    SEASON_ORDER, SEASON_COLORS, TRAFFIC_LIGHT_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    ALL_TL_STRATEGIES, PERSIST_INTERVALS,
    CHARACTERIZATION_YEARS, HOLDOUT_TRAIN_YEARS, HOLDOUT_TEST_YEARS,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, TABLES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ FIGURE CONFIG ▼▼▼
# =============================================================================

FIG_3_4 = {
    "figsize":       (14, 7),        # 6-panel layout (2×3 or 3×2)
    "layout":        (2, 3),         # (rows, cols) of subplots
    "title":         "",
    "xlabel":        "Hour of Day",
}

FIG_3_5 = {
    "figsize":       (10, 5),
    "bar_width":     0.3,
    "tl_color":       "#2ca02c",
    "optimal_color":  "#1f77b4",
    "title":          "",
    "ylabel":         "Carbon Savings (%)",
    "annotate_capture": True,        # show capture % above TL bars
}

FIG_3_6 = {
    "figsize":       (9, 6),
    "title":         "",
    "marker_size":   60,
}

FIG_3_7 = {
    "figsize":       (7, 6),
    "title":         "",
    "ref_line_color": "#cc0000",     # y = x perfect generalization
    "threshold_line": 0.8,           # 80% generalization threshold
    "threshold_color": "#999999",
}

FIG_SPP_HIST = {
    "figsize":       (8, 5),
    "bins":          80,
    "color":         REGION_COLORS["SPP_KANSAS"],
    "kde":           True,           # overlay KDE
    "title":         "",
    "xlabel":        f"MOER ({SIGNAL_UNIT})",
    "annotate_p25":  True,           # mark P25 threshold
    "annotate_valley": True,         # mark inter-modal valley (auto-detected)
}

FIG_STRATEGY_COMP = {
    "figsize":       (11, 5),
    "title":         "",
    "ylabel":        "Traffic Light Savings (%)",
    "strategy_colors": {
        "first_green":      "#d62728",   # red — shows failure clearly
        "persistent_green": "#2ca02c",   # green
        "best_green":       "#1f77b4",   # blue
        "mean_green":       "#ff7f0e",   # orange
    },
    "strategy_labels": {
        "first_green":      "First green",
        "persistent_green": f"Persistent green (≥{30} min)",
        "best_green":       "Best green (day lookahead)",
        "mean_green":       "Mean green",
    },
}

# ▲▲▲ END FIGURE CONFIG ▲▲▲
# =============================================================================


# =============================================================================
# TABLE 3-4: TRAFFIC LIGHT THRESHOLDS
# =============================================================================

def build_table_3_4(thresholds: pd.DataFrame) -> pd.DataFrame:
    """Format thresholds into thesis table — shows both scopes."""
    print("\n── Table 3-4: Traffic light thresholds ──")
    
    rows = []
    for region in CH3_REGIONS:
        t = thresholds[thresholds["region"] == region]
        if len(t) == 0:
            continue
        t = t.iloc[0]
        rows.append({
            "Archetype":         CH3_REGIONS[region]["archetype"],
            "Region":            rshort(region),
            f"Green ≤P{GREEN_PERCENTILE} (window)": f"≤{t['green_threshold']:,.0f}",
            "Yellow (IQR, window)": f"{t['green_threshold']:,.0f}–{t['red_threshold']:,.0f}",
            f"Red ≥P{RED_PERCENTILE} (window)":     f"≥{t['red_threshold']:,.0f}",
            f"Green ≤P{GREEN_PERCENTILE} (all hrs)": f"≤{t['green_threshold_allhours']:,.0f}",
            f"Red ≥P{RED_PERCENTILE} (all hrs)":     f"≥{t['red_threshold_allhours']:,.0f}",
        })
        record_number("Table 3-4", f"{rshort(region)} green (window)", t["green_threshold"], ".0f")
        record_number("Table 3-4", f"{rshort(region)} red (window)", t["red_threshold"], ".0f")
        record_number("Table 3-4", f"{rshort(region)} green (all hrs)", t["green_threshold_allhours"], ".0f")
        record_number("Table 3-4", f"{rshort(region)} red (all hrs)", t["red_threshold_allhours"], ".0f")
    
    table = pd.DataFrame(rows)
    save_table(table, "table_3_4_thresholds",
               "Table 3-4. Traffic light thresholds (operating window and all-hours).")
    return table


# =============================================================================
# TABLE 3-5 + FIG 3-5: TRAFFIC LIGHT SAVINGS
# =============================================================================

def build_table_3_5(sim_df: pd.DataFrame) -> pd.DataFrame:
    """Core results: baseline vs TL vs optimal, all strategies, with CIs."""
    print("\n── Table 3-5: Traffic light savings performance ──")
    
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        if len(rd) == 0:
            continue
        
        optimal_pct = rd["savings_optimal_pct"].mean()
        fg_pct      = rd["savings_fg_pct"].mean()
        pg_pct      = rd["savings_pg_pct"].mean()
        bg_pct      = rd["savings_bg_pct"].mean()
        mg_pct      = rd["savings_mg_pct"].mean()
        tl_pct      = rd["savings_tl_pct"].mean()  # canonical (per TL_STRATEGY)
        capture     = tl_pct / optimal_pct * 100 if optimal_pct > 0 else 100
        
        # Capture rates for each strategy
        cap_fg = fg_pct / optimal_pct * 100 if optimal_pct > 0 else 100
        cap_pg = pg_pct / optimal_pct * 100 if optimal_pct > 0 else 100
        cap_bg = bg_pct / optimal_pct * 100 if optimal_pct > 0 else 100
        cap_mg = mg_pct / optimal_pct * 100 if optimal_pct > 0 else 100
        
        # Bootstrap 95% CI on each strategy
        fg_ci = bootstrap_ci(rd["savings_fg_pct"].values)
        pg_ci = bootstrap_ci(rd["savings_pg_pct"].values)
        bg_ci = bootstrap_ci(rd["savings_bg_pct"].values)
        mg_ci = bootstrap_ci(rd["savings_mg_pct"].values)
        
        # CO₂ saved per 2 kWh (for canonical strategy)
        baseline_mean = rd["baseline_moer"].mean()
        tl_mean       = rd["traffic_light_moer"].mean()
        savings_moer  = baseline_mean - tl_mean
        co2_saved_g   = savings_moer * 2 / 1000 * 453.592
        
        rows.append({
            "Archetype":           CH3_REGIONS[region]["archetype"],
            "Region":              rshort(region),
            "Optimal (%)":         round(optimal_pct, 1),
            "First-Green (%)":     round(fg_pct, 1),
            "Persistent-Green (%)": round(pg_pct, 1),
            "Best-Green (%)":      round(bg_pct, 1),
            "Mean-Green (%)":      round(mg_pct, 1),
            "FG 95% CI":           f"({fg_ci[0]:.1f}, {fg_ci[1]:.1f})",
            "PG 95% CI":           f"({pg_ci[0]:.1f}, {pg_ci[1]:.1f})",
            "BG Capture (%)":      round(cap_bg, 0),
            "PG Capture (%)":      round(cap_pg, 0),
            "CO₂ Saved /2kWh (g)": round(co2_saved_g, 0),
        })
        
        s = rshort(region)
        record_number("Table 3-5", f"{s} optimal %", optimal_pct, ".1f")
        record_number("Table 3-5", f"{s} first-green %", fg_pct, ".1f")
        record_number("Table 3-5", f"{s} persistent-green %", pg_pct, ".1f")
        record_number("Table 3-5", f"{s} best-green %", bg_pct, ".1f")
        record_number("Table 3-5", f"{s} mean-green %", mg_pct, ".1f")
        record_number("Table 3-5", f"{s} FG 95% CI",
                      f"({fg_ci[0]:.1f}, {fg_ci[1]:.1f})")
        record_number("Table 3-5", f"{s} PG 95% CI",
                      f"({pg_ci[0]:.1f}, {pg_ci[1]:.1f})")
        record_number("Table 3-5", f"{s} BG capture %", cap_bg, ".0f")
        record_number("Table 3-5", f"{s} PG capture %", cap_pg, ".0f")
    
    table = pd.DataFrame(rows)
    save_table(table, "table_3_5_savings",
               f"Table 3-5. Traffic light savings — all strategies (canonical: {TL_STRATEGY}).")
    
    # Summary ranges for each strategy
    for strat, col in [("first-green", "First-Green (%)"),
                       ("persistent-green", "Persistent-Green (%)"),
                       ("best-green", "Best-Green (%)"),
                       ("mean-green", "Mean-Green (%)")]:
        vals = table[col]
        record_number("Section 3.4.3", f"{strat} savings range",
                      f"{vals.min():.1f}–{vals.max():.1f}%")
    
    # Capture rate ranges for PG and BG (the two recommended strategies)
    pg_caps = table["PG Capture (%)"]
    bg_caps = table["BG Capture (%)"]
    record_number("Section 3.4.3", "Persistent-green capture range",
                  f"{pg_caps.min():.0f}–{pg_caps.max():.0f}%")
    record_number("Section 3.4.3", "Best-green capture range",
                  f"{bg_caps.min():.0f}–{bg_caps.max():.0f}%")
    
    return table


def plot_fig_3_5(sim_df: pd.DataFrame):
    """Grouped bar: TL savings vs optimal savings, with capture rate annotated."""
    print("\n── Fig 3-5: Savings comparison ──")
    cfg = FIG_3_5
    
    # Aggregate per region
    agg = sim_df.groupby("region").agg({
        "savings_optimal_pct": "mean",
        "savings_tl_pct":      "mean",
    }).reindex(CH3_REGIONS.keys())
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        x = np.arange(len(agg))
        w = cfg["bar_width"]
        
        bars_o = ax.bar(x - w/2, agg["savings_optimal_pct"], w,
                        label="Optimal (perfect hindsight)", color=cfg["optimal_color"],
                        edgecolor="white", linewidth=0.5)
        bars_t = ax.bar(x + w/2, agg["savings_tl_pct"], w,
                        label="Traffic Light (P25 threshold)", color=cfg["tl_color"],
                        edgecolor="white", linewidth=0.5)
        
        # Annotate capture rate above TL bars
        if cfg["annotate_capture"]:
            for i, region in enumerate(agg.index):
                opt_sav = agg.loc[region, "savings_optimal_pct"]
                tl_sav  = agg.loc[region, "savings_tl_pct"]
                capture = tl_sav / opt_sav * 100 if opt_sav > 0 else 100
                ax.annotate(f"{capture:.0f}%\ncapture",
                            xy=(i + w/2, tl_sav),
                            xytext=(0, 8), textcoords="offset points",
                            ha="center", fontsize=8, fontweight="bold",
                            color=cfg["tl_color"])
        
        ax.set_xticks(x)
        ax.set_xticklabels([f"{rshort(r)}\n{CH3_REGIONS[r]['archetype']}"
                            for r in agg.index], fontsize=8)
        ax.set_ylabel(cfg["ylabel"])
        ax.legend(loc="upper left")
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_5_savings_comparison")
    
    return fig


# =============================================================================
# FIG 3-4: TRAFFIC LIGHT PROBABILITY HEATMAP
# =============================================================================

def plot_fig_3_4(df_5min: pd.DataFrame, thresholds: pd.DataFrame):
    """
    6-panel heatmap: for each region, show P(green), P(yellow), P(red) at each hour.
    """
    print("\n── Fig 3-4: Traffic light probability heatmap ──")
    cfg = FIG_3_4
    rows, cols = cfg["layout"]
    
    # Assign buckets to operating-window data
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].copy()
    
    window["bucket"] = "yellow"
    for _, t in thresholds.iterrows():
        mask = window["region"] == t["region"]
        window.loc[mask & (window["value"] <= t["green_threshold"]), "bucket"] = "green"
        window.loc[mask & (window["value"] >= t["red_threshold"]), "bucket"] = "red"
    
    with thesis_style():
        fig, axes = plt.subplots(rows, cols, figsize=cfg["figsize"], sharey=True)
        axes = axes.flatten()
        
        for idx, region in enumerate(CH3_REGIONS):
            ax = axes[idx]
            rd = window[window["region"] == region]
            
            # Compute probabilities by hour
            total_by_hour = rd.groupby("hour").size()
            probs = {}
            for bucket in ["green", "yellow", "red"]:
                bucket_by_hour = rd[rd["bucket"] == bucket].groupby("hour").size()
                probs[bucket] = (bucket_by_hour / total_by_hour).fillna(0)
            
            hours = sorted(rd["hour"].unique())
            bottom = np.zeros(len(hours))
            
            for bucket, color in TRAFFIC_LIGHT_COLORS.items():
                vals = [probs[bucket].get(h, 0) for h in hours]
                ax.bar(hours, vals, bottom=bottom, color=color, width=0.8,
                       edgecolor="white", linewidth=0.3)
                bottom += vals
            
            ax.set_title(CH3_REGIONS[region]["archetype"], fontsize=10,
                         fontweight="bold")
            ax.set_xlim(DAY_SHIFT_START - 0.5, DAY_SHIFT_END - 0.5)
            ax.set_ylim(0, 1)
            
            if idx >= (rows - 1) * cols:
                ax.set_xlabel(cfg["xlabel"])
            if idx % cols == 0:
                ax.set_ylabel("Probability")
        
        # Shared legend
        legend_elements = [
            Patch(facecolor=TRAFFIC_LIGHT_COLORS["green"],  label="Green (≤P25)"),
            Patch(facecolor=TRAFFIC_LIGHT_COLORS["yellow"], label="Yellow (IQR)"),
            Patch(facecolor=TRAFFIC_LIGHT_COLORS["red"],    label="Red (≥P75)"),
        ]
        fig.legend(handles=legend_elements, loc="lower center",
                   ncol=3, frameon=True, fontsize=10,
                   bbox_to_anchor=(0.5, -0.02))
        
        fig.tight_layout(rect=[0, 0.04, 1, 1])
        save_fig(fig, "fig_3_4_traffic_light_heatmap")
    
    return fig


# =============================================================================
# FIG 3-6: THRESHOLD VS TIME-BASED RULES
# =============================================================================

def analyze_threshold_vs_time(
    df_5min: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare threshold rules (start when MOER < P25) vs time-based rules
    (always start at historically best hour) for each region × season.
    
    Both use the 2h contiguous window methodology.
    """
    print("\n── Analyzing threshold vs time-based rules ──")
    
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    thresh_dict = {
        row["region"]: (row["green_threshold"], row["red_threshold"])
        for _, row in thresholds.iterrows()
    }
    
    results = []
    
    for region in CH3_REGIONS:
        green_t, red_t = thresh_dict[region]
        rd = df_5min[
            (df_5min["region"] == region) &
            (df_5min["hour"] >= DAY_SHIFT_START) &
            (df_5min["hour"] < DAY_SHIFT_END)
        ]
        
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) < 1000:
                continue
            
            # Find historically best starting hour for this season
            # (the hour whose mean 2h-window MOER is lowest)
            hourly_starts = sd.groupby("hour")["value"].mean()
            # Only hours where a full window fits: start + 2h < shift_end
            valid_hours = [h for h in hourly_starts.index
                           if h + REFERENCE_JOB_HOURS <= DAY_SHIFT_END]
            if not valid_hours:
                continue
            best_fixed_hour = min(valid_hours, key=lambda h: hourly_starts.get(h, 9999))
            
            # Simulate day by day
            time_moers = []
            threshold_moers = []
            baseline_moers = []
            
            for date, day_df in sd.groupby("date"):
                day_df = day_df.sort_values("point_time_local")
                values = day_df["value"].values
                hours = day_df["hour"].values
                
                if len(values) < job_intervals:
                    continue
                
                # Baseline: mean of all windows
                n_win = len(values) - job_intervals + 1
                cumsum = np.concatenate([[0], np.cumsum(values)])
                window_means = (cumsum[job_intervals:] - cumsum[:n_win]) / job_intervals
                baseline_moers.append(float(np.mean(window_means)))
                
                # Time-based: start at best_fixed_hour
                # Find the interval index where hour == best_fixed_hour
                hour_mask = hours[:n_win] == best_fixed_hour
                if np.any(hour_mask):
                    # Take first occurrence (start of that hour)
                    idx = np.where(hour_mask)[0][0]
                    time_moers.append(float(window_means[idx]))
                
                # Threshold: mean of green-start windows (same as canonical sim)
                start_moer = values[:n_win]
                green_mask = start_moer <= green_t
                if np.any(green_mask):
                    threshold_moers.append(float(np.mean(window_means[green_mask])))
                else:
                    yellow_mask = (start_moer > green_t) & (start_moer < red_t)
                    if np.any(yellow_mask):
                        threshold_moers.append(float(np.mean(window_means[yellow_mask])))
                    else:
                        threshold_moers.append(float(np.mean(window_means)))
            
            if not time_moers or not threshold_moers:
                continue
            
            base_mean      = np.mean(baseline_moers)
            time_mean      = np.mean(time_moers)
            thresh_mean    = np.mean(threshold_moers)
            
            time_sav = (base_mean - time_mean) / base_mean * 100 if base_mean > 0 else 0
            thresh_sav = (base_mean - thresh_mean) / base_mean * 100 if base_mean > 0 else 0
            
            results.append({
                "region":               region,
                "season":               season,
                "best_fixed_hour":      best_fixed_hour,
                "baseline_moer":        base_mean,
                "time_based_moer":      time_mean,
                "threshold_moer":       thresh_mean,
                "time_savings_pct":     time_sav,
                "threshold_savings_pct": thresh_sav,
                "threshold_advantage":  thresh_sav - time_sav,
                "winner":              "threshold" if thresh_sav > time_sav else "time",
            })
    
    df_results = pd.DataFrame(results)
    
    # Summary stats
    if len(df_results) > 0:
        thresh_wins = (df_results["winner"] == "threshold").mean() * 100
        avg_abs_advantage = df_results["threshold_advantage"].mean()
        # Relative advantage: how much better is threshold vs time, as % of time savings
        valid = df_results[df_results["time_savings_pct"] > 0]
        if len(valid) > 0:
            avg_rel_advantage = (
                (valid["threshold_savings_pct"] - valid["time_savings_pct"])
                / valid["time_savings_pct"]
            ).mean() * 100
        else:
            avg_rel_advantage = 0
        record_number("Section 3.4.3", "Threshold win rate %", thresh_wins, ".0f")
        record_number("Section 3.4.3",
                      "Threshold avg absolute advantage (pp)", avg_abs_advantage, ".1f")
        record_number("Section 3.4.3",
                      "Threshold avg relative advantage (%)", avg_rel_advantage, ".0f")
    
    return df_results


def plot_fig_3_6(tvt_df: pd.DataFrame):
    """Scatter: threshold vs time-based savings for each region-season."""
    print("\n── Fig 3-6: Threshold vs time-based comparison ──")
    cfg = FIG_3_6
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        # Plot each region with its color/marker
        for region in CH3_REGIONS:
            rd = tvt_df[tvt_df["region"] == region]
            if len(rd) == 0:
                continue
            ax.scatter(rd["time_savings_pct"], rd["threshold_savings_pct"],
                       c=rcolor(region), marker=rmarker(region),
                       s=cfg["marker_size"], label=rshort(region),
                       edgecolors="white", linewidth=0.5, zorder=3)
        
        # y = x line (equal performance)
        lims = [0, max(ax.get_xlim()[1], ax.get_ylim()[1]) * 1.05]
        ax.plot(lims, lims, "k--", linewidth=1, alpha=0.5, label="Equal performance")
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        
        ax.set_xlabel("Time-based rule savings (%)")
        ax.set_ylabel("Threshold rule savings (%)")
        ax.legend(loc="lower right", fontsize=9)
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        # Annotation: points above the line = threshold wins
        ax.text(0.05, 0.92, "Threshold wins ↑", transform=ax.transAxes,
                fontsize=10, fontstyle="italic", color="#555555")
        
        save_fig(fig, "fig_3_6_threshold_vs_time")
    
    return fig


# =============================================================================
# FIG 3-7: HOLDOUT VALIDATION
# =============================================================================

def analyze_holdout(
    df_5min: pd.DataFrame,
    thresholds_train: pd.DataFrame,
) -> pd.DataFrame:
    """
    Train thresholds on HOLDOUT_TRAIN_YEARS, test on HOLDOUT_TEST_YEARS.
    For each region-season: compare TL savings predicted by training data
    vs achieved on holdout data.
    """
    print("\n── Holdout validation (train → test) ──")
    
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    
    # Compute thresholds from training years only
    train_data = df_5min[df_5min["year"].isin(HOLDOUT_TRAIN_YEARS)]
    test_data  = df_5min[df_5min["year"].isin(HOLDOUT_TEST_YEARS)]
    
    train_thresholds = compute_thresholds(train_data)
    thresh_dict = {
        row["region"]: (row["green_threshold"], row["red_threshold"])
        for _, row in train_thresholds.iterrows()
    }
    
    results = []
    
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        green_t, red_t = thresh_dict[region]
        
        for season in SEASON_ORDER:
            # Training period savings
            train_season = train_data[
                (train_data["region"] == region) &
                (train_data["season"] == season) &
                (train_data["hour"] >= DAY_SHIFT_START) &
                (train_data["hour"] < DAY_SHIFT_END)
            ]
            
            # Test period savings
            test_season = test_data[
                (test_data["region"] == region) &
                (test_data["season"] == season) &
                (test_data["hour"] >= DAY_SHIFT_START) &
                (test_data["hour"] < DAY_SHIFT_END)
            ]
            
            if len(train_season) < 500 or len(test_season) < 200:
                continue
            
            # Helper: compute TL savings for a dataset.
            # Uses updated simulate_day signature (no day_hours arg).
            # Returns dict of savings by strategy.
            def _compute_tl_savings(data):
                daily_results = {s: [] for s in ALL_TL_STRATEGIES}
                for _, day_df in data.groupby("date"):
                    day_df = day_df.sort_values("point_time_local")
                    vals = day_df["value"].values
                    if len(vals) < job_intervals:
                        continue
                    result = simulate_day(vals, job_intervals, green_t, red_t)
                    if result is None:
                        continue
                    base = result["baseline_moer"]
                    if base <= 0:
                        continue
                    for strat in ALL_TL_STRATEGIES:
                        tl_val = result[f"tl_{strat}_moer"]
                        daily_results[strat].append((base - tl_val) / base * 100)
                # Return mean savings per strategy, or None if no data
                out = {}
                for strat in ALL_TL_STRATEGIES:
                    vals = daily_results[strat]
                    out[strat] = np.mean(vals) if vals else None
                return out
            
            train_results = _compute_tl_savings(train_season)
            test_results  = _compute_tl_savings(test_season)
            
            # Use canonical strategy for the holdout comparison
            train_sav = train_results.get(TL_STRATEGY)
            test_sav  = test_results.get(TL_STRATEGY)
            
            if train_sav is None or test_sav is None:
                continue
            
            gen_ratio = test_sav / train_sav if train_sav > 0 else 1.0
            abs_dev   = test_sav - train_sav
            
            row = {
                "region":               region,
                "season":               season,
                "train_savings_pct":    train_sav,
                "test_savings_pct":     test_sav,
                "generalization_ratio": gen_ratio,
                "absolute_deviation_pp": abs_dev,
                "generalizes_well":     gen_ratio >= 0.8,
            }
            # Also record all strategies for reference
            for strat in ALL_TL_STRATEGIES:
                row[f"train_{strat}_pct"] = train_results.get(strat)
                row[f"test_{strat}_pct"]  = test_results.get(strat)
            
            results.append(row)
    
    holdout_df = pd.DataFrame(results)
    
    if len(holdout_df) > 0:
        # Use median ratio (robust to near-zero denominators)
        median_ratio = holdout_df["generalization_ratio"].median()
        mean_ratio   = holdout_df["generalization_ratio"].mean()
        mean_abs_dev = holdout_df["absolute_deviation_pp"].mean()
        pct_good = holdout_df["generalizes_well"].mean() * 100
        pct_bad  = 100 - pct_good
        record_number("Section 3.4.4", "Median generalization ratio", median_ratio, ".2f")
        record_number("Section 3.4.4", "Mean generalization ratio", mean_ratio, ".2f")
        record_number("Section 3.4.4", "Mean absolute deviation (pp)", mean_abs_dev, ".2f")
        record_number("Section 3.4.4", "% combos ≥ 80% generalization", pct_good, ".0f")
        record_number("Section 3.4.4", "% combos degraded > 20%", pct_bad, ".0f")
        
        # Also report holdout for persistent-green
        pg_train = holdout_df["train_persistent_green_pct"].dropna()
        pg_test  = holdout_df["test_persistent_green_pct"].dropna()
        if len(pg_train) > 0 and len(pg_test) > 0:
            pg_ratios = pg_test.values / np.where(pg_train.values > 0, pg_train.values, 1.0)
            record_number("Section 3.4.4", "PG median generalization ratio",
                          np.median(pg_ratios), ".2f")
    
    return holdout_df


def plot_fig_3_7(holdout_df: pd.DataFrame):
    """Scatter: training savings vs holdout savings by region-season."""
    print("\n── Fig 3-7: Holdout validation ──")
    cfg = FIG_3_7
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        for region in CH3_REGIONS:
            rd = holdout_df[holdout_df["region"] == region]
            if len(rd) == 0:
                continue
            ax.scatter(rd["train_savings_pct"], rd["test_savings_pct"],
                       c=rcolor(region), marker=rmarker(region),
                       s=70, label=rshort(region),
                       edgecolors="white", linewidth=0.5, zorder=3)
        
        # Reference lines
        max_val = max(ax.get_xlim()[1], ax.get_ylim()[1]) * 1.05
        ax.plot([0, max_val], [0, max_val], color=cfg["ref_line_color"],
                linestyle="-", linewidth=1.5, alpha=0.7,
                label="Perfect generalization")
        ax.plot([0, max_val], [0, max_val * cfg["threshold_line"]],
                color=cfg["threshold_color"], linestyle="--", linewidth=1,
                alpha=0.6, label=f"{cfg['threshold_line']:.0%} threshold")
        
        ax.set_xlim(0, max_val)
        ax.set_ylim(0, max_val)
        ax.set_xlabel("Training period savings (%)")
        ax.set_ylabel("Holdout period savings (%)")
        ax.legend(loc="lower right", fontsize=9)
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_7_holdout_validation")
    
    return fig


# =============================================================================
# FIG 3-5B: STRATEGY COMPARISON (grouped bar — all 4 strategies)
# =============================================================================

def plot_strategy_comparison(sim_df: pd.DataFrame):
    """Grouped bar chart comparing all 4 TL strategies across regions."""
    print("\n── Fig 3-5b: Strategy comparison ──")
    cfg = FIG_STRATEGY_COMP
    
    strategies = [
        ("savings_fg_pct", "first_green"),
        ("savings_pg_pct", "persistent_green"),
        ("savings_bg_pct", "best_green"),
        ("savings_mg_pct", "mean_green"),
    ]
    
    # Aggregate per region
    agg = {}
    for col, strat in strategies:
        agg[strat] = sim_df.groupby("region")[col].mean().reindex(CH3_REGIONS.keys())
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        n_regions = len(CH3_REGIONS)
        n_strats = len(strategies)
        total_bar_width = 0.75
        bar_w = total_bar_width / n_strats
        x = np.arange(n_regions)
        
        for j, (col, strat) in enumerate(strategies):
            offset = (j - n_strats / 2 + 0.5) * bar_w
            vals = agg[strat].values
            ax.bar(x + offset, vals, bar_w,
                   label=cfg["strategy_labels"][strat],
                   color=cfg["strategy_colors"][strat],
                   edgecolor="white", linewidth=0.5)
        
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{rshort(r)}\n{CH3_REGIONS[r]['archetype']}"
                            for r in CH3_REGIONS], fontsize=8)
        ax.set_ylabel(cfg["ylabel"])
        ax.legend(loc="upper left", fontsize=9)
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_5b_strategy_comparison")
    
    return fig


# =============================================================================
# SPP HISTOGRAM (BIMODAL DISTRIBUTION)
# =============================================================================

def plot_spp_histogram(df_5min: pd.DataFrame):
    """
    MOER distribution for SPP_KANSAS showing bimodality.
    Auto-detects the inter-modal valley from KDE local minimum.
    """
    print("\n── SPP MOER histogram (bimodal) ──")
    cfg = FIG_SPP_HIST
    
    spp = df_5min[
        (df_5min["region"] == "SPP_KANSAS") &
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]["value"].dropna()
    
    p25 = spp.quantile(GREEN_PERCENTILE / 100)
    record_number("Fig SPP", "SPP P25 threshold", p25, ".0f")
    
    # Auto-detect inter-modal valley via KDE
    from scipy.stats import gaussian_kde
    from scipy.signal import argrelmin
    
    kde = gaussian_kde(spp, bw_method=0.05)
    x_kde = np.linspace(spp.min(), spp.max(), 1000)
    y_kde = kde(x_kde)
    
    valley_x = None
    if cfg["annotate_valley"]:
        # Find local minima in KDE
        local_mins = argrelmin(y_kde, order=50)[0]  # order controls smoothness
        if len(local_mins) > 0:
            # Pick the valley between the two largest modes
            # Filter to reasonable range (between 200 and 1200)
            candidates = [x_kde[m] for m in local_mins
                          if 200 < x_kde[m] < 1200]
            if candidates:
                valley_x = candidates[0]  # first valley in range
                record_number("Fig SPP", "SPP inter-modal valley", valley_x, ".0f")
            else:
                print("  ⚠️  Could not auto-detect valley; check KDE plot")
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        # Histogram
        ax.hist(spp, bins=cfg["bins"], density=True, color=cfg["color"],
                alpha=0.6, edgecolor="white", linewidth=0.3)
        
        # KDE overlay
        if cfg["kde"]:
            ax.plot(x_kde, y_kde, color=cfg["color"], linewidth=2)
        
        # P25 line
        if cfg["annotate_p25"]:
            ax.axvline(p25, color="#d62728", linewidth=2, linestyle="--")
            ax.annotate(f"P25 = {p25:.0f}",
                        xy=(p25, ax.get_ylim()[1] * 0.85),
                        xytext=(p25 + 80, ax.get_ylim()[1] * 0.9),
                        fontsize=10, color="#d62728", fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color="#d62728"))
        
        # Inter-modal valley
        if valley_x is not None:
            ax.axvline(valley_x, color="#555555", linewidth=1.5, linestyle=":")
            ax.annotate(f"Valley ≈ {valley_x:.0f}",
                        xy=(valley_x, ax.get_ylim()[1] * 0.6),
                        xytext=(valley_x + 120, ax.get_ylim()[1] * 0.7),
                        fontsize=10, color="#555555",
                        arrowprops=dict(arrowstyle="->", color="#555555"))
        
        ax.set_xlabel(cfg["xlabel"])
        ax.set_ylabel("Density")
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_spp_histogram")
    
    return fig


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    
    # Load data
    df_5min   = load_5min()
    df_hourly = load_hourly()
    
    # Compute canonical thresholds (full dataset, operating window)
    thresholds = compute_thresholds(df_5min)
    
    # --- Table 3-4 ---
    build_table_3_4(thresholds)
    
    # --- Core simulation (full dataset) ---
    sim_df = run_scheduling_sim(
        df_5min, thresholds=thresholds,
        use_cache=not recompute, cache_tag="s2_traffic_light",
    )
    
    # --- Table 3-5 + Fig 3-5 ---
    build_table_3_5(sim_df)
    plot_fig_3_5(sim_df)
    
    # --- Fig 3-5b: Strategy comparison (all 4 strategies) ---
    plot_strategy_comparison(sim_df)
    
    # --- Fig 3-4: traffic light heatmap ---
    plot_fig_3_4(df_5min, thresholds)
    
    # --- Green window duration analysis (Section 3.4.2 claims) ---
    # FIX: was incorrectly passing df_hourly; analyze_green_windows requires 5-min data
    gw_df = analyze_green_windows(df_5min, thresholds)
    save_table(gw_df, "green_window_durations",
               "Green window duration statistics by region.")
    
    # --- Year-over-year stability scoring (Section 3.2.2 / 3.4.4) ---
    # Using df_5min for correct Pearson correlation resolution
    stability_df = compute_stability_scores(df_5min)
    save_table(stability_df, "stability_scores",
               "Year-over-year diurnal profile stability scores.")
    
    # --- Fig 3-6: threshold vs time-based ---
    tvt_df = analyze_threshold_vs_time(df_5min, thresholds)
    plot_fig_3_6(tvt_df)
    
    # --- Fig 3-7: holdout validation ---
    holdout_df = analyze_holdout(df_5min, thresholds)
    plot_fig_3_7(holdout_df)
    
    # --- SPP histogram ---
    plot_spp_histogram(df_5min)
    
    export_numbers()
    print("\n✅ Section 3.4 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)