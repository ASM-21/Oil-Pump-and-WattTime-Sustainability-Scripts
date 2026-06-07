"""
ch3_s1_grid_characterization.py — Section 3.3 figures and tables.

Outputs:
    Figures:
        fig_3_1_diurnal_profiles.png/pdf   — Mean diurnal MOER ± 1σ, all 6 regions
        fig_3_2_representative_week.png/pdf — Raw 5-min MOER for CAISO/MISO/SPP, 1 week
        fig_3_3_optimal_hour_heatmap.png/pdf — Optimal hour by region × season
    Tables:
        table_3_2_archetype_metrics.csv/md  — Baseline vs optimal scheduling metrics
        table_3_3_optimal_hours.csv/md      — Optimal hour by archetype × season

Usage:
    python ch3_s1_grid_characterization.py
    python ch3_s1_grid_characterization.py --recompute   # ignore cache
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Patch

from ch3_common import (
    init, thesis_style, save_fig, save_panel, save_table, record_number, export_numbers,
    load_5min, load_hourly,
    run_scheduling_sim, compute_thresholds,
    CH3_REGIONS, REGION_COLORS, REGION_MARKERS, SEASON_ORDER, SEASON_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS,
    CHARACTERIZATION_YEARS, REP_WEEK_START,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR,
)


# =============================================================================
# ▼▼▼ FIGURE CONFIG — edit these dicts to tweak figures ▼▼▼
# =============================================================================

FIG_3_1 = {
    "figsize":       (12, 8),
    "ylim":          None,          # None = auto, or (low, high)
    "band_alpha":    0.15,          # ±1σ shading opacity
    "show_shifts":   True,          # vertical lines at shift boundaries
    "shift_hours":   [6, 18],       # which hours to mark
    "shift_color":   "#999999",
    "shift_ls":      "--",
    "linewidth":     2.0,
    "title":         "",            # empty = no title (thesis convention)
    "xlabel":        "Hour of Day (Local Time)",
    "ylabel":        f"MOER ({SIGNAL_UNIT})",
    # Layout: "overlay" = all 6 on one axes (cluttered with σ bands)
    #         "faceted" = 2×3 panels, one per archetype (recommended for thesis)
    "layout":        "faceted",     # ← "overlay" or "faceted"
    "facet_grid":    (2, 3),        # rows × cols for faceted layout
    "shared_ylim":   True,          # use same y-axis across all panels
}

# Fig 3-2: three-panel representative week
FIG_3_2 = {
    "figsize":       (12, 8),       # for 3 stacked subplots
    "regions":       ["CAISO_NORTH", "MISO_INDIANAPOLIS", "SPP_KANSAS"],
    "linewidth":     0.4,           # thin line for raw 5-min data
    "line_alpha":    0.9,
    "night_color":   "#e8e8e8",     # day/night shading
    "night_alpha":   0.4,
    "night_start":   18,            # shade from 18:00 to 06:00
    "night_end":     6,
    "title":         "",
    "ylabel":        f"MOER ({SIGNAL_UNIT})",
}

# Fig 3-3: heatmap
FIG_3_3 = {
    "figsize":       (7, 4),
    "cmap":          "twilight_shifted",  # circular colormap for hours
    "title":         "",
    "annotate":      True,           # show hour values in cells
    "annot_size":    10,
}

# ▲▲▲ END FIGURE CONFIG ▲▲▲
# =============================================================================


# =============================================================================
# FIG 3-1: MEAN DIURNAL MOER PROFILES ± 1σ
# =============================================================================

def plot_fig_3_1(df_hourly: pd.DataFrame):
    """
    Average diurnal MOER profiles for all six study regions with ±1σ bands.
    Supports "overlay" (all on one axes) or "faceted" (2×3 panels) layout.
    """
    print("\n── Fig 3-1: Diurnal MOER profiles ──")
    cfg = FIG_3_1
    
    # Pre-compute stats for all regions
    region_stats = {}
    global_min, global_max = 9999, 0
    for region in CH3_REGIONS:
        rd = df_hourly[df_hourly["region"] == region]
        if len(rd) == 0:
            continue
        hourly = rd.groupby("hour")["value_mean"].agg(["mean", "std"])
        region_stats[region] = hourly
        ymin = (hourly["mean"] - hourly["std"]).min()
        ymax = (hourly["mean"] + hourly["std"]).max()
        global_min = min(global_min, ymin)
        global_max = max(global_max, ymax)
        
        diurnal_range = hourly["mean"].max() - hourly["mean"].min()
        record_number("Table 3-2", f"{rshort(region)} diurnal range",
                      diurnal_range, ".0f")
        record_number("Table 3-2", f"{rshort(region)} mean MOER",
                      hourly["mean"].mean(), ".0f")
    
    with thesis_style():
        if cfg["layout"] == "faceted":
            rows, cols = cfg["facet_grid"]
            fig, axes = plt.subplots(rows, cols, figsize=cfg["figsize"],
                                     sharex=True, sharey=cfg["shared_ylim"])
            axes_flat = axes.flatten()
            
            for idx, region in enumerate(CH3_REGIONS):
                ax = axes_flat[idx]
                if region not in region_stats:
                    continue
                
                hourly = region_stats[region]
                hours = hourly.index
                color = rcolor(region)
                
                ax.plot(hours, hourly["mean"], color=color,
                        linewidth=cfg["linewidth"])
                ax.fill_between(hours,
                                hourly["mean"] - hourly["std"],
                                hourly["mean"] + hourly["std"],
                                alpha=cfg["band_alpha"], color=color)
                
                if cfg["show_shifts"]:
                    for h in cfg["shift_hours"]:
                        ax.axvline(h, color=cfg["shift_color"],
                                   linestyle=cfg["shift_ls"], linewidth=0.8,
                                   alpha=0.5)
                
                ax.set_xlim(0, 23)
                ax.set_xticks(range(0, 24, 6))
                ax.set_title(CH3_REGIONS[region]["archetype"], fontsize=10,
                             fontweight="bold", color=color)
                
                # Y-label only on left column
                if idx % cols == 0:
                    ax.set_ylabel(cfg["ylabel"], fontsize=9)
                # X-label only on bottom row
                if idx >= (rows - 1) * cols:
                    ax.set_xlabel(cfg["xlabel"], fontsize=9)
            
            fig.tight_layout()
        
        else:
            # Overlay layout (original)
            fig, ax = plt.subplots(figsize=cfg["figsize"])
            
            for region in CH3_REGIONS:
                if region not in region_stats:
                    continue
                hourly = region_stats[region]
                hours = hourly.index
                color = rcolor(region)
                ax.plot(hours, hourly["mean"], color=color,
                        linewidth=cfg["linewidth"], label=rlabel(region),
                        marker=rmarker(region), markersize=4, markevery=3)
                ax.fill_between(hours,
                                hourly["mean"] - hourly["std"],
                                hourly["mean"] + hourly["std"],
                                alpha=cfg["band_alpha"], color=color)
            
            if cfg["show_shifts"]:
                for h in cfg["shift_hours"]:
                    ax.axvline(h, color=cfg["shift_color"],
                               linestyle=cfg["shift_ls"], linewidth=0.8, alpha=0.6)
            
            ax.set_xlabel(cfg["xlabel"])
            ax.set_ylabel(cfg["ylabel"])
            if cfg["ylim"]:
                ax.set_ylim(cfg["ylim"])
            ax.set_xlim(0, 23)
            ax.set_xticks(range(0, 24, 3))
            ax.legend(loc="upper right", framealpha=0.9)
        
        if cfg["title"]:
            fig.suptitle(cfg["title"])
        
        save_fig(fig, "fig_3_1_diurnal_profiles")
    
    return fig


# =============================================================================
# FIG 3-2: REPRESENTATIVE WEEK — RAW 5-MIN DATA
# =============================================================================

def plot_fig_3_2(df_5min: pd.DataFrame):
    """
    Raw 5-minute MOER for one week, three contrasting archetypes.
    Day/night shading shows diurnal structure (or lack thereof).
    """
    print("\n── Fig 3-2: Representative week ──")
    cfg = FIG_3_2
    
    week_start = pd.Timestamp(REP_WEEK_START)
    week_end   = week_start + pd.Timedelta(days=7)
    
    with thesis_style():
        fig, axes = plt.subplots(len(cfg["regions"]), 1, figsize=cfg["figsize"],
                                 sharex=True)
        if len(cfg["regions"]) == 1:
            axes = [axes]
        
        for ax, region in zip(axes, cfg["regions"]):
            rd = df_5min[
                (df_5min["region"] == region) &
                (df_5min["point_time_local"] >= week_start) &
                (df_5min["point_time_local"] < week_end)
            ].sort_values("point_time_local")
            
            if len(rd) == 0:
                ax.text(0.5, 0.5, f"No data for {rshort(region)} in {REP_WEEK_START}",
                        transform=ax.transAxes, ha="center")
                continue
            
            # Plot raw 5-min trace
            ax.plot(rd["point_time_local"], rd["value"],
                    color=rcolor(region), linewidth=cfg["linewidth"],
                    alpha=cfg["line_alpha"])
            
            # Day/night shading
            for day_offset in range(7):
                day = week_start + pd.Timedelta(days=day_offset)
                # Night: previous evening to morning
                night_start_prev = day + pd.Timedelta(hours=cfg["night_start"]) - pd.Timedelta(days=1)
                night_end_morn   = day + pd.Timedelta(hours=cfg["night_end"])
                night_start_eve  = day + pd.Timedelta(hours=cfg["night_start"])
                night_end_next   = day + pd.Timedelta(days=1, hours=cfg["night_end"])
                
                # Morning night period (00:00 to 06:00)
                ax.axvspan(day, night_end_morn,
                           color=cfg["night_color"], alpha=cfg["night_alpha"],
                           zorder=0)
                # Evening night period (18:00 to 00:00)
                ax.axvspan(night_start_eve,
                           min(night_start_eve + pd.Timedelta(hours=24 - cfg["night_start"]), week_end),
                           color=cfg["night_color"], alpha=cfg["night_alpha"],
                           zorder=0)
            
            ax.set_ylabel(cfg["ylabel"], fontsize=10)
            ax.text(0.02, 0.92, rlabel(region), transform=ax.transAxes,
                    fontsize=11, fontweight="bold", va="top",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                              edgecolor=rcolor(region), alpha=0.9))
        
        # X-axis formatting on bottom panel only
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%a %m/%d"))
        axes[-1].xaxis.set_major_locator(mdates.DayLocator())
        axes[-1].tick_params(axis="x", rotation=30)
        
        fig.tight_layout(h_pad=0.5)
        save_fig(fig, "fig_3_2_representative_week")
    
    return fig


# =============================================================================
# FIG 3-3 + TABLE 3-3: OPTIMAL HOUR BY REGION × SEASON
# =============================================================================

def compute_optimal_hours(df_5min: pd.DataFrame) -> pd.DataFrame:
    """
    For each region × season, find the hour with the lowest mean MOER
    within the operating window. Also computes annual best range.
    """
    print("\n── Computing optimal scheduling hours ──")
    
    # Filter to operating window
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]
    
    rows = []
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                continue
            hourly_mean = sd.groupby("hour")["value"].mean()
            best_hour = int(hourly_mean.idxmin())
            best_moer = hourly_mean.min()
            
            rows.append({
                "region":    region,
                "archetype": CH3_REGIONS[region]["archetype"],
                "season":    season,
                "best_hour": best_hour,
                "best_moer": best_moer,
            })
            record_number("Table 3-3",
                          f"{rshort(region)} {season} optimal hour",
                          f"{best_hour:02d}:00")
        
        # Annual best range
        annual_hourly = rd.groupby("hour")["value"].mean()
        annual_best = int(annual_hourly.idxmin())
        # Get range of best hours across seasons
        season_bests = [r["best_hour"] for r in rows if r["region"] == region]
        record_number("Table 3-3",
                      f"{rshort(region)} annual best hour", f"{annual_best:02d}:00")
    
    return pd.DataFrame(rows)


def plot_fig_3_3(optimal_hours: pd.DataFrame):
    """Heatmap: optimal scheduling hour by region × season."""
    print("\n── Fig 3-3: Optimal hour heatmap ──")
    cfg = FIG_3_3
    
    # Pivot to matrix
    pivot = optimal_hours.pivot(index="region", columns="season", values="best_hour")
    pivot = pivot.reindex(index=CH3_REGIONS.keys(), columns=SEASON_ORDER)
    
    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        
        im = ax.imshow(pivot.values, cmap=cfg["cmap"], aspect="auto",
                        vmin=0, vmax=23)
        
        # Labels
        ax.set_xticks(range(len(SEASON_ORDER)))
        ax.set_xticklabels([s.capitalize() for s in SEASON_ORDER])
        ax.set_yticks(range(len(CH3_REGIONS)))
        ax.set_yticklabels([CH3_REGIONS[r]["archetype"] for r in CH3_REGIONS])
        
        # Annotate cells with hour
        if cfg["annotate"]:
            for i in range(pivot.shape[0]):
                for j in range(pivot.shape[1]):
                    val = pivot.iloc[i, j]
                    if pd.notna(val):
                        # Choose text color based on background
                        text_color = "white" if val < 6 or val > 18 else "black"
                        ax.text(j, i, f"{int(val):02d}:00",
                                ha="center", va="center", fontsize=cfg["annot_size"],
                                color=text_color, fontweight="bold")
        
        cbar = fig.colorbar(im, ax=ax, label="Hour of Day", shrink=0.8)
        cbar.set_ticks([0, 6, 12, 18, 23])
        cbar.set_ticklabels(["00:00", "06:00", "12:00", "18:00", "23:00"])
        
        if cfg["title"]:
            ax.set_title(cfg["title"])
        
        save_fig(fig, "fig_3_3_optimal_hour_heatmap")
    
    return fig


# =============================================================================
# TABLE 3-2: ARCHETYPE SCHEDULING METRICS
# =============================================================================

def build_table_3_2(sim_df: pd.DataFrame) -> pd.DataFrame:
    """
    Archetype scheduling metrics for the 2-hour day-shift reference job.
    Baseline MOER, Optimal MOER, Savings %, CO₂ saved per 2kWh, diurnal range.
    """
    print("\n── Table 3-2: Archetype scheduling metrics ──")
    
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        if len(rd) == 0:
            continue
        
        baseline_mean  = rd["baseline_moer"].mean()
        optimal_mean   = rd["optimal_moer"].mean()
        savings_pct    = rd["savings_optimal_pct"].mean()
        
        # CO₂ saved per 2 kWh reference job:
        # savings_moer in lbs CO₂/MWh * 2 kWh * (1 MWh / 1000 kWh) * (453.6 g / 1 lb)
        savings_moer = baseline_mean - optimal_mean
        co2_saved_g  = savings_moer * 2 / 1000 * 453.592
        
        rows.append({
            "Archetype":                CH3_REGIONS[region]["archetype"],
            "Region":                   rshort(region),
            "Baseline MOER (lbs/MWh)":  round(baseline_mean, 0),
            "Optimal MOER (lbs/MWh)":   round(optimal_mean, 0),
            "Savings (%)":              round(savings_pct, 1),
            "CO₂ Saved /2kWh (g)":      round(co2_saved_g, 0),
        })
        
        record_number("Table 3-2", f"{rshort(region)} baseline MOER",
                      baseline_mean, ".0f")
        record_number("Table 3-2", f"{rshort(region)} optimal MOER",
                      optimal_mean, ".0f")
        record_number("Table 3-2", f"{rshort(region)} baseline-to-optimal savings",
                      savings_pct, ".1f")
    
    table = pd.DataFrame(rows)
    save_table(table, "table_3_2_archetype_metrics",
               "Table 3-2. Archetype scheduling metrics for a 2-hour day-shift reference job.")
    return table


# =============================================================================
# TABLE 3-3: OPTIMAL HOUR BY ARCHETYPE × SEASON
# =============================================================================

def build_table_3_3(optimal_hours: pd.DataFrame) -> pd.DataFrame:
    """Format the optimal hours into the thesis table layout."""
    print("\n── Table 3-3: Optimal scheduling hour by archetype and season ──")
    
    pivot = optimal_hours.pivot(index="region", columns="season", values="best_hour")
    pivot = pivot.reindex(index=CH3_REGIONS.keys(), columns=SEASON_ORDER)
    
    # Format as HH:00 strings
    for col in pivot.columns:
        pivot[col] = pivot[col].apply(lambda x: f"{int(x):02d}:00" if pd.notna(x) else "—")
    
    # Add labels
    pivot.insert(0, "Archetype", [CH3_REGIONS[r]["archetype"] for r in pivot.index])
    pivot.insert(1, "Region", [rshort(r) for r in pivot.index])
    pivot.columns = [c.capitalize() if c in SEASON_ORDER else c for c in pivot.columns]
    pivot = pivot.reset_index(drop=True)
    
    save_table(pivot, "table_3_3_optimal_hours",
               "Table 3-3. Optimal scheduling hour by archetype and season.")
    return pivot


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    
    # Load data
    df_5min  = load_5min()
    df_hourly = load_hourly()
    
    # --- Figures ---
    plot_fig_3_1(df_hourly)
    plot_fig_3_2(df_5min)
    
    optimal_hours = compute_optimal_hours(df_5min)
    plot_fig_3_3(optimal_hours)
    
    # --- Simulation for Table 3-2 ---
    thresholds = compute_thresholds(df_5min)
    sim_df = run_scheduling_sim(
        df_5min, thresholds=thresholds,
        use_cache=not recompute, cache_tag="s1_baseline_optimal",
    )
    
    # --- Tables ---
    build_table_3_2(sim_df)
    build_table_3_3(optimal_hours)
    
    export_numbers()
    print("\n✅ Section 3.3 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true",
                        help="Ignore cached simulation results")
    args = parser.parse_args()
    main(recompute=args.recompute)
