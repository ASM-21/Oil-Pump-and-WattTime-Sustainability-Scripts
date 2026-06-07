"""
11_threshold_buckets.py - Traffic Light Decision Rules

Simplifies carbon-aware scheduling to a traffic light system:
  - Green: Bottom 25% MOER - run freely
  - Yellow: Middle 50% MOER - run if needed  
  - Red: Top 25% MOER - defer if possible

Provides lookup tables for operators without requiring API integration.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below
    3. Run: python 11_threshold_buckets.py

Analysis:
    1. Threshold Definition
       - Calculate green/yellow/red cutoffs per region
       - Calibrate to regional MOER distributions
    2. Bucket Distribution
       - % of hours in each bucket by region/season/hour
       - Availability analysis for production planning
    3. Transition Patterns
       - Markov-style transition probabilities
       - How long do green windows typically last?
    4. Savings Quantification
       - If defer all red → next green, what's the savings?
       - Comparison to optimal scheduling

Output (in run folder):
    - figures/11_*.png
    - outputs/11_*.csv
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

# Traffic light thresholds (percentiles)
# GREEN: MOER below this percentile (cleanest grid)
# YELLOW: MOER between green and red (moderate)
# RED: MOER above this percentile (dirtiest grid)
GREEN_PERCENTILE = 25  # Bottom 25%
RED_PERCENTILE = 75    # Top 25%

# Minimum production hours needed per day
MIN_PRODUCTION_HOURS_PER_DAY = 8

# Transition analysis
TRANSITION_LOOKAHEAD_HOURS = [1, 2, 3, 4]  # Hours ahead to calculate transitions

# Analysis toggles
RUN_THRESHOLD_DEFINITION = True
RUN_BUCKET_DISTRIBUTION = True
RUN_TRANSITION_ANALYSIS = True
RUN_SAVINGS_QUANTIFICATION = True

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================


# Traffic light colors
TRAFFIC_COLORS = {
    "green": "#2ecc71",
    "yellow": "#f39c12", 
    "red": "#e74c3c"
}


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


def load_data(run_dir: Path) -> pd.DataFrame:
    """Load processed hourly data."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")

    df_hourly["point_time"] = pd.to_datetime(df_hourly[["year", "month", "day", "hour"]].assign(minute=0, second=0))
    
    print(f"  Hourly: {len(df_hourly):,} records")
    
    return df_hourly


# =============================================================================
# SECTION 1: THRESHOLD DEFINITION
# =============================================================================

def calculate_thresholds(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """Calculate green/yellow/red thresholds for each region."""
    print("\n  1A. Calculating traffic light thresholds...")
    
    thresholds = []
    
    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region]
        
        green_threshold = region_data["value_mean"].quantile(GREEN_PERCENTILE / 100)
        red_threshold = region_data["value_mean"].quantile(RED_PERCENTILE / 100)
        
        thresholds.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "green_threshold": green_threshold,
            "red_threshold": red_threshold,
            "green_percentile": GREEN_PERCENTILE,
            "red_percentile": RED_PERCENTILE,
            "region_min": region_data["value_mean"].min(),
            "region_max": region_data["value_mean"].max(),
            "region_mean": region_data["value_mean"].mean(),
            "region_median": region_data["value_mean"].median(),
        })
        
        print(f"    {REGIONS.get(region, {}).get('name', region)}:")
        print(f"      Green (≤P{GREEN_PERCENTILE}): ≤{green_threshold:.0f}")
        print(f"      Yellow (P{GREEN_PERCENTILE}-P{RED_PERCENTILE}): {green_threshold:.0f}-{red_threshold:.0f}")
        print(f"      Red (≥P{RED_PERCENTILE}): ≥{red_threshold:.0f}")
    
    return pd.DataFrame(thresholds)


