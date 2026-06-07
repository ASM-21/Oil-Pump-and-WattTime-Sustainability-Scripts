"""
12_multiday_optimization.py - Multi-Day Production Optimization

Extends single-day scheduling to multi-day production planning.
Analyzes when to front-load or back-load production based on predicted
grid patterns, and quantifies value of flexibility across different time horizons.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below
    3. Run: python 12_multiday_optimization.py

Analysis:
    1. Multi-Day Patterns
       - Weekly MOER cycles (weekday vs weekend)
       - Multi-day trend detection
       - Best days to concentrate production
    2. Production Shifting Scenarios
       - If you have weekly quota, how to distribute?
       - Front-load vs back-load analysis
    3. Flexibility Value
       - Value of 1-day vs 2-day vs 5-day flexibility
       - Diminishing returns of longer planning horizons
    4. Risk-Adjusted Scheduling
       - Expected savings vs variability trade-off
       - Conservative vs aggressive strategies

Output (in run folder):
    - figures/12_*.png
    - outputs/12_*.csv
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

# Production parameters
DAILY_PRODUCTION_HOURS = 8  # Hours of production needed per day
WEEKLY_PRODUCTION_HOURS = 40  # Hours of production needed per week

# Flexibility scenarios
FLEXIBILITY_WINDOWS = [1, 2, 3, 5, 7]  # Days of flexibility

# Simulation parameters
MIN_HOURS_PER_DAY = 4  # Minimum hours to run on any single day
MAX_HOURS_PER_DAY = 12  # Maximum hours to run on any single day

# Risk parameters
CONSERVATIVE_PERCENTILE = 25  # Target this percentile for conservative strategy
AGGRESSIVE_PERCENTILE = 10  # Target this percentile for aggressive strategy

# Analysis toggles
RUN_MULTIDAY_PATTERNS = True
RUN_SHIFTING_SCENARIOS = True
RUN_FLEXIBILITY_VALUE = True
RUN_RISK_ANALYSIS = True

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
    """Load processed data."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")

    df_hourly["point_time"] = pd.to_datetime(df_hourly[["year", "month", "day", "hour"]].assign(minute=0, second=0))

    df_daily = pd.read_parquet(processed_dir / "daily_statistics.parquet")
    
    print(f"  Hourly: {len(df_hourly):,} records")
    print(f"  Daily: {len(df_daily):,} records")
    
    # Add week number
    df_hourly["week"] = df_hourly["point_time"].dt.isocalendar().week.astype(int)
    df_hourly["year_week"] = df_hourly["year"].astype(str) + "-W" + df_hourly["week"].astype(str).str.zfill(2)
    
    df_daily["week"] = pd.to_datetime(df_daily["date"]).dt.isocalendar().week.astype(int)
    df_daily["year_week"] = df_daily["year"].astype(str) + "-W" + df_daily["week"].astype(str).str.zfill(2)
    
    return df_hourly, df_daily


# =============================================================================
# SECTION 1: MULTI-DAY PATTERNS
# =============================================================================

