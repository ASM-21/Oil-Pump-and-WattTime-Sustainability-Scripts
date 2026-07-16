"""
diagnose_kansas.py - Debug unusual spikes in Kansas data

Usage:
    python diagnose_kansas.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RUNS_DIR, REGIONS, FIGURE_DPI

# =============================================================================
# CONFIG
# =============================================================================

RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"
REGION = "SPP_KANSAS"

# =============================================================================

def get_run_dir() -> Path:
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
            sys.exit(1)
        return run_dir
    
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    if not runs:
        print("ERROR: No runs found.")
        sys.exit(1)
    return runs[0]


def load_data(run_dir: Path):
    """Load data from run folder."""
    processed_dir = run_dir / "processed"
    df_5min = pd.read_parquet(processed_dir / "data_5min.parquet")
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")
    df_daily = pd.read_parquet(processed_dir / "daily_statistics.parquet")
    return df_5min, df_hourly, df_daily


def main():
    run_dir = get_run_dir()
    print(f"Run: {run_dir.name}\nRegion: {REGION}\n")
    
    df_5min, df_hourly, df_daily = load_data(run_dir)
    
    # Filter to Kansas
    h = df_hourly[df_hourly["region"] == REGION]
    d = df_daily[df_daily["region"] == REGION]
    
    # Basic stats
    print("="*60)
    print("HOURLY STATISTICS")
    print("="*60)
    print(f"Count: {len(h):,}")
    print(f"Mean: {h['value_mean'].mean():.1f}")
    print(f"Std:  {h['value_mean'].std():.1f}")
    print(f"Min:  {h['value_mean'].min():.1f}")
    print(f"Max:  {h['value_mean'].max():.1f}")
    print(f"p50:  {h['value_mean'].quantile(0.50):.1f}")
    print(f"p90:  {h['value_mean'].quantile(0.90):.1f}")
    print(f"p99:  {h['value_mean'].quantile(0.99):.1f}")
    
   # Find outliers
    q99 = h['value_mean'].quantile(0.99)
    outliers = h[h['value_mean'] > q99].sort_values('value_mean', ascending=False)
    
    print(f"\n{'='*60}")
    print(f"TOP 20 SPIKY HOURS (>p99={q99:.1f})")
    print(f"{'='*60}")
    for idx, row in outliers.head(20).iterrows():
        print(f"Index {idx}: {row['value_mean']:.1f} | Year: {row['year']}, Month: {row['month']}, Hour: {row['hour']}")
    
    # By year
    print(f"\n{'='*60}")
    print("BY YEAR")
    print(f"{'='*60}")
    for year in sorted(h['year'].unique()):
        year_data = h[h['year'] == year]
        print(f"{year}: mean={year_data['value_mean'].mean():.1f}, max={year_data['value_mean'].max():.1f}, count={len(year_data)}")
    
    # By month
    print(f"\n{'='*60}")
    print("BY MONTH (avg over all years)")
    print(f"{'='*60}")
    for month in range(1, 13):
        month_data = h[h['month'] == month]
        if len(month_data) == 0:
            continue
        print(f"Month {month:2d}: mean={month_data['value_mean'].mean():.1f}, max={month_data['value_mean'].max():.1f}")
    
    # By hour of day
    print(f"\n{'='*60}")
    print("BY HOUR OF DAY")
    print(f"{'='*60}")
    for hour in range(24):
        hour_data = h[h['hour'] == hour]
        if len(hour_data) == 0:
            continue
        print(f"Hour {hour:2d}: mean={hour_data['value_mean'].mean():.1f}, max={hour_data['value_mean'].max():.1f}")
    
    # Plot: time series of worst days
    print(f"\n{'='*60}")
    print("GENERATING DIAGNOSTIC PLOTS")
    print(f"{'='*60}")
    
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    
    # Plot 1: Time series of all hourly values
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.scatter(range(len(h)), h['value_mean'], alpha=0.5, s=10)
    ax.axhline(q99, color='red', linestyle='--', label=f'p99={q99:.1f}')
    ax.set_xlabel("Time (hourly records)")
    ax.set_ylabel("Value")
    ax.set_title(f"{REGION.capitalize()} - All Hourly Values")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures_dir / "diag_timeseries.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: diag_timeseries.png")
    
    # Plot 2: Distribution
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(h['value_mean'], bins=100, alpha=0.7, edgecolor='black')
    ax.axvline(q99, color='red', linestyle='--', linewidth=2, label=f'p99={q99:.1f}')
    ax.axvline(h['value_mean'].mean(), color='green', linestyle='--', linewidth=2, label=f'mean={h["value_mean"].mean():.1f}')
    ax.set_xlabel("Value")
    ax.set_ylabel("Frequency")
    ax.set_title(f"{REGION.capitalize()} - Distribution of Hourly Values")
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(figures_dir / "diag_distribution.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: diag_distribution.png")
    
    # Plot 3: Monthly boxplot
    fig, ax = plt.subplots(figsize=(12, 6))
    data_by_month = [h[h['month'] == m]['value_mean'].values for m in range(1, 13)]
    ax.boxplot(data_by_month, labels=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_ylabel("Value")
    ax.set_title(f"{REGION.capitalize()} - Monthly Variability")
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(figures_dir / "diag_by_month.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: diag_by_month.png")
    
    print("\nDone. Check figures/ for plots.")


if __name__ == "__main__":
    main()