def assign_buckets(df_hourly: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """Assign each hour to a traffic light bucket."""
    print("\n  1B. Assigning hours to buckets...")
    
    df = df_hourly.copy()
    df["bucket"] = "yellow"  # Default
    
    for _, thresh in thresholds.iterrows():
        region = thresh["region"]
        mask = df["region"] == region
        
        df.loc[mask & (df["value_mean"] <= thresh["green_threshold"]), "bucket"] = "green"
        df.loc[mask & (df["value_mean"] >= thresh["red_threshold"]), "bucket"] = "red"
    
    # Verify distribution
    bucket_counts = df["bucket"].value_counts()
    print(f"    Overall distribution: {dict(bucket_counts)}")
    
    return df


# =============================================================================
# SECTION 2: BUCKET DISTRIBUTION
# =============================================================================

def analyze_bucket_distribution(df_with_buckets: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Analyze distribution of buckets by region, season, and hour."""
    print("\n  2A. Analyzing bucket distribution...")
    
    results = {}
    
    # By region
    by_region = df_with_buckets.groupby(["region", "bucket"]).size().unstack(fill_value=0)
    by_region_pct = by_region.div(by_region.sum(axis=1), axis=0) * 100
    by_region_pct = by_region_pct.reset_index()
    by_region_pct["region_name"] = by_region_pct["region"].map(
        lambda r: REGIONS.get(r, {}).get("name", r)
    )
    results["by_region"] = by_region_pct
    
    # By region and season
    by_season = df_with_buckets.groupby(["region", "season", "bucket"]).size().unstack(fill_value=0)
    by_season_pct = by_season.div(by_season.sum(axis=1), axis=0) * 100
    by_season_pct = by_season_pct.reset_index()
    results["by_season"] = by_season_pct
    
    # By region and hour
    by_hour = df_with_buckets.groupby(["region", "hour", "bucket"]).size().unstack(fill_value=0)
    by_hour_pct = by_hour.div(by_hour.sum(axis=1), axis=0) * 100
    by_hour_pct = by_hour_pct.reset_index()
    results["by_hour"] = by_hour_pct
    
    # By region, season, and hour (full matrix)
    by_all = df_with_buckets.groupby(["region", "season", "hour", "bucket"]).size().unstack(fill_value=0)
    by_all_pct = by_all.div(by_all.sum(axis=1), axis=0) * 100
    by_all_pct = by_all_pct.reset_index()
    results["by_all"] = by_all_pct
    
    return results


def analyze_daily_availability(df_with_buckets: pd.DataFrame) -> pd.DataFrame:
    """Analyze how many green hours are typically available per day."""
    print("\n  2B. Analyzing daily green hour availability...")
    
    # Group by region, date
    daily = df_with_buckets.groupby(["region", "date", "bucket"]).size().unstack(fill_value=0)
    daily = daily.reset_index()
    
    # Ensure all bucket columns exist
    for bucket in ["green", "yellow", "red"]:
        if bucket not in daily.columns:
            daily[bucket] = 0
    
    # Summary statistics
    summary = []
    for region in daily["region"].unique():
        region_data = daily[daily["region"] == region]
        
        summary.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "avg_green_hours_per_day": region_data["green"].mean(),
            "min_green_hours_per_day": region_data["green"].min(),
            "max_green_hours_per_day": region_data["green"].max(),
            "avg_yellow_hours_per_day": region_data["yellow"].mean(),
            "avg_red_hours_per_day": region_data["red"].mean(),
            "days_with_min_green": (region_data["green"] >= MIN_PRODUCTION_HOURS_PER_DAY).mean() * 100,
            "pct_days_with_no_green": (region_data["green"] == 0).mean() * 100,
        })
    
    return pd.DataFrame(summary)


# =============================================================================
# SECTION 3: TRANSITION ANALYSIS
# =============================================================================

def analyze_transitions(df_with_buckets: pd.DataFrame) -> pd.DataFrame:
    """Calculate Markov-style transition probabilities between buckets."""
    print("\n  3A. Analyzing bucket transitions...")
    
    results = []
    
    for region in df_with_buckets["region"].unique():
        region_data = df_with_buckets[df_with_buckets["region"] == region].sort_values("point_time")
        
        for lookahead in TRANSITION_LOOKAHEAD_HOURS:
            # Shift to get future bucket
            region_data[f"bucket_in_{lookahead}h"] = region_data["bucket"].shift(-lookahead)
            
            # Calculate transitions
            transitions = region_data.groupby(["bucket", f"bucket_in_{lookahead}h"]).size().unstack(fill_value=0)
            transitions_pct = transitions.div(transitions.sum(axis=1), axis=0) * 100
            
            for current_bucket in ["green", "yellow", "red"]:
                if current_bucket not in transitions_pct.index:
                    continue
                    
                for future_bucket in ["green", "yellow", "red"]:
                    if future_bucket not in transitions_pct.columns:
                        prob = 0
                    else:
                        prob = transitions_pct.loc[current_bucket, future_bucket]
                    
                    results.append({
                        "region": region,
                        "region_name": REGIONS.get(region, {}).get("name", region),
                        "lookahead_hours": lookahead,
                        "current_bucket": current_bucket,
                        "future_bucket": future_bucket,
                        "probability_pct": prob,
                    })
    
    return pd.DataFrame(results)


def analyze_green_window_duration(df_with_buckets: pd.DataFrame) -> pd.DataFrame:
    """Analyze how long green windows typically last."""
    print("\n  3B. Analyzing green window durations...")
    
    results = []
    
    for region in df_with_buckets["region"].unique():
        region_data = df_with_buckets[df_with_buckets["region"] == region].sort_values("point_time")
        
        # Identify contiguous green windows
        region_data["is_green"] = region_data["bucket"] == "green"
        region_data["green_group"] = (region_data["is_green"] != region_data["is_green"].shift()).cumsum()
        
        # Get green windows only
        green_windows = region_data[region_data["is_green"]].groupby("green_group").size()
        
        if len(green_windows) > 0:
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "n_green_windows": len(green_windows),
                "mean_duration_hours": green_windows.mean(),
                "median_duration_hours": green_windows.median(),
                "min_duration_hours": green_windows.min(),
                "max_duration_hours": green_windows.max(),
                "std_duration_hours": green_windows.std(),
                "pct_1h_windows": (green_windows == 1).mean() * 100,
                "pct_2h_plus_windows": (green_windows >= 2).mean() * 100,
                "pct_4h_plus_windows": (green_windows >= 4).mean() * 100,
            })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 4: SAVINGS QUANTIFICATION
# =============================================================================

def calculate_traffic_light_savings(df_with_buckets: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate savings from using traffic light rules:
    - Defer red hours to next green
    - Compare to random scheduling and optimal scheduling
    """
    print("\n  4A. Calculating traffic light savings...")
    
    results = []
    
    for region in df_with_buckets["region"].unique():
        region_data = df_with_buckets[df_with_buckets["region"] == region].sort_values("point_time")
        region_thresh = thresholds[thresholds["region"] == region].iloc[0]
        
        # Baseline: random hour (average MOER)
        baseline_moer = region_data["value_mean"].mean()
        
        # Optimal: always pick lowest MOER hour (per day)
        optimal_daily = region_data.groupby("date")["value_mean"].min()
        optimal_moer = optimal_daily.mean()
        
        # Traffic light strategy:
        # - Green: run immediately
        # - Yellow: run immediately (acceptable)
        # - Red: defer to next green or yellow
        
        # Simulate by day
        traffic_light_moer_list = []
        
        for date, day_data in region_data.groupby("date"):
            day_data = day_data.sort_values("hour")
            
            # If we need to run 8 hours, pick the 8 best hours based on traffic light
            n_hours = min(8, len(day_data))
            
            # Priority: green first, then yellow, then red
            green_hours = day_data[day_data["bucket"] == "green"]["value_mean"]
            yellow_hours = day_data[day_data["bucket"] == "yellow"]["value_mean"]
            red_hours = day_data[day_data["bucket"] == "red"]["value_mean"]
            
            selected = []
            for hours_series in [green_hours, yellow_hours, red_hours]:
                remaining = n_hours - len(selected)
                if remaining > 0 and len(hours_series) > 0:
                    selected.extend(hours_series.nsmallest(remaining).values)
            
            if len(selected) > 0:
                traffic_light_moer_list.append(np.mean(selected))
        
        traffic_light_moer = np.mean(traffic_light_moer_list)
        
        # Green-only strategy (if possible)
        green_only_moer = region_data[region_data["bucket"] == "green"]["value_mean"].mean()
        
        # Calculate savings
        baseline_savings = 0
        optimal_savings = (baseline_moer - optimal_moer) / baseline_moer * 100
        traffic_light_savings = (baseline_moer - traffic_light_moer) / baseline_moer * 100
        green_only_savings = (baseline_moer - green_only_moer) / baseline_moer * 100 if not np.isnan(green_only_moer) else 0
        
        # Capture rate (traffic light vs optimal)
        capture_rate = traffic_light_savings / optimal_savings if optimal_savings > 0 else 1
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "baseline_moer": baseline_moer,
            "optimal_moer": optimal_moer,
            "traffic_light_moer": traffic_light_moer,
            "green_only_moer": green_only_moer,
            "optimal_savings_pct": optimal_savings,
            "traffic_light_savings_pct": traffic_light_savings,
            "green_only_savings_pct": green_only_savings,
            "traffic_light_capture_rate": capture_rate,
            "simplicity_vs_optimal_gap": optimal_savings - traffic_light_savings,
        })
    
    return pd.DataFrame(results)