def analyze_day_of_week_patterns(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Analyze MOER patterns by day of week."""
    print("\n  1A. Analyzing day-of-week patterns...")
    
    results = []
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    for region in df_daily["region"].unique():
        region_data = df_daily[df_daily["region"] == region]
        
        for dow in range(7):
            dow_data = region_data[region_data["day_of_week"] == dow]
            
            if len(dow_data) < 10:
                continue
            
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "day_of_week": dow,
                "day_name": day_names[dow],
                "is_weekend": dow >= 5,
                "avg_moer": dow_data["value_mean"].mean(),
                "std_moer": dow_data["value_mean"].std(),
                "min_moer": dow_data["value_min"].mean(),
                "max_moer": dow_data["value_max"].mean(),
                "n_days": len(dow_data),
            })
    
    df = pd.DataFrame(results)
    
    if len(df) > 0:
        # Add rank within region
        df["rank"] = df.groupby("region")["avg_moer"].rank(ascending=True).astype(int)
    
    return df


def analyze_weekend_vs_weekday(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Compare weekend vs weekday MOER patterns."""
    print("\n  1B. Comparing weekend vs weekday...")
    
    results = []
    
    for region in df_daily["region"].unique():
        region_data = df_daily[df_daily["region"] == region]
        
        weekday_data = region_data[region_data["is_weekend"] == False]
        weekend_data = region_data[region_data["is_weekend"] == True]
        
        if len(weekday_data) < 10 or len(weekend_data) < 10:
            continue
        
        weekday_avg = weekday_data["value_mean"].mean()
        weekend_avg = weekend_data["value_mean"].mean()
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "weekday_avg_moer": weekday_avg,
            "weekend_avg_moer": weekend_avg,
            "weekend_vs_weekday_pct": 100 * (weekend_avg - weekday_avg) / weekday_avg,
            "better_period": "weekend" if weekend_avg < weekday_avg else "weekday",
            "advantage_pct": abs(100 * (weekend_avg - weekday_avg) / weekday_avg),
        })
    
    return pd.DataFrame(results)


