"""
08_grid_stress.py - Grid Stress Event Analysis

Identifies and characterizes periods of extreme grid emissions (stress events).
Analyzes when they occur, how long they last, whether they're predictable,
and provides guidance on when NOT to run energy-intensive operations.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below
    3. Run: python 08_grid_stress.py

Analysis:
    1. Stress Event Identification
       - Top 5%/10% MOER periods
       - Consecutive hour grouping
       - Duration and intensity metrics
    2. Temporal Characterization
       - Monthly/hourly distribution
       - Weekday vs weekend
       - Year-over-year trends
    3. Regional Correlation
       - Do regions spike together?
       - Safe harbor identification
    4. Forecast Warning Analysis
       - Did forecasts predict stress events?
       - Lead time distribution

Output (in run folder):
    - figures/08_*.png
    - outputs/08_*.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import seaborn as sns
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS, SEASON_COLORS,
    get_signal_metadata, get_unit_label
)

warnings.filterwarnings('ignore', category=FutureWarning)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run folder to analyze (set to None for most recent)
RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"

# Stress event definitions
STRESS_PERCENTILE_HIGH = 95  # Top 5% = severe stress
STRESS_PERCENTILE_MODERATE = 90  # Top 10% = moderate stress
MIN_CONSECUTIVE_HOURS = 2  # Minimum hours to count as an "event" (vs spike)
GAP_HOURS_TO_MERGE = 1  # Merge events separated by this many hours or less

# Analysis toggles
RUN_EVENT_IDENTIFICATION = True
RUN_TEMPORAL_ANALYSIS = True
RUN_REGIONAL_CORRELATION = True
RUN_FORECAST_WARNING = True  # Requires forecast data

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


def load_data(run_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load processed data files."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")
    df_hourly["point_time"] = pd.to_datetime(df_hourly[["year", "month", "day", "hour"]].assign(minute=0, second=0))
    df_5min = pd.read_parquet(processed_dir / "data_5min.parquet")
    
    print(f"  Hourly: {len(df_hourly):,} records")
    print(f"  5-min: {len(df_5min):,} records")
    
    return df_hourly, df_5min


def load_forecast_data(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load forecast data if available."""
    forecast_path = run_dir / "processed" / "data_forecast.parquet"
    if not forecast_path.exists():
        return None
    
    df = pd.read_parquet(forecast_path)
    print(f"  Forecast: {len(df):,} records")
    return df


# =============================================================================
# SECTION 1: STRESS EVENT IDENTIFICATION
# =============================================================================

