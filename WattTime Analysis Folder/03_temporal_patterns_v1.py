"""
03_temporal_patterns.py - Temporal Pattern Analysis

Characterizes value patterns by hour, season, weekday/weekend, and year.
Generates figures for understanding when grid is cleanest/dirtiest.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below to point to your run folder
    3. Run: python 03_temporal_patterns.py

Output (in run folder):
    - figures/03_hourly_profile_{region}.png
    - figures/03_hourly_by_season_{region}.png
    - figures/03_heatmap_{region}.png
    - figures/03_weekday_weekend_{region}.png
    - figures/03_hourly_all_regions.png
    - figures/03_yoy_trend_{region}.png
    - figures/03_annual_mean_comparison.png
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
# Use the folder name from runs/, e.g., "2025-01-28_moer_temporal"
# Or set to None to use the most recent run
RUN_FOLDER = "2026-02-16_GridMixStudy_Test2"  # Will auto-detect most recent run

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


def plot_hourly_profile(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot 24-hour profile with std shading for a single region."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    # Aggregate by hour
    hourly_stats = data.groupby("hour").agg(
        mean=("value_mean", "mean"),
        std=("value_mean", "std"),
        p10=("value_mean", lambda x: x.quantile(0.10)),
        p90=("value_mean", lambda x: x.quantile(0.90)),
    ).reset_index()
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    hours = hourly_stats["hour"]
    mean = hourly_stats["mean"]
    std = hourly_stats["std"]
    
    # Plot mean line
    ax.plot(hours, mean, color=REGION_COLORS.get(region, "#1f77b4"), linewidth=2, label="Mean")
    
    # Plot +/- 1 std shading
    ax.fill_between(hours, mean - std, mean + std, alpha=0.3, 
                    color=REGION_COLORS.get(region, "#1f77b4"), label="+/- 1 Std Dev")
    
    # Plot 10th-90th percentile range
    ax.fill_between(hours, hourly_stats["p10"], hourly_stats["p90"], alpha=0.1,
                    color=REGION_COLORS.get(region, "#1f77b4"), label="10th-90th Percentile")
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"24-Hour Profile: {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    # Mark typical shift boundaries
    for hour in [6, 14, 22]:
        ax.axvline(x=hour, color='gray', linestyle='--', alpha=0.5, linewidth=1)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_hourly_profile_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_hourly_by_season(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot hourly profiles by season for a single region."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    for season in ["winter", "spring", "summer", "fall"]:
        season_data = data[data["season"] == season]
        if len(season_data) == 0:
            continue
        hourly_mean = season_data.groupby("hour")["value_mean"].mean()
        
        ax.plot(hourly_mean.index, hourly_mean.values, 
                color=SEASON_COLORS[season], linewidth=2, label=season.capitalize())
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Hourly Profile by Season: {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_hourly_by_season_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_heatmap(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot hour x month heatmap for a single region."""
    
    unit_label = get_unit_label(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    # Create pivot table: rows=hour, columns=month
    pivot = data.groupby(["hour", "month"])["value_mean"].mean().unstack()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    im = ax.imshow(pivot.values, aspect='auto', cmap='RdYlGn_r', origin='lower')
    
    # Labels
    ax.set_xticks(range(12))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_yticks(range(0, 24, 3))
    ax.set_yticklabels(range(0, 24, 3))
    
    ax.set_xlabel("Month", fontsize=12)
    ax.set_ylabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_title(f"Heatmap: {REGIONS[region]['name']}", fontsize=14)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label(f"{unit_label}", fontsize=11)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_heatmap_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_weekday_weekend(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot weekday vs weekend hourly profiles."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Weekday
    weekday_data = data[~data["is_weekend"]]
    weekday_mean = weekday_data.groupby("hour")["value_mean"].mean()
    ax.plot(weekday_mean.index, weekday_mean.values, 
            color="#1f77b4", linewidth=2, label="Weekday")
    
    # Weekend
    weekend_data = data[data["is_weekend"]]
    weekend_mean = weekend_data.groupby("hour")["value_mean"].mean()
    ax.plot(weekend_mean.index, weekend_mean.values, 
            color="#ff7f0e", linewidth=2, label="Weekend")
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Weekday vs Weekend: {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    # Calculate and annotate difference
    diff = (weekday_mean - weekend_mean).mean()
    ax.annotate(f"Avg Difference: {diff:.1f} {unit_label}", xy=(0.02, 0.98), 
                xycoords='axes fraction', va='top', fontsize=10,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_weekday_weekend_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_all_regions_hourly(df_hourly: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot hourly profiles for all regions on one chart."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, ax = plt.subplots(figsize=(12, 7))
    
    for region in sorted(df_hourly["region"].unique()):
        data = df_hourly[df_hourly["region"] == region]
        hourly_mean = data.groupby("hour")["value_mean"].mean()
        
        ax.plot(hourly_mean.index, hourly_mean.values,
                color=REGION_COLORS.get(region, "#333333"), 
                linewidth=2, label=REGIONS.get(region, {}).get("name", region))
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title("24-Hour Profile Comparison Across Regions", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    outpath = figures_dir / "03_hourly_all_regions.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_yoy_trend(df_hourly: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot year-over-year hourly profile comparison."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    data = df_hourly[df_hourly["region"] == region]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    years = sorted(data["year"].unique())
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(years)))
    
    for year, color in zip(years, colors):
        year_data = data[data["year"] == year]
        hourly_mean = year_data.groupby("hour")["value_mean"].mean()
        ax.plot(hourly_mean.index, hourly_mean.values,
                color=color, linewidth=2, label=str(year))
    
    ax.set_xlabel("Hour of Day (Local Time)", fontsize=12)
    ax.set_ylabel(f"{signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title(f"Year-over-Year Trend: {REGIONS[region]['name']}", fontsize=14)
    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    outpath = figures_dir / f"03_yoy_trend_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_annual_mean_comparison(df_daily: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot annual mean by region over the years."""
    
    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    # Calculate annual means
    annual = df_daily.groupby(["region", "year"])["value_mean"].mean().unstack()
    
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
    ax.set_ylabel(f"Mean {signal_meta['name']} ({unit_label})", fontsize=12)
    ax.set_title("Annual Average by Region", fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(annual.columns.astype(int))
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    outpath = figures_dir / "03_annual_mean_comparison.png"
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


def generate_summary_stats(df_hourly: pd.DataFrame, df_daily: pd.DataFrame, 
                           signal: str, outputs_dir: Path):
    """Generate and save summary statistics table."""
    
    unit_label = get_unit_label(signal)
    
    summary_rows = []
    
    for region in sorted(df_daily["region"].unique()):
        daily = df_daily[df_daily["region"] == region]
        hourly = df_hourly[df_hourly["region"] == region]
        
        # Find best/worst hours
        hourly_avg = hourly.groupby("hour")["value_mean"].mean()
        best_hour = hourly_avg.idxmin()
        worst_hour = hourly_avg.idxmax()
        
        summary_rows.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "signal": signal,
            "unit": unit_label,
            "mean_value": daily["value_mean"].mean(),
            "std_value": daily["value_mean"].std(),
            "min_value": daily["value_min"].min(),
            "max_value": daily["value_max"].max(),
            "avg_daily_range": daily["value_range"].mean(),
            "best_hour": best_hour,
            "best_hour_value": hourly_avg[best_hour],
            "worst_hour": worst_hour,
            "worst_hour_value": hourly_avg[worst_hour],
            "hour_spread": hourly_avg[worst_hour] - hourly_avg[best_hour],
            "n_days": len(daily),
        })
    
    summary_df = pd.DataFrame(summary_rows)
    
    outpath = outputs_dir / "temporal_pattern_summary.csv"
    summary_df.to_csv(outpath, index=False)
    print(f"\n  Saved summary: {outpath.name}")
    
    # Print to console
    print("\n" + "=" * 60)
    print("TEMPORAL PATTERN SUMMARY")
    print("=" * 60)
    for _, row in summary_df.iterrows():
        print(f"\n{row['region_name']}:")
        print(f"  Mean: {row['mean_value']:.1f} {unit_label}")
        print(f"  Best hour: {int(row['best_hour'])}:00 ({row['best_hour_value']:.1f})")
        print(f"  Worst hour: {int(row['worst_hour'])}:00 ({row['worst_hour_value']:.1f})")
        print(f"  Hourly spread: {row['hour_spread']:.1f} {unit_label}")
    
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
    
    print("=" * 60)
    print("TEMPORAL PATTERN ANALYSIS")
    print("=" * 60)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Regions: {', '.join(config['regions'])}")
    print("=" * 60)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df_5min, df_hourly, df_daily = load_data(run_dir)
    
    # Get regions present in data
    regions_in_data = sorted(df_hourly["region"].unique())
    
    # Generate per-region plots
    print("\nGenerating per-region figures...")
    for region in regions_in_data:
        print(f"\n  {region}:")
        plot_hourly_profile(df_hourly, region, signal, figures_dir)
        plot_hourly_by_season(df_hourly, region, signal, figures_dir)
        plot_heatmap(df_hourly, region, signal, figures_dir)
        plot_weekday_weekend(df_hourly, region, signal, figures_dir)
        plot_yoy_trend(df_hourly, region, signal, figures_dir)
    
    # Generate comparison plots
    print("\nGenerating comparison figures...")
    plot_all_regions_hourly(df_hourly, signal, figures_dir)
    plot_annual_mean_comparison(df_daily, signal, figures_dir)
    plot_daily_variability(df_daily, signal, figures_dir)
    
    # Generate summary statistics
    summary = generate_summary_stats(df_hourly, df_daily, signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "03_temporal_patterns")
    
    print("\n" + "=" * 60)
    print("TEMPORAL PATTERN ANALYSIS COMPLETE")
    print(f"Figures saved to: {figures_dir}")
    print(f"Summary saved to: {outputs_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