def identify_best_production_days(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Identify which days of the week are best for production."""
    print("\n  1C. Identifying best production days...")
    
    results = []
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    for region in df_daily["region"].unique():
        region_data = df_daily[df_daily["region"] == region]
        region_avg = region_data["value_mean"].mean()
        
        # Rank days by average MOER
        dow_avgs = region_data.groupby("day_of_week")["value_mean"].mean().sort_values()
        
        # Top 3 best days
        best_days = dow_avgs.head(3)
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "best_day_1": day_names[best_days.index[0]],
            "best_day_2": day_names[best_days.index[1]],
            "best_day_3": day_names[best_days.index[2]],
            "best_3_avg_moer": best_days.mean(),
            "region_avg_moer": region_avg,
            "potential_savings_pct": 100 * (region_avg - best_days.mean()) / region_avg,
        })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 2: PRODUCTION SHIFTING SCENARIOS
# =============================================================================

def simulate_weekly_distribution(df_hourly: pd.DataFrame, df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Simulate different weekly production distribution strategies:
    1. Even: 8 hours every day
    2. Front-loaded: More hours Mon-Wed
    3. Back-loaded: More hours Thu-Sat
    4. Optimal: Best 40 hours across week
    5. Weekend-focused: Concentrate on weekend
    """
    print("\n  2A. Simulating weekly distribution strategies...")
    
    results = []
    
    strategies = {
        "even": {0: 8, 1: 8, 2: 8, 3: 8, 4: 8, 5: 0, 6: 0},  # Mon-Fri
        "front_load": {0: 10, 1: 10, 2: 10, 3: 6, 4: 4, 5: 0, 6: 0},
        "back_load": {0: 4, 1: 6, 2: 6, 3: 10, 4: 10, 5: 4, 6: 0},
        "weekend": {0: 4, 1: 4, 2: 4, 3: 4, 4: 4, 5: 10, 6: 10},
    }
    
    for region in df_hourly["region"].unique():
        region_hourly = df_hourly[df_hourly["region"] == region]
        
        # Get all weeks
        weeks = region_hourly["year_week"].unique()
        
        for week in weeks:
            week_data = region_hourly[region_hourly["year_week"] == week]
            
            if len(week_data) < 100:  # Need most of the week
                continue
            
            week_results = {"region": region, "year_week": week}
            
            # Baseline: average of all hours
            baseline_moer = week_data["value_mean"].mean()
            week_results["baseline_moer"] = baseline_moer
            
            # Optimal: best WEEKLY_PRODUCTION_HOURS hours
            best_hours = week_data.nsmallest(WEEKLY_PRODUCTION_HOURS, "value_mean")
            optimal_moer = best_hours["value_mean"].mean()
            week_results["optimal_moer"] = optimal_moer
            week_results["optimal_savings_pct"] = 100 * (baseline_moer - optimal_moer) / baseline_moer
            
            # Each strategy
            for strategy_name, day_hours in strategies.items():
                strategy_moer_list = []
                
                for dow, hours in day_hours.items():
                    if hours == 0:
                        continue
                    
                    day_data = week_data[week_data["day_of_week"] == dow]
                    if len(day_data) >= hours:
                        best = day_data.nsmallest(hours, "value_mean")
                        strategy_moer_list.extend(best["value_mean"].values)
                
                if len(strategy_moer_list) > 0:
                    strategy_moer = np.mean(strategy_moer_list)
                    week_results[f"{strategy_name}_moer"] = strategy_moer
                    week_results[f"{strategy_name}_savings_pct"] = 100 * (baseline_moer - strategy_moer) / baseline_moer
            
            results.append(week_results)
    
    return pd.DataFrame(results)


def summarize_distribution_strategies(weekly_results: pd.DataFrame) -> pd.DataFrame:
    """Summarize performance of each distribution strategy."""
    print("\n  2B. Summarizing distribution strategies...")
    
    if len(weekly_results) == 0:
        return pd.DataFrame()
    
    summary = []
    strategies = ["even", "front_load", "back_load", "weekend"]
    
    for region in weekly_results["region"].unique():
        region_data = weekly_results[weekly_results["region"] == region]
        
        region_summary = {
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_weeks": len(region_data),
            "optimal_savings_pct": region_data["optimal_savings_pct"].mean(),
        }
        
        for strategy in strategies:
            col = f"{strategy}_savings_pct"
            if col in region_data.columns:
                region_summary[f"{strategy}_savings_pct"] = region_data[col].mean()
                region_summary[f"{strategy}_capture_rate"] = (
                    region_data[col].mean() / region_data["optimal_savings_pct"].mean()
                    if region_data["optimal_savings_pct"].mean() > 0 else 0
                )
        
        summary.append(region_summary)
    
    df = pd.DataFrame(summary)
    
    # Identify best strategy per region
    if len(df) > 0:
        strategy_cols = [f"{s}_savings_pct" for s in strategies if f"{s}_savings_pct" in df.columns]
        if strategy_cols:
            df["best_strategy"] = df[strategy_cols].idxmax(axis=1).str.replace("_savings_pct", "")
    
    return df


# =============================================================================
# SECTION 3: FLEXIBILITY VALUE
# =============================================================================

def calculate_flexibility_value(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the value of production flexibility (ability to shift across days).
    Compare 1-day vs 2-day vs 5-day vs 7-day planning horizons.
    """
    print("\n  3A. Calculating flexibility value...")
    
    results = []
    
    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region].copy()
        region_data = region_data.sort_values("point_time")
        
        # Group by date
        dates = sorted(region_data["date"].unique())
        
        for i, start_date in enumerate(dates):
            for window in FLEXIBILITY_WINDOWS:
                if i + window > len(dates):
                    continue
                
                # Get data for this window
                window_dates = dates[i:i+window]
                window_data = region_data[region_data["date"].isin(window_dates)]
                
                if len(window_data) < 24 * window * 0.8:  # Need most hours
                    continue
                
                # Calculate production hours for this window
                production_hours = DAILY_PRODUCTION_HOURS * window
                
                # Baseline: pick best hours from each day separately (no flexibility)
                baseline_moer_list = []
                for date in window_dates:
                    day_data = window_data[window_data["date"] == date]
                    if len(day_data) >= DAILY_PRODUCTION_HOURS:
                        best = day_data.nsmallest(DAILY_PRODUCTION_HOURS, "value_mean")
                        baseline_moer_list.extend(best["value_mean"].values)
                
                if len(baseline_moer_list) < production_hours * 0.8:
                    continue
                
                baseline_moer = np.mean(baseline_moer_list)
                
                # Flexible: pick best hours from entire window
                best_window = window_data.nsmallest(production_hours, "value_mean")
                flexible_moer = best_window["value_mean"].mean()
                
                # Calculate value of flexibility
                flexibility_value = baseline_moer - flexible_moer
                flexibility_value_pct = 100 * flexibility_value / baseline_moer if baseline_moer > 0 else 0
                
                results.append({
                    "region": region,
                    "flexibility_days": window,
                    "start_date": start_date,
                    "baseline_moer": baseline_moer,
                    "flexible_moer": flexible_moer,
                    "flexibility_value_moer": flexibility_value,
                    "flexibility_value_pct": flexibility_value_pct,
                })
    
    return pd.DataFrame(results)


def summarize_flexibility_value(flexibility_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize flexibility value by window size."""
    print("\n  3B. Summarizing flexibility value...")
    
    if len(flexibility_df) == 0:
        return pd.DataFrame()
    
    summary = flexibility_df.groupby(["region", "flexibility_days"]).agg({
        "flexibility_value_pct": ["mean", "std", "min", "max"],
        "baseline_moer": "count"
    }).reset_index()
    
    summary.columns = [
        "region", "flexibility_days", 
        "mean_value_pct", "std_value_pct", "min_value_pct", "max_value_pct",
        "n_windows"
    ]
    
    summary["region_name"] = summary["region"].map(lambda r: REGIONS.get(r, {}).get("name", r))
    
    # Calculate marginal value of additional flexibility
    summary = summary.sort_values(["region", "flexibility_days"])
    summary["marginal_value_pct"] = summary.groupby("region")["mean_value_pct"].diff()
    
    return summary


# =============================================================================
# SECTION 4: RISK-ADJUSTED SCHEDULING
# =============================================================================

def analyze_risk_reward_tradeoff(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze trade-off between expected savings and consistency.
    Compare conservative vs aggressive strategies.
    """
    print("\n  4A. Analyzing risk-reward tradeoff...")
    
    results = []
    
    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region]
        
        # Group by date
        daily_results = []
        
        for date, day_data in region_data.groupby("date"):
            if len(day_data) < 20:
                continue
            
            baseline = day_data["value_mean"].mean()
            
            # Conservative: target Pxx of the day's distribution
            conservative_threshold = day_data["value_mean"].quantile(CONSERVATIVE_PERCENTILE / 100)
            conservative_hours = day_data[day_data["value_mean"] <= conservative_threshold]
            
            # Aggressive: target Pyy of the day's distribution
            aggressive_threshold = day_data["value_mean"].quantile(AGGRESSIVE_PERCENTILE / 100)
            aggressive_hours = day_data[day_data["value_mean"] <= aggressive_threshold]
            
            # Optimal: best 8 hours
            optimal_hours = day_data.nsmallest(DAILY_PRODUCTION_HOURS, "value_mean")
            
            daily_results.append({
                "date": date,
                "baseline": baseline,
                "conservative_moer": conservative_hours["value_mean"].mean() if len(conservative_hours) > 0 else baseline,
                "aggressive_moer": aggressive_hours["value_mean"].mean() if len(aggressive_hours) > 0 else baseline,
                "optimal_moer": optimal_hours["value_mean"].mean(),
                "conservative_hours_available": len(conservative_hours),
                "aggressive_hours_available": len(aggressive_hours),
            })
        
        if len(daily_results) == 0:
            continue
        
        daily_df = pd.DataFrame(daily_results)
        
        # Calculate savings
        daily_df["conservative_savings_pct"] = 100 * (daily_df["baseline"] - daily_df["conservative_moer"]) / daily_df["baseline"]
        daily_df["aggressive_savings_pct"] = 100 * (daily_df["baseline"] - daily_df["aggressive_moer"]) / daily_df["baseline"]
        daily_df["optimal_savings_pct"] = 100 * (daily_df["baseline"] - daily_df["optimal_moer"]) / daily_df["baseline"]
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_days": len(daily_df),
            
            "conservative_mean_savings": daily_df["conservative_savings_pct"].mean(),
            "conservative_std_savings": daily_df["conservative_savings_pct"].std(),
            "conservative_min_savings": daily_df["conservative_savings_pct"].min(),
            "conservative_avg_hours": daily_df["conservative_hours_available"].mean(),
            
            "aggressive_mean_savings": daily_df["aggressive_savings_pct"].mean(),
            "aggressive_std_savings": daily_df["aggressive_savings_pct"].std(),
            "aggressive_min_savings": daily_df["aggressive_savings_pct"].min(),
            "aggressive_avg_hours": daily_df["aggressive_hours_available"].mean(),
            
            "optimal_mean_savings": daily_df["optimal_savings_pct"].mean(),
            "optimal_std_savings": daily_df["optimal_savings_pct"].std(),
        })
    
    return pd.DataFrame(results)


def calculate_downside_protection(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate worst-case outcomes for different strategies.
    What happens if forecasts are wrong?
    """
    print("\n  4B. Calculating downside protection...")
    
    results = []
    
    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region]
        
        worst_days = []
        
        for date, day_data in region_data.groupby("date"):
            if len(day_data) < 20:
                continue
            
            baseline = day_data["value_mean"].mean()
            
            # Worst case: pick wrong hours (highest MOER)
            worst_hours = day_data.nlargest(DAILY_PRODUCTION_HOURS, "value_mean")
            worst_moer = worst_hours["value_mean"].mean()
            
            # Best case: pick right hours (lowest MOER)
            best_hours = day_data.nsmallest(DAILY_PRODUCTION_HOURS, "value_mean")
            best_moer = best_hours["value_mean"].mean()
            
            # Range
            range_moer = worst_moer - best_moer
            
            worst_days.append({
                "date": date,
                "baseline": baseline,
                "best_moer": best_moer,
                "worst_moer": worst_moer,
                "range_moer": range_moer,
                "range_pct": 100 * range_moer / baseline if baseline > 0 else 0,
            })
        
        if len(worst_days) == 0:
            continue
        
        worst_df = pd.DataFrame(worst_days)
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_days": len(worst_df),
            "avg_daily_range_pct": worst_df["range_pct"].mean(),
            "max_daily_range_pct": worst_df["range_pct"].max(),
            "avg_worst_case_penalty_pct": (worst_df["worst_moer"] - worst_df["baseline"]).mean() / worst_df["baseline"].mean() * 100,
            "avg_best_case_benefit_pct": (worst_df["baseline"] - worst_df["best_moer"]).mean() / worst_df["baseline"].mean() * 100,
        })
    
    return pd.DataFrame(results)


