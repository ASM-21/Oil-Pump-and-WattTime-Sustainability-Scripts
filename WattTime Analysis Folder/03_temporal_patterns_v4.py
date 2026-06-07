"""
03_temporal_patterns.py - Temporal Pattern Analysis (Percentile-Based, Mean & Median Heatmaps)

Characterizes value patterns by hour, season, weekday/weekend, and year.
Uses percentiles and median for skewed data distributions.
Generates both mean and median heatmaps for comparison.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below to point to your run folder
    3. Run: python 03_temporal_patterns.py

Output (in run folder):
    - figures/03_hourly_profile_{region}.png
    - figures/03_hourly_density_{region}.png
    - figures/03_hourly_by_season_{region}.png
    - figures/03_heatmap_median_{region}.png
    - figures/03_heatmap_mean_{region}.png
    - figures/03_weekday_weekend_{region}.png
    - figures/03_hourly_all_regions.png
    - figures/03_seasonal_all_regions.png
    - figures/03_weekday_weekend_all_regions.png
    - figures/03_yoy_trend_{region}.png
    - figures/03_annual_median_comparison.png
    - figures/03_daily_variability.png
    - figures/03_daily_range_by_season.png
    - outputs/temporal_pattern_summary.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
from datetime import datetime
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS, SEASON_COLORS,
    get_signal_metadata, get_unit_label
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run folder to analyze (created by 02_data_processing.py)
RUN_FOLDER = "2026-03-04_AOER_6RegionSummary_V1"

# Fixed plot limits
FIXED_YLIM = (0, 1600)
FIXED_HEATMAP_RANGE = (0, 1600)

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================


def get_run_dir() -> Path:
    """Get the run directory, auto-detecting if not specified."""
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
            print(f"\nAvailable runs in {RUNS_DIR}:")
            for d in sorted(RUNS_DIR.iterdir()):
                if d.is_dir():
                    print(f"  {d.name}")
            sys.exit(1)
        return run_dir
    
    # Auto-detect most recent run
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    if not runs:
        print("ERROR: No runs found. Run 02_data_processing.py first.")
        sys.exit(1)
    
    return runs[0]


def load_run_config(run_dir: Path) -> dict:
    """Load run configuration."""
    config_path = run_dir / "run_config.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def load_data(run_dir: Path):
    """Load processed data files from run folder."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    
    df_5min = pd.read_parquet(processed_dir / "data_5min.parquet")
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")
    df_daily = pd.read_parquet(processed_dir / "daily_statistics.parquet")
    
    print(f"  5-min: {len(df_5min):,} records")
    print(f"  Hourly: {len(df_hourly):,} records")
    print(f"  Daily: {len(df_daily):,} records")
    
    return df_5min, df_hourly, df_daily