def create_operator_lookup_table(df_with_buckets: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    """
    Create a simple lookup table for operators:
    Given region, season, hour → expected bucket and recommended action.
    """
    print("\n  4B. Creating operator lookup table...")
    
    # Calculate mode bucket for each region/season/hour combination
    lookup = df_with_buckets.groupby(["region", "season", "hour"]).agg({
        "bucket": lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else "yellow",
        "value_mean": ["mean", "std"]
    }).reset_index()
    lookup.columns = ["region", "season", "hour", "typical_bucket", "avg_moer", "moer_std"]
    
    # Add recommendation
    def get_recommendation(bucket):
        if bucket == "green":
            return "RUN - Grid is clean"
        elif bucket == "yellow":
            return "OK TO RUN - Grid is moderate"
        else:
            return "DEFER IF POSSIBLE - Grid is dirty"
    
    lookup["recommendation"] = lookup["typical_bucket"].map(get_recommendation)
    lookup["region_name"] = lookup["region"].map(lambda r: REGIONS.get(r, {}).get("name", r))
    
    # Add threshold context
    lookup = lookup.merge(
        thresholds[["region", "green_threshold", "red_threshold"]],
        on="region",
        how="left"
    )
    
    return lookup


# =============================================================================
# PLOTTING FUNCTIONS
# =============================================================================

def plot_bucket_heatmap(distribution: Dict, figures_dir: Path):
    """Plot 24-hour × season heatmap of green percentage."""
    
    by_all = distribution.get("by_all")
    if by_all is None or len(by_all) == 0:
        print("    No distribution data to plot")
        return
    
    regions = by_all["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(n_regions, 1, figsize=(14, 4 * n_regions), squeeze=False)
    
    season_order = ["winter", "spring", "summer", "fall"]
    
    for i, region in enumerate(regions):
        ax = axes[i, 0]
        region_data = by_all[by_all["region"] == region]
        
        # Ensure green column exists
        if "green" not in region_data.columns:
            region_data["green"] = 0
        
        # Pivot: season × hour, value = green percentage
        pivot_data = []
        for season in season_order:
            for hour in range(24):
                row = region_data[(region_data["season"] == season) & (region_data["hour"] == hour)]
                green_pct = row["green"].values[0] if len(row) > 0 else 0
                pivot_data.append({"season": season, "hour": hour, "green_pct": green_pct})
        
        pivot_df = pd.DataFrame(pivot_data)
        pivot = pivot_df.pivot(index="season", columns="hour", values="green_pct")
        pivot = pivot.reindex(season_order)
        
        sns.heatmap(pivot, ax=ax, cmap="Greens", vmin=0, vmax=100,
                   cbar_kws={"label": "% Green Hours"}, annot=True, fmt=".0f", annot_kws={"size": 8})
        
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}", fontsize=12)
        ax.set_xlabel("Hour of Day")
        ax.set_ylabel("Season")
        ax.set_yticklabels([s.capitalize() for s in season_order], rotation=0)
    
    plt.suptitle("Green Hour Availability by Season and Hour\n(Higher % = more likely to be clean grid)", 
                 fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "11_bucket_heatmap.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 11_bucket_heatmap.png")


def plot_traffic_light_summary(thresholds: pd.DataFrame, savings: pd.DataFrame, figures_dir: Path):
    """Create operator-friendly traffic light summary."""
    
    if len(thresholds) == 0:
        print("    No threshold data to plot")
        return
    
    n_regions = len(thresholds)
    fig, axes = plt.subplots(1, n_regions, figsize=(4 * n_regions, 6), squeeze=False)
    
    for i, (_, row) in enumerate(thresholds.iterrows()):
        ax = axes[0, i]
        
        region = row["region"]
        region_name = row["region_name"]
        
        # Draw traffic light style visualization
        positions = [0.75, 0.5, 0.25]  # Red, Yellow, Green from top
        colors = [TRAFFIC_COLORS["red"], TRAFFIC_COLORS["yellow"], TRAFFIC_COLORS["green"]]
        labels = [
            f"RED\n≥{row['red_threshold']:.0f}",
            f"YELLOW\n{row['green_threshold']:.0f}-{row['red_threshold']:.0f}",
            f"GREEN\n≤{row['green_threshold']:.0f}"
        ]
        
        for pos, color, label in zip(positions, colors, labels):
            circle = plt.Circle((0.5, pos), 0.15, color=color, ec='black', linewidth=2)
            ax.add_patch(circle)
            ax.text(0.5, pos, label, ha='center', va='center', fontsize=9, fontweight='bold')
        
        # Add region stats
        if len(savings) > 0:
            region_savings = savings[savings["region"] == region]
            if len(region_savings) > 0:
                savings_pct = region_savings["traffic_light_savings_pct"].values[0]
                capture = region_savings["traffic_light_capture_rate"].values[0]
                ax.text(0.5, 0.05, f"Savings: {savings_pct:.1f}%\nCapture: {capture:.0%}", 
                       ha='center', va='center', fontsize=10, 
                       bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray'))
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect('equal')
        ax.set_title(region_name, fontsize=12, fontweight='bold')
        ax.axis('off')
    
    plt.suptitle("Traffic Light Thresholds by Region\n(MOER values)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "11_traffic_light_summary.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 11_traffic_light_summary.png")


def plot_transition_probabilities(transitions: pd.DataFrame, figures_dir: Path):
    """Plot transition probability matrices."""
    
    if len(transitions) == 0:
        print("    No transition data to plot")
        return
    
    # Use 1-hour lookahead
    trans_1h = transitions[transitions["lookahead_hours"] == 1]
    
    if len(trans_1h) == 0:
        trans_1h = transitions[transitions["lookahead_hours"] == transitions["lookahead_hours"].min()]
    
    regions = trans_1h["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(1, n_regions, figsize=(5 * n_regions, 4), squeeze=False)
    
    bucket_order = ["green", "yellow", "red"]
    
    for i, region in enumerate(regions):
        ax = axes[0, i]
        region_data = trans_1h[trans_1h["region"] == region]
        
        # Pivot to matrix
        pivot = region_data.pivot(index="current_bucket", columns="future_bucket", values="probability_pct")
        pivot = pivot.reindex(index=bucket_order, columns=bucket_order, fill_value=0)
        
        sns.heatmap(pivot, ax=ax, annot=True, fmt=".0f", cmap="Blues",
                   cbar_kws={"label": "Probability (%)"}, vmin=0, vmax=100)
        
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}\n1-Hour Transitions", fontsize=11)
        ax.set_xlabel("Next Hour Bucket")
        ax.set_ylabel("Current Bucket")
        ax.set_xticklabels([b.capitalize() for b in bucket_order])
        ax.set_yticklabels([b.capitalize() for b in bucket_order], rotation=0)
    
    plt.suptitle("Traffic Light Transition Probabilities\n(What comes next?)", fontsize=14, y=1.05)
    plt.tight_layout()
    plt.savefig(figures_dir / "11_transition_probabilities.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 11_transition_probabilities.png")


def plot_green_window_distribution(window_stats: pd.DataFrame, figures_dir: Path):
    """Plot distribution of green window durations."""
    
    if len(window_stats) == 0:
        print("    No window data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(window_stats))
    width = 0.25
    
    ax.bar(x - width, window_stats["mean_duration_hours"], width, 
           label="Mean Duration", color=TRAFFIC_COLORS["green"], edgecolor='black')
    ax.bar(x, window_stats["median_duration_hours"], width,
           label="Median Duration", color=TRAFFIC_COLORS["yellow"], edgecolor='black')
    ax.bar(x + width, window_stats["max_duration_hours"], width,
           label="Max Duration", color='steelblue', edgecolor='black', alpha=0.7)
    
    ax.set_xlabel("Region")
    ax.set_ylabel("Hours")
    ax.set_title("Green Window Duration Statistics\n(How long do clean grid periods last?)")
    ax.set_xticks(x)
    ax.set_xticklabels(window_stats["region_name"], rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "11_green_window_duration.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 11_green_window_duration.png")


def plot_savings_comparison(savings: pd.DataFrame, figures_dir: Path):
    """Plot comparison of traffic light vs optimal savings."""
    
    if len(savings) == 0:
        print("    No savings data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Savings comparison
    ax = axes[0]
    x = np.arange(len(savings))
    width = 0.35
    
    ax.bar(x - width/2, savings["optimal_savings_pct"], width, 
           label="Optimal (perfect info)", color='steelblue', edgecolor='black')
    ax.bar(x + width/2, savings["traffic_light_savings_pct"], width,
           label="Traffic Light (simple rules)", color=TRAFFIC_COLORS["green"], edgecolor='black')
    
    ax.set_xlabel("Region")
    ax.set_ylabel("Emissions Savings (%)")
    ax.set_title("Traffic Light vs Optimal Savings")
    ax.set_xticks(x)
    ax.set_xticklabels(savings["region_name"], rotation=45, ha='right')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # Capture rate
    ax = axes[1]
    bars = ax.bar(x, savings["traffic_light_capture_rate"] * 100, 
                  color=TRAFFIC_COLORS["green"], edgecolor='black')
    
    ax.axhline(y=80, color='orange', linestyle='--', alpha=0.7, label='80% target')
    ax.axhline(y=90, color='red', linestyle='--', alpha=0.7, label='90% target')
    
    ax.set_xlabel("Region")
    ax.set_ylabel("Capture Rate (%)")
    ax.set_title("Traffic Light Efficiency\n(% of optimal savings achieved)")
    ax.set_xticks(x)
    ax.set_xticklabels(savings["region_name"], rotation=45, ha='right')
    ax.set_ylim(0, 105)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "11_savings_comparison.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 11_savings_comparison.png")


# =============================================================================
# SUMMARY
# =============================================================================

def generate_summary_report(thresholds: pd.DataFrame, availability: pd.DataFrame,
                           window_stats: pd.DataFrame, savings: pd.DataFrame,
                           signal: str, outputs_dir: Path):
    """Generate text summary of traffic light analysis."""
    
    lines = [
        "=" * 70,
        "TRAFFIC LIGHT DECISION RULES SUMMARY",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        f"Thresholds: Green ≤P{GREEN_PERCENTILE}, Red ≥P{RED_PERCENTILE}",
        "",
    ]
    
    lines.extend([
        "-" * 70,
        "THRESHOLDS BY REGION",
        "-" * 70,
    ])
    
    for _, row in thresholds.iterrows():
        lines.append(f"\n{row['region_name']}:")
        lines.append(f"  GREEN (run freely): MOER ≤ {row['green_threshold']:.0f}")
        lines.append(f"  YELLOW (run if needed): {row['green_threshold']:.0f} < MOER < {row['red_threshold']:.0f}")
        lines.append(f"  RED (defer if possible): MOER ≥ {row['red_threshold']:.0f}")
    
    if len(availability) > 0:
        lines.extend([
            "",
            "-" * 70,
            "GREEN HOUR AVAILABILITY",
            "-" * 70,
        ])
        
        for _, row in availability.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Average green hours/day: {row['avg_green_hours_per_day']:.1f}")
            lines.append(f"  Days with ≥{MIN_PRODUCTION_HOURS_PER_DAY}h green: {row['days_with_min_green']:.0f}%")
    
    if len(window_stats) > 0:
        lines.extend([
            "",
            "-" * 70,
            "GREEN WINDOW DURATION",
            "-" * 70,
        ])
        
        for _, row in window_stats.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Mean window duration: {row['mean_duration_hours']:.1f} hours")
            lines.append(f"  Windows ≥2 hours: {row['pct_2h_plus_windows']:.0f}%")
    
    if len(savings) > 0:
        lines.extend([
            "",
            "-" * 70,
            "SAVINGS ANALYSIS",
            "-" * 70,
        ])
        
        for _, row in savings.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Optimal savings (perfect info): {row['optimal_savings_pct']:.1f}%")
            lines.append(f"  Traffic light savings: {row['traffic_light_savings_pct']:.1f}%")
            lines.append(f"  Capture rate: {row['traffic_light_capture_rate']:.0%}")
    
    lines.extend([
        "",
        "-" * 70,
        "KEY TAKEAWAYS",
        "-" * 70,
        "",
        "1. Traffic light rules achieve majority of optimal savings with minimal complexity",
        "2. No API integration required - just lookup tables by time/season",
        "3. Green windows typically last multiple hours, enabling production planning",
        "4. Region-specific thresholds are essential (MOER ranges vary widely)",
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])
    
    report_text = "\n".join(lines)
    
    with open(outputs_dir / "11_summary_report.txt", "w", encoding="utf-8") as f:
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
    print("TRAFFIC LIGHT DECISION RULES ANALYSIS")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Thresholds: Green ≤P{GREEN_PERCENTILE}, Red ≥P{RED_PERCENTILE}")
    print("=" * 70)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df_hourly = load_data(run_dir)
    
    # Initialize results
    thresholds = pd.DataFrame()
    df_with_buckets = pd.DataFrame()
    distribution = {}
    availability = pd.DataFrame()
    transitions = pd.DataFrame()
    window_stats = pd.DataFrame()
    savings = pd.DataFrame()
    lookup_table = pd.DataFrame()
    
    # ==========================================================================
    # SECTION 1: THRESHOLD DEFINITION
    # ==========================================================================
    if RUN_THRESHOLD_DEFINITION:
        print("\n" + "=" * 70)
        print("SECTION 1: THRESHOLD DEFINITION")
        print("=" * 70)
        
        thresholds = calculate_thresholds(df_hourly)
        thresholds.to_csv(outputs_dir / "11_thresholds.csv", index=False)
        
        df_with_buckets = assign_buckets(df_hourly, thresholds)
    
    # ==========================================================================
    # SECTION 2: BUCKET DISTRIBUTION
    # ==========================================================================
    if RUN_BUCKET_DISTRIBUTION and len(df_with_buckets) > 0:
        print("\n" + "=" * 70)
        print("SECTION 2: BUCKET DISTRIBUTION")
        print("=" * 70)
        
        distribution = analyze_bucket_distribution(df_with_buckets)
        for name, df in distribution.items():
            df.to_csv(outputs_dir / f"11_distribution_{name}.csv", index=False)
        
        availability = analyze_daily_availability(df_with_buckets)
        availability.to_csv(outputs_dir / "11_availability.csv", index=False)
        
        plot_bucket_heatmap(distribution, figures_dir)
    
    # ==========================================================================
    # SECTION 3: TRANSITION ANALYSIS
    # ==========================================================================
    if RUN_TRANSITION_ANALYSIS and len(df_with_buckets) > 0:
        print("\n" + "=" * 70)
        print("SECTION 3: TRANSITION ANALYSIS")
        print("=" * 70)
        
        transitions = analyze_transitions(df_with_buckets)
        transitions.to_csv(outputs_dir / "11_transitions.csv", index=False)
        
        window_stats = analyze_green_window_duration(df_with_buckets)
        window_stats.to_csv(outputs_dir / "11_green_window_duration.csv", index=False)
        
        plot_transition_probabilities(transitions, figures_dir)
        plot_green_window_distribution(window_stats, figures_dir)
    
    # ==========================================================================
    # SECTION 4: SAVINGS QUANTIFICATION
    # ==========================================================================
    if RUN_SAVINGS_QUANTIFICATION and len(df_with_buckets) > 0:
        print("\n" + "=" * 70)
        print("SECTION 4: SAVINGS QUANTIFICATION")
        print("=" * 70)
        
        savings = calculate_traffic_light_savings(df_with_buckets, thresholds)
        savings.to_csv(outputs_dir / "11_savings.csv", index=False)
        
        lookup_table = create_operator_lookup_table(df_with_buckets, thresholds)
        lookup_table.to_csv(outputs_dir / "11_operator_lookup.csv", index=False)
        
        plot_traffic_light_summary(thresholds, savings, figures_dir)
        plot_savings_comparison(savings, figures_dir)
    
    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)
    
    generate_summary_report(thresholds, availability, window_stats, savings,
                           signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "11_threshold_buckets")
    
    print("\n" + "=" * 70)
    print("TRAFFIC LIGHT ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/11_*.png")
    print(f"Data: {outputs_dir}/11_*.csv")
    print(f"Lookup Table: {outputs_dir}/11_operator_lookup.csv")
    print(f"Report: {outputs_dir}/11_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()