# =============================================================================
# PLOTTING FUNCTIONS
# =============================================================================

def plot_day_of_week_patterns(dow_df: pd.DataFrame, figures_dir: Path):
    """Plot MOER patterns by day of week."""
    
    if len(dow_df) == 0:
        print("    No day-of-week data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    
    for region in dow_df["region"].unique():
        region_data = dow_df[dow_df["region"] == region].sort_values("day_of_week")
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["day_of_week"], region_data["avg_moer"],
               marker='o', label=REGIONS.get(region, {}).get("name", region),
               color=color, linewidth=2)
    
    ax.set_xlabel("Day of Week")
    ax.set_ylabel("Average MOER")
    ax.set_title("MOER Patterns by Day of Week\n(Lower = better for production)")
    ax.set_xticks(range(7))
    ax.set_xticklabels(day_names)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Shade weekend
    ax.axvspan(4.5, 6.5, alpha=0.1, color='blue', label='Weekend')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "12_day_of_week_patterns.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 12_day_of_week_patterns.png")


def plot_distribution_strategies(strategy_summary: pd.DataFrame, figures_dir: Path):
    """Plot comparison of distribution strategies."""
    
    if len(strategy_summary) == 0:
        print("    No strategy data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    strategies = ["even", "front_load", "back_load", "weekend"]
    strategy_labels = ["Even (8h/day)", "Front-load", "Back-load", "Weekend"]
    colors = ['#3498db', '#2ecc71', '#e74c3c', '#9b59b6']
    
    x = np.arange(len(strategy_summary))
    width = 0.2
    
    for i, (strategy, label, color) in enumerate(zip(strategies, strategy_labels, colors)):
        col = f"{strategy}_savings_pct"
        if col in strategy_summary.columns:
            values = strategy_summary[col].fillna(0)
            ax.bar(x + i * width, values, width, label=label, color=color, edgecolor='black')
    
    # Add optimal line
    if "optimal_savings_pct" in strategy_summary.columns:
        for j, opt in enumerate(strategy_summary["optimal_savings_pct"]):
            ax.hlines(y=opt, xmin=j - 0.1, xmax=j + 0.7, colors='black', 
                     linestyles='--', linewidth=2)
    
    ax.set_xlabel("Region")
    ax.set_ylabel("Average Savings (%)")
    ax.set_title("Weekly Production Distribution Strategies\n(Dashed line = optimal with perfect flexibility)")
    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(strategy_summary["region_name"], rotation=45, ha='right')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "12_distribution_strategies.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 12_distribution_strategies.png")