def plot_hourly_profile(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, ylim=None):
    """Plot 24-hour profile with percentile shading for a single region."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    # Aggregate by hour using percentiles and median
    hourly_stats = data.groupby("hour").agg(
        mean=("value_mean", "mean"),
        median=("value_mean", "median"),
        p10=("value_mean", lambda x: x.quantile(0.10)),
        p90=("value_mean", lambda x: x.quantile(0.90)),
        p25=("value_mean", lambda x: x.quantile(0.25)),
        p75=("value_mean", lambda x: x.quantile(0.75)),
        count=("value_mean", "count"),
    ).reset_index()
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    hours = hourly_stats["hour"]
    median = hourly_stats["median"]
    mean = hourly_stats["mean"]
    
    # Plot median line (primary)
    ax.plot(hours, median, color=REGION_COLORS.get(region, "#1f77b4"), 
            linewidth=2.5, label="Median", zorder=3)
    
    # Plot mean line (secondary, lighter)
    ax.plot(hours, mean, color=REGION_COLORS.get(region, "#1f77b4"), 
            linewidth=1.5, linestyle='--', alpha=0.6, label="Mean", zorder=2)
    
    # Plot p25-p75 (IQR) shading - tighter band
    ax.fill_between(hours, hourly_stats["p25"], hourly_stats["p75"], alpha=0.4, 
                    color=REGION_COLORS.get(region, "#1f77b4"), label="25th-75th Percentile", zorder=1)
    
    # Plot p10-p90 range - wider band
    ax.fill_between(hours, hourly_stats["p10"], hourly_stats["p90"], alpha=0.15,
                    color=REGION_COLORS.get(region, "#1f77b4"), label="10th-90th Percentile", zorder=0)
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"24-Hour Profile: {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Mark typical shift boundaries
    for hour in [6, 14, 22]:
        ax.axvline(x=hour, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_hourly_profile_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_hourly_density(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, ylim=None):
    """Plot hourly profiles as violin/density plots to show distribution shape."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Prepare data for violin plot
    hours = sorted(data["hour"].unique())
    violin_data = [data[data["hour"] == h]["value_mean"].values for h in hours]
    
    # Create violin plot
    parts = ax.violinplot(violin_data, positions=hours, widths=0.7, 
                          showmeans=True, showmedians=True)
    
    # Customize colors
    for pc in parts['bodies']:
        pc.set_facecolor(REGION_COLORS.get(region, "#1f77b4"))
        pc.set_alpha(0.6)
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Hourly Distribution (Density): {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(range(0, 24, 3))
    ax.grid(True, alpha=0.3, axis='y')
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_hourly_density_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_hourly_by_season(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, ylim=None):
    """Plot hourly profiles by season for a single region using median."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    for season in ["winter", "spring", "summer", "fall"]:
        season_data = data[data["season"] == season]
        if len(season_data) == 0:
            continue
        hourly_median = season_data.groupby("hour")["value_mean"].median()
        
        ax.plot(hourly_median.index, hourly_median.values, 
                color=SEASON_COLORS[season], linewidth=2.5, label=season.capitalize())
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Hourly Profile by Season (Median): {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_hourly_by_season_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_heatmap_median(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, vmin=None, vmax=None):
    """Plot hour x month heatmap using median values for a single region."""
    
    unit_label = get_unit_label(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    # Create pivot table: rows=hour, columns=month (using median)
    pivot = data.groupby(["hour", "month"])["value_mean"].median().unstack()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn_r', origin='lower',
                   vmin=vmin, vmax=vmax)
    
    # Labels
    ax.set_xticks(range(12))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_yticks(range(0, 24, 3))
    ax.set_yticklabels(range(0, 24, 3))
    
    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_title(f"Heatmap (Median): {REGIONS[region]['name']}", fontsize=14)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(f"{unit_label}", fontsize=11)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_heatmap_median_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_heatmap_mean(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, vmin=None, vmax=None):
    """Plot hour x month heatmap using mean values for a single region."""
    
    unit_label = get_unit_label(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    # Create pivot table: rows=hour, columns=month (using mean)
    pivot = data.groupby(["hour", "month"])["value_mean"].mean().unstack()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn_r', origin='lower',
                   vmin=vmin, vmax=vmax)
    
    # Labels
    ax.set_xticks(range(12))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_yticks(range(0, 24, 3))
    ax.set_yticklabels(range(0, 24, 3))
    
    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_title(f"Heatmap (Mean): {REGIONS[region]['name']}", fontsize=14)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(f"{unit_label}", fontsize=11)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_heatmap_mean_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_weekday_weekend(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, ylim=None):
    """Plot weekday vs weekend hourly profiles using median."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Weekday
    weekday_data = data[~data["is_weekend"]]
    weekday_median = weekday_data.groupby("hour")["value_mean"].median()
    ax.plot(weekday_median.index, weekday_median.values, 
            color="#1f77b4", linewidth=2.5, label="Weekday")
    
    # Weekend
    weekend_data = data[data["is_weekend"]]
    weekend_median = weekend_data.groupby("hour")["value_mean"].median()
    ax.plot(weekend_median.index, weekend_median.values, 
            color="#ff7f0e", linewidth=2.5, label="Weekend")
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Weekday vs Weekend (Median): {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    # Calculate and annotate difference
    diff = (weekday_median - weekend_median).mean()
    ax.annotate(f"Avg Difference: {diff:.1f} {unit_label}", xy=(0.02, 0.98), 
                xycoords='axes fraction', va='top', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_weekday_weekend_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_all_regions_hourly(df_hourly: pd.DataFrame, signal: str, figures_dir: Path, ylim=None):
    """Plot hourly profiles (median) for all regions on one chart."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    for region in sorted(df_hourly["region"].unique()):
        data = df_hourly[df_hourly["region"] == region]
        hourly_median = data.groupby("hour")["value_mean"].median()
        
        ax.plot(hourly_median.index, hourly_median.values,
                color=REGION_COLORS.get(region, "#333333"), 
                linewidth=2.5, label=REGIONS.get(region, {}).get("name", region))
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title("24-Hour Profile Comparison Across Regions (Median)", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / "03_hourly_all_regions.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_all_regions_seasonal(df_hourly: pd.DataFrame, signal: str, figures_dir: Path, ylim=None):
    """Plot hourly profiles (median) for all regions overlaid, one subplot per season."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    
    # Use a distinct color palette
    regions_in_data = sorted(df_hourly["region"].unique())
    colors = plt.cm.tab10(np.linspace(0, 1, len(regions_in_data)))
    region_colors_distinct = {region: colors[i] for i, region in enumerate(regions_in_data)}
    
    for idx, season in enumerate(["winter", "spring", "summer", "fall"]):
        ax = axes[idx]
        season_data = df_hourly[df_hourly["season"] == season]
        
        for region in sorted(season_data["region"].unique()):
            rdata = season_data[season_data["region"] == region]
            hourly_median = rdata.groupby("hour")["value_mean"].median()
            ax.plot(hourly_median.index, hourly_median.values,
                    color=region_colors_distinct[region],
                    linewidth=2.5, label=REGIONS.get(region, {}).get("name", region))
        
        ax.set_title(season.capitalize(), fontsize=12)
        ax.set_xlim(0, 23)
        if ylim:
            ax.set_ylim(ylim)
        ax.set_xticks(range(0, 24, 6))
        ax.grid(True, alpha=0.3)
        if idx == 0:
            ax.legend(fontsize=9, loc='upper right')
    
    fig.supxlabel("Hour of Day (Local Time)", fontsize=12)
    fig.supylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    fig.suptitle("Seasonal Hourly Profiles: All Regions (Median)", fontsize=14)
    plt.tight_layout()
    
    outpath = figures_dir / "03_seasonal_all_regions.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_all_regions_weekday_weekend(df_hourly: pd.DataFrame, signal: str, figures_dir: Path, ylim=None):
    """Plot weekday vs weekend hourly profiles (median) for all regions, side by side."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    for ax_idx, (label, is_wknd) in enumerate([("Weekday", False), ("Weekend", True)]):
        ax = axes[ax_idx]
        subset = df_hourly[df_hourly["is_weekend"] == is_wknd]
        
        for region in sorted(subset["region"].unique()):
            rdata = subset[subset["region"] == region]
            hourly_median = rdata.groupby("hour")["value_mean"].median()
            ax.plot(hourly_median.index, hourly_median.values,
                    color=REGION_COLORS.get(region, "#333333"),
                    linewidth=2.5, label=REGIONS.get(region, {}).get("name", region))
        
        ax.set_title(label, fontsize=12)
        ax.set_xlabel("Hour of Day (Local Time)", fontsize=11)
        ax.set_xlim(0, 23)
        if ylim:
            ax.set_ylim(ylim)
        ax.set_xticks(range(0, 24, 6))
        ax.grid(True, alpha=0.3)
        if ax_idx == 0:
            ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=11)
            ax.legend(fontsize=8)
    
    fig.suptitle("Weekday vs Weekend Hourly Profiles: All Regions (Median)", fontsize=14)
    plt.tight_layout()
    
    outpath = figures_dir / "03_weekday_weekend_all_regions.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_yoy_trend(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path, ylim=None):
    """Plot year-over-year hourly profile comparison (median)."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    years = sorted(data["year"].unique())
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(years)))
    
    for year, color in zip(years, colors):
        year_data = data[data["year"] == year]
        hourly_median = year_data.groupby("hour")["value_mean"].median()
        ax.plot(hourly_median.index, hourly_median.values,
                color=color, linewidth=2.5, label=str(year))
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Year-over-Year Trend (Median): {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    if ylim:
        ax.set_ylim(ylim)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_yoy_trend_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_annual_median_comparison(df_daily: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot annual median by region over the years."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Calculate annual medians
    annual = df_daily.groupby(["region", "year"])["value_mean"].median().unstack()
    
    x = np.arange(len(annual.columns))
    width = 0.15
    
    regions_in_data = sorted(annual.index.tolist())
    
    for i, region in enumerate(regions_in_data):
        offset = (i - len(regions_in_data)/2 + 0.5) * width
        values = annual.loc[region].values
        ax.bar(x + offset, values, width, 
               label=REGIONS.get(region, {}).get("name", region), 
               color=REGION_COLORS.get(region, "#333333"))
    
    ax.set_xlabel("Year", fontsize=12)
    ax.set_ylabel(f"Median {signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title("Annual Median by Region", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(annual.columns.astype(int))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    outpath = figures_dir / "03_annual_median_comparison.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_daily_variability(df_daily: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot distribution of daily range (max-min) by region."""
    
    unit_label = get_unit_label(signal)
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    regions_in_data = sorted(df_daily["region"].unique())
    
    data_to_plot = [df_daily[df_daily["region"] == r]["value_range"].values 
                    for r in regions_in_data]
    
    bp = ax.boxplot(data_to_plot, 
                    tick_labels=[REGIONS.get(r, {}).get("name", r) for r in regions_in_data],
                    patch_artist=True)
    
    # Color the boxes
    for patch, region in zip(bp['boxes'], regions_in_data):
        patch.set_facecolor(REGION_COLORS.get(region, "#cccccc"))
        patch.set_alpha(0.7)
    
    ax.set_ylabel(f"Daily Range ({unit_label})", fontsize=12)
    ax.set_title("Distribution of Daily Variability by Region", fontsize=14)
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    outpath = figures_dir / "03_daily_variability.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_daily_range_by_season(df_daily: pd.DataFrame, signal: str, figures_dir: Path):
    """Box plot of daily value range (max-min) by region and season.
    Shows when the grid has enough intra-day variation for scheduling to matter."""
    
    unit_label = get_unit_label(signal)
    
    regions_in_data = sorted(df_daily["region"].unique())
    seasons = ["winter", "spring", "summer", "fall"]
    n_regions = len(regions_in_data)
    
    fig, axes = plt.subplots(1, n_regions, figsize=(4 * n_regions, 6), sharey=True)
    if n_regions == 1:
        axes = [axes]
    
    for ax, region in zip(axes, regions_in_data):
        region_data = df_daily[df_daily["region"] == region]
        
        data_by_season = [region_data[region_data["season"] == s]["value_range"].dropna().values
                          for s in seasons]
        
        bp = ax.boxplot(data_by_season,
                        tick_labels=[s.capitalize()[:3] for s in seasons],
                        patch_artist=True, widths=0.6)
        
        for patch, season in zip(bp['boxes'], seasons):
            patch.set_facecolor(SEASON_COLORS[season])
            patch.set_alpha(0.7)
        
        ax.set_title(REGIONS.get(region, {}).get("name", region), fontsize=11)
        ax.grid(True, alpha=0.3, axis='y')
        ax.tick_params(axis='x', rotation=45)
    
    axes[0].set_ylabel(f"Daily Range ({unit_label})", fontsize=12)
    fig.suptitle("Intra-Day Range by Season and Region\n(Higher = More Scheduling Opportunity)", fontsize=13)
    plt.tight_layout()
    
    outpath = figures_dir / "03_daily_range_by_season.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def generate_summary_stats(df_hourly: pd.DataFrame, df_daily: pd.DataFrame, 
                           signal: str, outputs_dir: Path):
    """Generate and save summary statistics table using percentiles and median."""
    
    unit_label = get_unit_label(signal)
    
    summary_rows = []
    
    for region in sorted(df_daily["region"].unique()):
        daily = df_daily[df_daily["region"] == region]
        hourly = df_hourly[df_hourly["region"] == region]
        
        # Find best/worst hours (by median)
        hourly_median = hourly.groupby("hour")["value_mean"].median()
        best_hour = hourly_median.idxmin()
        worst_hour = hourly_median.idxmax()
        
        summary_rows.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "signal": signal,
            "unit": unit_label,
            "median_value": daily["value_mean"].median(),
            "mean_value": daily["value_mean"].mean(),
            "p10_value": daily["value_mean"].quantile(0.10),
            "p90_value": daily["value_mean"].quantile(0.90),
            "min_value": daily["value_min"].min(),
            "max_value": daily["value_max"].max(),
            "avg_daily_range": daily["value_range"].mean(),
            "best_hour": best_hour,
            "best_hour_median": hourly_median[best_hour],
            "worst_hour": worst_hour,
            "worst_hour_median": hourly_median[worst_hour],
            "hour_spread": hourly_median[worst_hour] - hourly_median[best_hour],
            "n_days": len(daily),
        })
    
    summary_df = pd.DataFrame(summary_rows)
    
    outpath = outputs_dir / "temporal_pattern_summary.csv"
    summary_df.to_csv(outpath, index=False)
    print(f"\n  Saved summary: {outpath.name}")
    
    # Print to console
    print("\n" + "=" * 80)
    print("TEMPORAL PATTERN SUMMARY (Median-Based)")
    print("=" * 80)
    for _, row in summary_df.iterrows():
        print(f"\n{row['region_name']}:")
        print(f"  Median: {row['median_value']:.1f} {unit_label}")
        print(f"  Mean: {row['mean_value']:.1f} {unit_label}")
        print(f"  P10-P90: {row['p10_value']:.1f} - {row['p90_value']:.1f}")
        print(f"  Best hour: {int(row['best_hour'])}:00 (median: {row['best_hour_median']:.1f})")
        print(f"  Worst hour: {int(row['worst_hour'])}:00 (median: {row['worst_hour_median']:.1f})")
        print(f"  Hourly spread: {row['hour_spread']:.1f} {unit_label}")
        print(f"  Days in dataset: {int(row['n_days'])}")
    
    return summary_df


def mark_script_run(run_dir: Path, script_name: str):
    """Record that a script was run."""
    config_path = run_dir / "run_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    config["scripts_run"].append({
        "script": script_name,
        "timestamp": datetime.now().isoformat(),
    })
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)


def main():
    # Get run directory
    run_dir = get_run_dir()
    config = load_run_config(run_dir)
    signal = config["signal"]
    
    print("=" * 80)
    print("TEMPORAL PATTERN ANALYSIS (Percentile-Based, Mean & Median Heatmaps)")
    print("=" * 80)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Regions: {', '.join(config['regions'])}")
    print("=" * 80)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    figures_dir.mkdir(exist_ok=True)
    outputs_dir.mkdir(exist_ok=True)
    
    # Load data
    df_5min, df_hourly, df_daily = load_data(run_dir)
    
    # Get regions present in data
    regions_in_data = sorted(df_hourly["region"].unique())
    
    # Use fixed limits from config
    global_hourly_ylim = FIXED_YLIM
    global_heatmap_range = FIXED_HEATMAP_RANGE
    
    # Generate per-region plots
    print("\nGenerating per-region figures...")
    for region in regions_in_data:
        print(f"\n  {region}:")
        plot_hourly_profile(df_hourly, region, signal, figures_dir, ylim=global_hourly_ylim)
        plot_hourly_density(df_hourly, region, signal, figures_dir, ylim=global_hourly_ylim)
        plot_hourly_by_season(df_hourly, region, signal, figures_dir, ylim=global_hourly_ylim)
        plot_heatmap_median(df_hourly, region, signal, figures_dir, vmin=global_heatmap_range[0], vmax=global_heatmap_range[1])
        plot_heatmap_mean(df_hourly, region, signal, figures_dir, vmin=global_heatmap_range[0], vmax=global_heatmap_range[1])
        plot_weekday_weekend(df_hourly, region, signal, figures_dir, ylim=global_hourly_ylim)
        plot_yoy_trend(df_hourly, region, signal, figures_dir, ylim=global_hourly_ylim)
    
    # Generate comparison plots
    print("\nGenerating comparison figures...")
    plot_all_regions_hourly(df_hourly, signal, figures_dir, ylim=global_hourly_ylim)
    plot_all_regions_seasonal(df_hourly, signal, figures_dir, ylim=global_hourly_ylim)
    plot_all_regions_weekday_weekend(df_hourly, signal, figures_dir, ylim=global_hourly_ylim)
    plot_annual_median_comparison(df_daily, signal, figures_dir)
    plot_daily_variability(df_daily, signal, figures_dir)
    plot_daily_range_by_season(df_daily, signal, figures_dir)
    
    # Generate summary statistics
    summary = generate_summary_stats(df_hourly, df_daily, signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "03_temporal_patterns")
    
    print("\n" + "=" * 80)
    print("TEMPORAL PATTERN ANALYSIS COMPLETE")
    print(f"Figures saved to: {figures_dir}")
    print(f"Summary saved to: {outputs_dir}")
    print("=" * 80)


if __name__ == "__main__":
    main()