def identify_stress_events(df_hourly: pd.DataFrame, signal: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Identify stress events as consecutive hours above threshold.
    
    Returns:
        events_df: One row per event with start, end, duration, peak
        hourly_flags: Original hourly data with stress flags added
    """
    print("\n  1A. Identifying stress events...")
    
    all_events = []
    hourly_with_flags = df_hourly.copy()
    hourly_with_flags["is_stress_severe"] = False
    hourly_with_flags["is_stress_moderate"] = False
    hourly_with_flags["event_id"] = None
    
    event_counter = 0
    
    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region].copy()
        region_data = region_data.sort_values("point_time")
        
        # Calculate thresholds
        threshold_severe = region_data["value_mean"].quantile(STRESS_PERCENTILE_HIGH / 100)
        threshold_moderate = region_data["value_mean"].quantile(STRESS_PERCENTILE_MODERATE / 100)
        
        print(f"    {REGIONS.get(region, {}).get('name', region)}: severe > {threshold_severe:.0f}, moderate > {threshold_moderate:.0f}")
        
        # Flag stress hours
        region_data["is_stress_severe"] = region_data["value_mean"] >= threshold_severe
        region_data["is_stress_moderate"] = region_data["value_mean"] >= threshold_moderate
        
        # Group consecutive severe hours into events
        region_data["stress_group"] = (
            (region_data["is_stress_severe"] != region_data["is_stress_severe"].shift())
        ).cumsum()
        
        # Find event groups
        for stress_flag in [True]:  # Only process stress periods
            stress_periods = region_data[region_data["is_stress_severe"] == stress_flag]
            
            for group_id in stress_periods["stress_group"].unique():
                group_data = stress_periods[stress_periods["stress_group"] == group_id]
                
                if len(group_data) < MIN_CONSECUTIVE_HOURS:
                    continue  # Skip isolated spikes
                
                event_counter += 1
                
                event = {
                    "event_id": event_counter,
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "start_time": group_data["point_time"].min(),
                    "end_time": group_data["point_time"].max(),
                    "duration_hours": len(group_data),
                    "peak_value": group_data["value_mean"].max(),
                    "mean_value": group_data["value_mean"].mean(),
                    "start_hour": group_data["hour"].iloc[0],
                    "peak_hour": group_data.loc[group_data["value_mean"].idxmax(), "hour"],
                    "month": group_data["month"].iloc[0],
                    "season": group_data["season"].iloc[0],
                    "year": group_data["year"].iloc[0],
                    "day_of_week": group_data["day_of_week"].iloc[0],
                    "is_weekend": group_data["is_weekend"].iloc[0],
                    "threshold_severe": threshold_severe,
                }
                all_events.append(event)
                
                # Update flags in hourly data
                idx = region_data[region_data["stress_group"] == group_id].index
                hourly_with_flags.loc[idx, "event_id"] = event_counter
        
        # Update stress flags
        idx = hourly_with_flags[hourly_with_flags["region"] == region].index
        hourly_with_flags.loc[idx, "is_stress_severe"] = region_data["is_stress_severe"].values
        hourly_with_flags.loc[idx, "is_stress_moderate"] = region_data["is_stress_moderate"].values
    
    events_df = pd.DataFrame(all_events)
    
    if len(events_df) > 0:
        print(f"\n    Total events identified: {len(events_df)}")
        print(f"    Mean duration: {events_df['duration_hours'].mean():.1f} hours")
        print(f"    Max duration: {events_df['duration_hours'].max()} hours")
    
    return events_df, hourly_with_flags


def calculate_event_statistics(events_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate summary statistics for stress events by region."""
    print("\n  1B. Calculating event statistics...")
    
    if len(events_df) == 0:
        return pd.DataFrame()
    
    stats = []
    
    for region in events_df["region"].unique():
        region_events = events_df[events_df["region"] == region]
        
        stats.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "total_events": len(region_events),
            "total_stress_hours": region_events["duration_hours"].sum(),
            "mean_duration_hours": region_events["duration_hours"].mean(),
            "median_duration_hours": region_events["duration_hours"].median(),
            "max_duration_hours": region_events["duration_hours"].max(),
            "mean_peak_value": region_events["peak_value"].mean(),
            "max_peak_value": region_events["peak_value"].max(),
            "events_per_year": len(region_events) / region_events["year"].nunique(),
            "stress_hours_per_year": region_events["duration_hours"].sum() / region_events["year"].nunique(),
            "pct_weekend": 100 * region_events["is_weekend"].mean(),
        })
    
    return pd.DataFrame(stats)


# =============================================================================
# SECTION 2: TEMPORAL CHARACTERIZATION
# =============================================================================