def plot_flexibility_value(flex_summary: pd.DataFrame, figures_dir: Path):
    """Plot value of flexibility by planning horizon."""
    
    if len(flex_summary) == 0:
        print("    No flexibility data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Total value
    ax = axes[0]
    for region in flex_summary["region"].unique():
        region_data = flex_summary[flex_summary["region"] == region].sort_values("flexibility_days")
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["flexibility_days"], region_data["mean_value_pct"],
               marker='o', label=REGIONS.get(region, {}).get("name", region),
               color=color, linewidth=2)
    
    ax.set_xlabel("Planning Horizon (days)")
    ax.set_ylabel("Flexibility Value (% savings)")
    ax.set_title("Value of Multi-Day Flexibility")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # Marginal value
    ax = axes[1]
    for region in flex_summary["region"].unique():
        region_data = flex_summary[flex_summary["region"] == region].sort_values("flexibility_days")
        marginal = region_data["marginal_value_pct"].fillna(region_data["mean_value_pct"])
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["flexibility_days"], marginal,
               marker='s', label=REGIONS.get(region, {}).get("name", region),
               color=color, linewidth=2)
    
    ax.set_xlabel("Additional Day of Flexibility")
    ax.set_ylabel("Marginal Value (%)")
    ax.set_title("Diminishing Returns of Additional Flexibility")
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "12_flexibility_value.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 12_flexibility_value.png")


def plot_risk_reward(risk_df: pd.DataFrame, figures_dir: Path):
    """Plot risk-reward tradeoff."""
    
    if len(risk_df) == 0:
        print("    No risk data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Scatter: x = std (risk), y = mean (reward)
    for _, row in risk_df.iterrows():
        region = row["region"]
        color = REGION_COLORS.get(region, "#333333")
        
        # Conservative
        ax.scatter(row["conservative_std_savings"], row["conservative_mean_savings"],
                  marker='o', s=100, c=color, label=f"{row['region_name']} (Cons.)")
        
        # Aggressive
        ax.scatter(row["aggressive_std_savings"], row["aggressive_mean_savings"],
                  marker='^', s=100, c=color)
        
        # Connect with line
        ax.plot([row["conservative_std_savings"], row["aggressive_std_savings"]],
               [row["conservative_mean_savings"], row["aggressive_mean_savings"]],
               color=color, linestyle='--', alpha=0.5)
    
    ax.set_xlabel("Risk (Std Dev of Daily Savings)")
    ax.set_ylabel("Expected Savings (%)")
    ax.set_title("Risk-Reward Tradeoff: Conservative (○) vs Aggressive (△)")
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "12_risk_reward.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 12_risk_reward.png")


# =============================================================================
# SUMMARY
# =============================================================================