def analyze_stress_temporal_patterns(events_df: pd.DataFrame, hourly_flags: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Analyze when stress events occur (month, hour, weekday)."""
    print("\n  2A. Analyzing temporal patterns...")
    
    results = {}
    
    if len(events_df) == 0:
        return results
    
    # Monthly distribution
    monthly = events_df.groupby(["region", "month"]).agg({
        "event_id": "count",
        "duration_hours": "sum",
        "peak_value": "mean"
    }).reset_index()
    monthly.columns = ["region", "month", "n_events", "total_hours", "mean_peak"]
    results["monthly"] = monthly
    
    # Hour of day (when events START)
    hourly_start = events_df.groupby(["region", "start_hour"]).agg({
        "event_id": "count"
    }).reset_index()
    hourly_start.columns = ["region", "hour", "n_events_starting"]
    results["hourly_start"] = hourly_start
    
    # Hour of day (when peaks occur)
    hourly_peak = events_df.groupby(["region", "peak_hour"]).agg({
        "event_id": "count"
    }).reset_index()
    hourly_peak.columns = ["region", "hour", "n_events_peaking"]
    results["hourly_peak"] = hourly_peak
    
    # Day of week
    dow = events_df.groupby(["region", "day_of_week"]).agg({
        "event_id": "count",
        "duration_hours": "mean"
    }).reset_index()
    dow.columns = ["region", "day_of_week", "n_events", "mean_duration"]
    results["day_of_week"] = dow
    
    # Season
    seasonal = events_df.groupby(["region", "season"]).agg({
        "event_id": "count",
        "duration_hours": ["sum", "mean"],
        "peak_value": "mean"
    }).reset_index()
    seasonal.columns = ["region", "season", "n_events", "total_hours", "mean_duration", "mean_peak"]
    results["seasonal"] = seasonal
    
    # Year over year trends
    yearly = events_df.groupby(["region", "year"]).agg({
        "event_id": "count",
        "duration_hours": ["sum", "mean"],
        "peak_value": "mean"
    }).reset_index()
    yearly.columns = ["region", "year", "n_events", "total_hours", "mean_duration", "mean_peak"]
    results["yearly"] = yearly
    
    return results


def create_stress_calendar(events_df: pd.DataFrame) -> pd.DataFrame:
    """Create calendar view of stress events (month × hour heatmap data)."""
    print("\n  2B. Creating stress calendar...")
    
    if len(events_df) == 0:
        return pd.DataFrame()
    
    calendar_data = []
    
    for region in events_df["region"].unique():
        region_events = events_df[events_df["region"] == region]
        
        # Count events by month and start hour
        for month in range(1, 13):
            for hour in range(24):
                count = len(region_events[
                    (region_events["month"] == month) & 
                    (region_events["start_hour"] == hour)
                ])
                
                calendar_data.append({
                    "region": region,
                    "month": month,
                    "hour": hour,
                    "n_events": count
                })
    
    return pd.DataFrame(calendar_data)


# =============================================================================
# SECTION 3: REGIONAL CORRELATION
# =============================================================================

def analyze_regional_correlation(hourly_flags: pd.DataFrame) -> pd.DataFrame:
    """Analyze if stress events correlate across regions."""
    print("\n  3A. Analyzing regional correlation...")
    
    regions = hourly_flags["region"].unique()
    
    if len(regions) < 2:
        print("    Need at least 2 regions for correlation analysis")
        return pd.DataFrame()
    
    # Pivot to get regions as columns
    stress_pivot = hourly_flags.pivot_table(
        index="point_time",
        columns="region",
        values="is_stress_severe",
        aggfunc="first"
    ).fillna(False)
    
    # Calculate correlation matrix
    corr_matrix = stress_pivot.astype(int).corr()
    
    # Convert to long format
    corr_data = []
    for r1 in regions:
        for r2 in regions:
            if r1 in corr_matrix.index and r2 in corr_matrix.columns:
                corr_data.append({
                    "region_1": r1,
                    "region_2": r2,
                    "correlation": corr_matrix.loc[r1, r2]
                })
    
    return pd.DataFrame(corr_data)


def find_concurrent_stress(hourly_flags: pd.DataFrame) -> pd.DataFrame:
    """Find hours where multiple regions are stressed simultaneously."""
    print("\n  3B. Finding concurrent stress periods...")
    
    # Count stressed regions per hour
    stress_counts = hourly_flags.groupby("point_time")["is_stress_severe"].sum().reset_index()
    stress_counts.columns = ["point_time", "n_regions_stressed"]
    
    # Summary statistics
    summary = []
    total_hours = len(stress_counts)
    
    for n in range(1, hourly_flags["region"].nunique() + 1):
        hours_with_n = len(stress_counts[stress_counts["n_regions_stressed"] >= n])
        summary.append({
            "n_regions_stressed": n,
            "hours": hours_with_n,
            "pct_of_time": 100 * hours_with_n / total_hours
        })
    
    return pd.DataFrame(summary)


# =============================================================================
# SECTION 4: FORECAST WARNING ANALYSIS
# =============================================================================

def analyze_forecast_warning(events_df: pd.DataFrame, df_forecast: pd.DataFrame, 
                             hourly_flags: pd.DataFrame) -> pd.DataFrame:
    """Analyze how much warning forecasts gave for stress events."""
    print("\n  4A. Analyzing forecast warning capability...")
    
    if len(events_df) == 0 or df_forecast is None or len(df_forecast) == 0:
        print("    Insufficient data for forecast warning analysis")
        return pd.DataFrame()
    
    warning_results = []
    
    for _, event in events_df.iterrows():
        region = event["region"]
        event_start = event["start_time"]
        threshold = event["threshold_severe"]
        
        # Look for forecasts made before the event
        # that predicted high values during the event
        region_forecasts = df_forecast[df_forecast["region"] == region]
        
        if len(region_forecasts) == 0:
            continue
        
        # Find forecasts that cover this event's time period
        # (generated_at < event_start, point_time >= event_start)
        relevant_forecasts = region_forecasts[
            (region_forecasts["generated_at"] < event_start) &
            (region_forecasts["point_time"] >= event_start) &
            (region_forecasts["point_time"] <= event["end_time"])
        ]
        
        if len(relevant_forecasts) == 0:
            warning_results.append({
                "event_id": event["event_id"],
                "region": region,
                "event_start": event_start,
                "event_duration": event["duration_hours"],
                "event_peak": event["peak_value"],
                "forecast_available": False,
                "predicted_stress": False,
                "lead_time_hours": None,
                "forecast_peak": None,
            })
            continue
        
        # Check if any forecast predicted stress (value > threshold)
        forecasts_predicting_stress = relevant_forecasts[
            relevant_forecasts["value"] >= threshold
        ]
        
        if len(forecasts_predicting_stress) > 0:
            # Find earliest warning
            earliest_forecast = forecasts_predicting_stress.sort_values("generated_at").iloc[0]
            lead_time = (event_start - earliest_forecast["generated_at"]).total_seconds() / 3600
            forecast_peak = forecasts_predicting_stress["value"].max()
            predicted_stress = True
        else:
            lead_time = None
            forecast_peak = relevant_forecasts["value"].max()
            predicted_stress = False
        
        warning_results.append({
            "event_id": event["event_id"],
            "region": region,
            "event_start": event_start,
            "event_duration": event["duration_hours"],
            "event_peak": event["peak_value"],
            "forecast_available": True,
            "predicted_stress": predicted_stress,
            "lead_time_hours": lead_time,
            "forecast_peak": forecast_peak,
        })
    
    return pd.DataFrame(warning_results)


# =============================================================================
# PLOTTING FUNCTIONS
# =============================================================================

def plot_stress_monthly_heatmap(calendar_df: pd.DataFrame, figures_dir: Path):
    """Plot monthly × hourly heatmap of stress events."""
    
    if len(calendar_df) == 0:
        print("    No calendar data to plot")
        return
    
    regions = calendar_df["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(1, n_regions, figsize=(5 * n_regions, 6), squeeze=False)
    
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for i, region in enumerate(regions):
        ax = axes[0, i]
        region_data = calendar_df[calendar_df["region"] == region]
        
        pivot = region_data.pivot(index="month", columns="hour", values="n_events")
        pivot = pivot.reindex(range(1, 13)).fillna(0)
        
        sns.heatmap(pivot, ax=ax, cmap="YlOrRd", cbar_kws={"label": "# Events"})
        
        ax.set_title(REGIONS.get(region, {}).get("name", region), fontsize=11)
        ax.set_xlabel("Hour of Day")
        ax.set_ylabel("Month")
        ax.set_yticklabels(month_names, rotation=0)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xticklabels(range(0, 24, 3))
    
    plt.suptitle("Grid Stress Events: When Do They Start?", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_monthly_heatmap.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 08_stress_monthly_heatmap.png")


def plot_duration_distribution(events_df: pd.DataFrame, figures_dir: Path):
    """Plot distribution of stress event durations."""
    
    if len(events_df) == 0:
        print("    No events to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histogram
    ax = axes[0]
    for region in events_df["region"].unique():
        region_events = events_df[events_df["region"] == region]
        color = REGION_COLORS.get(region, "#333333")
        ax.hist(region_events["duration_hours"], bins=range(1, 25), alpha=0.5, 
                label=REGIONS.get(region, {}).get("name", region), color=color, edgecolor='black')
    
    ax.set_xlabel("Duration (hours)")
    ax.set_ylabel("Number of Events")
    ax.set_title("Distribution of Stress Event Durations")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Box plot by region
    ax = axes[1]
    regions = events_df["region"].unique()
    data_to_plot = [events_df[events_df["region"] == r]["duration_hours"] for r in regions]
    bp = ax.boxplot(data_to_plot, labels=[REGIONS.get(r, {}).get("name", r) for r in regions])
    ax.set_ylabel("Duration (hours)")
    ax.set_title("Event Duration by Region")
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_duration_dist.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 08_stress_duration_dist.png")


def plot_seasonal_stress(temporal_results: Dict, figures_dir: Path):
    """Plot stress events by season."""
    
    if "seasonal" not in temporal_results or len(temporal_results["seasonal"]) == 0:
        print("    No seasonal data to plot")
        return
    
    seasonal = temporal_results["seasonal"]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Events by season
    ax = axes[0]
    season_order = ["winter", "spring", "summer", "fall"]
    
    for region in seasonal["region"].unique():
        region_data = seasonal[seasonal["region"] == region]
        region_data = region_data.set_index("season").reindex(season_order)
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(season_order, region_data["n_events"], marker='o', 
                label=REGIONS.get(region, {}).get("name", region), color=color, linewidth=2)
    
    ax.set_xlabel("Season")
    ax.set_ylabel("Number of Events")
    ax.set_title("Stress Events by Season")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Total stress hours by season
    ax = axes[1]
    for region in seasonal["region"].unique():
        region_data = seasonal[seasonal["region"] == region]
        region_data = region_data.set_index("season").reindex(season_order)
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(season_order, region_data["total_hours"], marker='s',
                label=REGIONS.get(region, {}).get("name", region), color=color, linewidth=2)
    
    ax.set_xlabel("Season")
    ax.set_ylabel("Total Stress Hours")
    ax.set_title("Total Stress Hours by Season")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_seasonal.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 08_stress_seasonal.png")


def plot_regional_correlation(corr_df: pd.DataFrame, figures_dir: Path):
    """Plot regional correlation heatmap."""
    
    if len(corr_df) == 0:
        print("    No correlation data to plot")
        return
    
    # Pivot to matrix
    pivot = corr_df.pivot(index="region_1", columns="region_2", values="correlation")
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlBu_r", center=0,
                vmin=-0.5, vmax=1, ax=ax, cbar_kws={"label": "Correlation"})
    
    # Update labels
    labels = [REGIONS.get(r, {}).get("name", r) for r in pivot.index]
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=9)
    ax.set_yticklabels(labels, rotation=0, fontsize=9)
    
    ax.set_title("Regional Stress Event Correlation\n(Do regions spike together?)", fontsize=12)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_regional_corr.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 08_stress_regional_corr.png")


def plot_forecast_warning(warning_df: pd.DataFrame, figures_dir: Path):
    """Plot forecast warning analysis."""
    
    if len(warning_df) == 0:
        print("    No forecast warning data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Prediction success rate
    ax = axes[0]
    with_forecast = warning_df[warning_df["forecast_available"]]
    
    if len(with_forecast) > 0:
        success_rate = with_forecast.groupby("region")["predicted_stress"].mean() * 100
        
        bars = ax.bar(range(len(success_rate)), success_rate.values, 
                      color=[REGION_COLORS.get(r, "#333333") for r in success_rate.index],
                      edgecolor='black')
        ax.set_xticks(range(len(success_rate)))
        ax.set_xticklabels([REGIONS.get(r, {}).get("name", r) for r in success_rate.index],
                          rotation=45, ha='right', fontsize=9)
        ax.set_ylabel("% of Events Predicted")
        ax.set_title("Forecast Success Rate\n(Did forecast predict stress?)")
        ax.axhline(y=50, color='red', linestyle='--', alpha=0.5, label='50% baseline')
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, axis='y')
    
    # Lead time distribution
    ax = axes[1]
    predicted = warning_df[warning_df["predicted_stress"] == True]
    
    if len(predicted) > 0 and predicted["lead_time_hours"].notna().any():
        lead_times = predicted["lead_time_hours"].dropna()
        ax.hist(lead_times, bins=20, color='steelblue', edgecolor='black', alpha=0.7)
        ax.axvline(lead_times.median(), color='red', linestyle='--', 
                   label=f'Median: {lead_times.median():.1f}h')
        ax.set_xlabel("Lead Time (hours)")
        ax.set_ylabel("Number of Events")
        ax.set_title("Forecast Lead Time Distribution\n(How much warning did we get?)")
        ax.legend()
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "No predicted events\nwith lead time data", 
                ha='center', va='center', transform=ax.transAxes, fontsize=12)
        ax.set_title("Forecast Lead Time Distribution")
    
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_forecast_warning.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 08_stress_forecast_warning.png")


def plot_yearly_trends(temporal_results: Dict, figures_dir: Path):
    """Plot year-over-year trends in stress events."""
    
    if "yearly" not in temporal_results or len(temporal_results["yearly"]) == 0:
        print("    No yearly data to plot")
        return
    
    yearly = temporal_results["yearly"]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Number of events per year
    ax = axes[0]
    for region in yearly["region"].unique():
        region_data = yearly[yearly["region"] == region]
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["year"], region_data["n_events"], marker='o',
                label=REGIONS.get(region, {}).get("name", region), color=color, linewidth=2)
    
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of Stress Events")
    ax.set_title("Stress Events by Year")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Total stress hours per year
    ax = axes[1]
    for region in yearly["region"].unique():
        region_data = yearly[yearly["region"] == region]
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["year"], region_data["total_hours"], marker='s',
                label=REGIONS.get(region, {}).get("name", region), color=color, linewidth=2)
    
    ax.set_xlabel("Year")
    ax.set_ylabel("Total Stress Hours")
    ax.set_title("Total Stress Hours by Year")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "08_stress_yearly_trends.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 08_stress_yearly_trends.png")


# =============================================================================
# SUMMARY
# =============================================================================

def generate_summary_report(events_df: pd.DataFrame, event_stats: pd.DataFrame,
                           temporal_results: Dict, warning_df: pd.DataFrame,
                           signal: str, outputs_dir: Path):
    """Generate text summary of stress event analysis."""
    
    lines = [
        "=" * 70,
        "GRID STRESS EVENT ANALYSIS SUMMARY",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        f"Stress threshold: top {100 - STRESS_PERCENTILE_HIGH}% of MOER values",
        f"Minimum event duration: {MIN_CONSECUTIVE_HOURS} consecutive hours",
        "",
    ]
    
    if len(events_df) > 0:
        lines.extend([
            "-" * 70,
            "OVERALL STATISTICS",
            "-" * 70,
            f"Total stress events identified: {len(events_df)}",
            f"Total stress hours: {events_df['duration_hours'].sum():,}",
            f"Mean event duration: {events_df['duration_hours'].mean():.1f} hours",
            f"Max event duration: {events_df['duration_hours'].max()} hours",
            "",
        ])
        
        lines.extend([
            "-" * 70,
            "BY REGION",
            "-" * 70,
        ])
        
        for _, row in event_stats.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Events: {row['total_events']} ({row['events_per_year']:.1f}/year)")
            lines.append(f"  Total stress hours: {row['total_stress_hours']:.0f} ({row['stress_hours_per_year']:.1f}/year)")
            lines.append(f"  Mean duration: {row['mean_duration_hours']:.1f} hours")
            lines.append(f"  Weekend events: {row['pct_weekend']:.0f}%")
        
        if "seasonal" in temporal_results:
            lines.extend([
                "",
                "-" * 70,
                "SEASONAL PATTERNS",
                "-" * 70,
            ])
            seasonal = temporal_results["seasonal"]
            for region in seasonal["region"].unique():
                region_data = seasonal[seasonal["region"] == region]
                worst_season = region_data.loc[region_data["n_events"].idxmax(), "season"]
                lines.append(f"  {REGIONS.get(region, {}).get('name', region)}: Most events in {worst_season}")
    
    if len(warning_df) > 0:
        with_forecast = warning_df[warning_df["forecast_available"]]
        if len(with_forecast) > 0:
            pred_rate = 100 * with_forecast["predicted_stress"].mean()
            predicted = warning_df[warning_df["predicted_stress"]]
            
            lines.extend([
                "",
                "-" * 70,
                "FORECAST WARNING",
                "-" * 70,
                f"Events with forecast data: {len(with_forecast)}",
                f"Prediction success rate: {pred_rate:.0f}%",
            ])
            
            if len(predicted) > 0 and predicted["lead_time_hours"].notna().any():
                lead_times = predicted["lead_time_hours"].dropna()
                lines.append(f"Median lead time: {lead_times.median():.1f} hours")
                lines.append(f"Max lead time: {lead_times.max():.1f} hours")
    
    lines.extend([
        "",
        "-" * 70,
        "KEY TAKEAWAYS",
        "-" * 70,
    ])
    
    if len(events_df) > 0:
        # Calculate avoidance value
        total_hours = len(events_df["year"].unique()) * 8760  # Approximate
        stress_pct = 100 * events_df["duration_hours"].sum() / total_hours
        lines.append(f"  • Stress events represent ~{stress_pct:.1f}% of total hours")
        lines.append(f"  • Avoiding these hours provides disproportionate emissions reduction")
        
        # Worst times
        if "hourly_peak" in temporal_results:
            hourly = temporal_results["hourly_peak"]
            worst_hour = hourly.groupby("hour")["n_events_peaking"].sum().idxmax()
            lines.append(f"  • Peak stress most common at hour {worst_hour}:00")
    
    lines.extend([
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])
    
    report_text = "\n".join(lines)
    
    with open(outputs_dir / "08_summary_report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(report_text)


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
    
    print("=" * 70)
    print("GRID STRESS EVENT ANALYSIS")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Stress threshold: top {100 - STRESS_PERCENTILE_HIGH}%")
    print("=" * 70)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df_hourly, df_5min = load_data(run_dir)
    df_forecast = load_forecast_data(run_dir) if RUN_FORECAST_WARNING else None
    
    # Initialize results
    events_df = pd.DataFrame()
    hourly_flags = pd.DataFrame()
    event_stats = pd.DataFrame()
    temporal_results = {}
    calendar_df = pd.DataFrame()
    corr_df = pd.DataFrame()
    concurrent_df = pd.DataFrame()
    warning_df = pd.DataFrame()
    
    # ==========================================================================
    # SECTION 1: EVENT IDENTIFICATION
    # ==========================================================================
    if RUN_EVENT_IDENTIFICATION:
        print("\n" + "=" * 70)
        print("SECTION 1: STRESS EVENT IDENTIFICATION")
        print("=" * 70)
        
        events_df, hourly_flags = identify_stress_events(df_hourly, signal)
        
        if len(events_df) > 0:
            events_df.to_csv(outputs_dir / "08_stress_events.csv", index=False)
            
            event_stats = calculate_event_statistics(events_df)
            event_stats.to_csv(outputs_dir / "08_stress_statistics.csv", index=False)
            
            plot_duration_distribution(events_df, figures_dir)
    
    # ==========================================================================
    # SECTION 2: TEMPORAL ANALYSIS
    # ==========================================================================
    if RUN_TEMPORAL_ANALYSIS and len(events_df) > 0:
        print("\n" + "=" * 70)
        print("SECTION 2: TEMPORAL CHARACTERIZATION")
        print("=" * 70)
        
        temporal_results = analyze_stress_temporal_patterns(events_df, hourly_flags)
        
        for name, df in temporal_results.items():
            df.to_csv(outputs_dir / f"08_stress_{name}.csv", index=False)
        
        calendar_df = create_stress_calendar(events_df)
        calendar_df.to_csv(outputs_dir / "08_stress_calendar.csv", index=False)
        
        plot_stress_monthly_heatmap(calendar_df, figures_dir)
        plot_seasonal_stress(temporal_results, figures_dir)
        plot_yearly_trends(temporal_results, figures_dir)
    
    # ==========================================================================
    # SECTION 3: REGIONAL CORRELATION
    # ==========================================================================
    if RUN_REGIONAL_CORRELATION and len(hourly_flags) > 0:
        print("\n" + "=" * 70)
        print("SECTION 3: REGIONAL CORRELATION")
        print("=" * 70)
        
        corr_df = analyze_regional_correlation(hourly_flags)
        if len(corr_df) > 0:
            corr_df.to_csv(outputs_dir / "08_stress_correlation.csv", index=False)
            plot_regional_correlation(corr_df, figures_dir)
        
        concurrent_df = find_concurrent_stress(hourly_flags)
        concurrent_df.to_csv(outputs_dir / "08_stress_concurrent.csv", index=False)
    
    # ==========================================================================
    # SECTION 4: FORECAST WARNING
    # ==========================================================================
    if RUN_FORECAST_WARNING and df_forecast is not None and len(events_df) > 0:
        print("\n" + "=" * 70)
        print("SECTION 4: FORECAST WARNING ANALYSIS")
        print("=" * 70)
        
        warning_df = analyze_forecast_warning(events_df, df_forecast, hourly_flags)
        if len(warning_df) > 0:
            warning_df.to_csv(outputs_dir / "08_stress_forecast_warning.csv", index=False)
            plot_forecast_warning(warning_df, figures_dir)
    elif RUN_FORECAST_WARNING:
        print("\n  Skipping forecast warning (no forecast data)")
    
    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)
    
    generate_summary_report(events_df, event_stats, temporal_results, warning_df,
                           signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "08_grid_stress")
    
    print("\n" + "=" * 70)
    print("GRID STRESS ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/08_*.png")
    print(f"Data: {outputs_dir}/08_*.csv")
    print(f"Report: {outputs_dir}/08_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()