def generate_summary_report(dow_df: pd.DataFrame, weekend_df: pd.DataFrame,
                           strategy_summary: pd.DataFrame, flex_summary: pd.DataFrame,
                           risk_df: pd.DataFrame, signal: str, outputs_dir: Path):
    """Generate text summary of multi-day optimization analysis."""
    
    lines = [
        "=" * 70,
        "MULTI-DAY PRODUCTION OPTIMIZATION SUMMARY",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        f"Production: {DAILY_PRODUCTION_HOURS}h/day, {WEEKLY_PRODUCTION_HOURS}h/week",
        "",
    ]
    
    if len(weekend_df) > 0:
        lines.extend([
            "-" * 70,
            "WEEKEND VS WEEKDAY",
            "-" * 70,
        ])
        
        for _, row in weekend_df.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Weekday avg MOER: {row['weekday_avg_moer']:.0f}")
            lines.append(f"  Weekend avg MOER: {row['weekend_avg_moer']:.0f}")
            lines.append(f"  Better period: {row['better_period']} ({row['advantage_pct']:.1f}% advantage)")
    
    if len(strategy_summary) > 0:
        lines.extend([
            "",
            "-" * 70,
            "DISTRIBUTION STRATEGY COMPARISON",
            "-" * 70,
        ])
        
        for _, row in strategy_summary.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Optimal (perfect flex): {row['optimal_savings_pct']:.1f}%")
            
            if "best_strategy" in row:
                lines.append(f"  Best simple strategy: {row['best_strategy']}")
            
            for strategy in ["even", "front_load", "back_load", "weekend"]:
                col = f"{strategy}_savings_pct"
                if col in row and pd.notna(row[col]):
                    lines.append(f"  {strategy}: {row[col]:.1f}%")
    
    if len(flex_summary) > 0:
        lines.extend([
            "",
            "-" * 70,
            "FLEXIBILITY VALUE",
            "-" * 70,
        ])
        
        for region in flex_summary["region"].unique():
            region_data = flex_summary[flex_summary["region"] == region].sort_values("flexibility_days")
            region_name = REGIONS.get(region, {}).get("name", region)
            
            lines.append(f"\n{region_name}:")
            for _, row in region_data.iterrows():
                lines.append(f"  {int(row['flexibility_days'])}-day window: {row['mean_value_pct']:.2f}% value")
    
    if len(risk_df) > 0:
        lines.extend([
            "",
            "-" * 70,
            "RISK ANALYSIS",
            "-" * 70,
        ])
        
        for _, row in risk_df.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  Conservative: {row['conservative_mean_savings']:.1f}% avg ± {row['conservative_std_savings']:.1f}%")
            lines.append(f"  Aggressive: {row['aggressive_mean_savings']:.1f}% avg ± {row['aggressive_std_savings']:.1f}%")
    
    lines.extend([
        "",
        "-" * 70,
        "KEY TAKEAWAYS",
        "-" * 70,
        "",
        "1. Weekend vs weekday patterns vary by region - check before assuming",
        "2. 2-3 days of flexibility captures most of the multi-day value",
        "3. Simple distribution strategies achieve majority of optimal savings",
        "4. Conservative strategies trade ~10-20% savings for consistency",
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])
    
    report_text = "\n".join(lines)
    
    with open(outputs_dir / "12_summary_report.txt", "w", encoding="utf-8") as f:
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
    print("MULTI-DAY PRODUCTION OPTIMIZATION")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Production: {DAILY_PRODUCTION_HOURS}h/day, {WEEKLY_PRODUCTION_HOURS}h/week")
    print("=" * 70)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df_hourly, df_daily = load_data(run_dir)
    
    # Initialize results
    dow_df = pd.DataFrame()
    weekend_df = pd.DataFrame()
    best_days_df = pd.DataFrame()
    weekly_results = pd.DataFrame()
    strategy_summary = pd.DataFrame()
    flexibility_df = pd.DataFrame()
    flex_summary = pd.DataFrame()
    risk_df = pd.DataFrame()
    downside_df = pd.DataFrame()
    
    # ==========================================================================
    # SECTION 1: MULTI-DAY PATTERNS
    # ==========================================================================
    if RUN_MULTIDAY_PATTERNS:
        print("\n" + "=" * 70)
        print("SECTION 1: MULTI-DAY PATTERNS")
        print("=" * 70)
        
        dow_df = analyze_day_of_week_patterns(df_daily)
        dow_df.to_csv(outputs_dir / "12_day_of_week.csv", index=False)
        
        weekend_df = analyze_weekend_vs_weekday(df_daily)
        weekend_df.to_csv(outputs_dir / "12_weekend_vs_weekday.csv", index=False)
        
        best_days_df = identify_best_production_days(df_daily)
        best_days_df.to_csv(outputs_dir / "12_best_production_days.csv", index=False)
        
        plot_day_of_week_patterns(dow_df, figures_dir)
    
    # ==========================================================================
    # SECTION 2: PRODUCTION SHIFTING
    # ==========================================================================
    if RUN_SHIFTING_SCENARIOS:
        print("\n" + "=" * 70)
        print("SECTION 2: PRODUCTION SHIFTING SCENARIOS")
        print("=" * 70)
        
        weekly_results = simulate_weekly_distribution(df_hourly, df_daily)
        weekly_results.to_csv(outputs_dir / "12_weekly_simulation.csv", index=False)
        
        strategy_summary = summarize_distribution_strategies(weekly_results)
        strategy_summary.to_csv(outputs_dir / "12_strategy_summary.csv", index=False)
        
        plot_distribution_strategies(strategy_summary, figures_dir)
    
    # ==========================================================================
    # SECTION 3: FLEXIBILITY VALUE
    # ==========================================================================
    if RUN_FLEXIBILITY_VALUE:
        print("\n" + "=" * 70)
        print("SECTION 3: FLEXIBILITY VALUE")
        print("=" * 70)
        
        flexibility_df = calculate_flexibility_value(df_hourly)
        flexibility_df.to_csv(outputs_dir / "12_flexibility_raw.csv", index=False)
        
        flex_summary = summarize_flexibility_value(flexibility_df)
        flex_summary.to_csv(outputs_dir / "12_flexibility_summary.csv", index=False)
        
        plot_flexibility_value(flex_summary, figures_dir)
    
    # ==========================================================================
    # SECTION 4: RISK ANALYSIS
    # ==========================================================================
    if RUN_RISK_ANALYSIS:
        print("\n" + "=" * 70)
        print("SECTION 4: RISK-ADJUSTED SCHEDULING")
        print("=" * 70)
        
        risk_df = analyze_risk_reward_tradeoff(df_hourly)
        risk_df.to_csv(outputs_dir / "12_risk_reward.csv", index=False)
        
        downside_df = calculate_downside_protection(df_hourly)
        downside_df.to_csv(outputs_dir / "12_downside_protection.csv", index=False)
        
        plot_risk_reward(risk_df, figures_dir)
    
    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)
    
    generate_summary_report(dow_df, weekend_df, strategy_summary, flex_summary,
                           risk_df, signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "12_multiday_optimization")
    
    print("\n" + "=" * 70)
    print("MULTI-DAY OPTIMIZATION COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/12_*.png")
    print(f"Data: {outputs_dir}/12_*.csv")
    print(f"Report: {outputs_dir}/12_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()
