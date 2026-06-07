"""
09_shutdown_planning.py - Strategic Shutdown/Maintenance Window Planning

Analyzes optimal timing for planned facility downtime (maintenance, shutdowns)
to maximize avoided emissions. Provides weekly and monthly rankings,
diminishing returns analysis, and holiday alignment assessment.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below
    3. Run: python 09_shutdown_planning.py

Analysis:
    1. Weekly Rankings
       - Rank all 52 weeks by average MOER
       - Year-over-year consistency
       - Best weeks for maintenance (high MOER = good to be offline)
    2. Monthly Rankings
       - Monthly MOER patterns
       - Best months for downtime
    3. Optimal Maintenance Windows
       - If you have N weeks of downtime, which N weeks?
       - Diminishing returns curve
    4. Holiday/Calendar Analysis
       - How do common industrial shutdowns align with grid patterns?
       - Opportunity cost of current practices

Output (in run folder):
    - figures/09_*.png
    - outputs/09_*.csv
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

# Shutdown scenarios to analyze (weeks of annual downtime)
SHUTDOWN_DURATIONS_WEEKS = [1, 2, 3, 4]

# Common US industrial shutdown periods (week numbers, ISO week)
# Week 1 = first week of January, Week 52 = last week of December
COMMON_SHUTDOWNS = {
    "christmas_ny": [52, 1],           # Christmas through New Year
    "july_4th": [27],                   # July 4th week
    "thanksgiving": [47],               # Thanksgiving week
    "memorial_day": [22],               # Memorial Day week
    "labor_day": [36],                  # Labor Day week
}

# Analysis toggles
RUN_WEEKLY_RANKINGS = True
RUN_MONTHLY_RANKINGS = True
RUN_OPTIMAL_WINDOWS = True
RUN_HOLIDAY_ANALYSIS = True
RUN_PRODUCTION_OPTIMIZATION = True

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


def load_data(run_dir: Path) -> pd.DataFrame:
    """Load processed hourly data."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")

    df_hourly["point_time"] = pd.to_datetime(df_hourly[["year", "month", "day", "hour"]].assign(minute=0, second=0))
    
    print(f"  Hourly: {len(df_hourly):,} records")
    print(df_hourly.columns.tolist())
    # Add ISO week number
    df_hourly["week"] = df_hourly["point_time"].dt.isocalendar().week.astype(int)
    df_hourly["year_week"] = df_hourly["year"].astype(str) + "-W" + df_hourly["week"].astype(str).str.zfill(2)
    
    
    print(df_hourly.columns.tolist())
    print(df_hourly.head())

    return df_hourly


# =============================================================================
# SECTION 1: WEEKLY RANKINGS
# =============================================================================

def calculate_weekly_rankings(df_hourly: pd.DataFrame, signal: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rank all 52 weeks by average MOER.
    Higher MOER weeks = better for maintenance (avoid running during dirty grid).
    """
    print("\n  1A. Calculating weekly rankings...")
    
    # Calculate weekly averages per region and year
    weekly = df_hourly.groupby(["region", "year", "week"]).agg({
        "value_mean": ["mean", "std", "min", "max"],
        "point_time": "count"
    }).reset_index()
    weekly.columns = ["region", "year", "week", "moer_mean", "moer_std", "moer_min", "moer_max", "n_hours"]
    
    # Filter out partial weeks (less than 100 hours)
    weekly = weekly[weekly["n_hours"] >= 100]
    
    # Calculate overall weekly rankings (averaged across years)
    overall = weekly.groupby(["region", "week"]).agg({
        "moer_mean": ["mean", "std"],
        "n_hours": "sum"
    }).reset_index()
    overall.columns = ["region", "week", "avg_moer", "moer_variability", "total_hours"]
    
    # Rank weeks within each region (1 = highest MOER = best for maintenance)
    overall["rank_for_maintenance"] = overall.groupby("region")["avg_moer"].rank(ascending=False).astype(int)
    overall["rank_for_production"] = overall.groupby("region")["avg_moer"].rank(ascending=True).astype(int)
    
    # Add consistency score (how stable is this week's ranking across years?)
    consistency_scores = []
    for region in weekly["region"].unique():
        region_weekly = weekly[weekly["region"] == region]
        
        for week in range(1, 53):
            week_data = region_weekly[region_weekly["week"] == week]
            
            if len(week_data) < 2:
                consistency_scores.append({
                    "region": region,
                    "week": week,
                    "consistency": np.nan,
                    "n_years": len(week_data)
                })
                continue
            
            # Calculate coefficient of variation
            cv = week_data["moer_mean"].std() / week_data["moer_mean"].mean() if week_data["moer_mean"].mean() > 0 else 1
            consistency = max(0, 1 - cv)  # Higher = more consistent
            
            consistency_scores.append({
                "region": region,
                "week": week,
                "consistency": consistency,
                "n_years": len(week_data)
            })
    
    consistency_df = pd.DataFrame(consistency_scores)
    overall = overall.merge(consistency_df, on=["region", "week"], how="left")
    
    # Add region names
    overall["region_name"] = overall["region"].map(lambda r: REGIONS.get(r, {}).get("name", r))
    weekly["region_name"] = weekly["region"].map(lambda r: REGIONS.get(r, {}).get("name", r))
    
    print(f"    Analyzed {len(overall)} region-weeks")
    
    return overall, weekly


def identify_best_maintenance_weeks(weekly_rankings: pd.DataFrame, n_weeks: int) -> pd.DataFrame:
    """Identify the best N weeks for maintenance per region."""
    print(f"\n  1B. Identifying best {n_weeks} weeks for maintenance...")
    
    results = []
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        
        # Top N weeks by MOER (best for maintenance)
        best_weeks = region_data.nsmallest(n_weeks, "rank_for_maintenance")
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_weeks": n_weeks,
            "best_weeks": list(best_weeks["week"]),
            "avg_moer_during_shutdown": best_weeks["avg_moer"].mean(),
            "region_avg_moer": region_data["avg_moer"].mean(),
            "emissions_avoided_pct": 100 * (best_weeks["avg_moer"].mean() - region_data["avg_moer"].mean()) / region_data["avg_moer"].mean()
        })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 2: MONTHLY RANKINGS
# =============================================================================

def calculate_monthly_rankings(df_hourly: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Rank months by average MOER."""
    print("\n  2A. Calculating monthly rankings...")
    
    monthly = df_hourly.groupby(["region", "year", "month"]).agg({
        "value_mean": ["mean", "std"]
    }).reset_index()
    monthly.columns = ["region", "year", "month", "moer_mean", "moer_std"]
    
    # Overall monthly rankings
    overall = monthly.groupby(["region", "month"]).agg({
        "moer_mean": ["mean", "std"]
    }).reset_index()
    overall.columns = ["region", "month", "avg_moer", "moer_variability"]
    
    # Rank months
    overall["rank_for_maintenance"] = overall.groupby("region")["avg_moer"].rank(ascending=False).astype(int)
    overall["rank_for_production"] = overall.groupby("region")["avg_moer"].rank(ascending=True).astype(int)
    
    # Add month names
    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    overall["month_name"] = overall["month"].map(lambda m: month_names[m-1])
    overall["region_name"] = overall["region"].map(lambda r: REGIONS.get(r, {}).get("name", r))
    
    return overall


# =============================================================================
# SECTION 3: OPTIMAL MAINTENANCE WINDOWS
# =============================================================================

def calculate_diminishing_returns(weekly_rankings: pd.DataFrame, max_weeks: int = 8) -> pd.DataFrame:
    """
    Calculate diminishing returns curve for maintenance scheduling.
    Shows how much additional value each extra week of downtime provides.
    """
    print("\n  3A. Calculating diminishing returns...")
    
    results = []
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region].sort_values("rank_for_maintenance")
        region_avg = region_data["avg_moer"].mean()
        
        cumulative_value = 0
        
        for n in range(1, min(max_weeks + 1, len(region_data) + 1)):
            top_n = region_data.head(n)
            shutdown_moer = top_n["avg_moer"].mean()
            
            # Value = how much higher than average MOER during shutdown
            # (higher = more emissions avoided by being offline)
            total_value = (shutdown_moer - region_avg) * n
            marginal_value = total_value - cumulative_value if n > 1 else total_value
            
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "n_weeks": n,
                "weeks_selected": list(top_n["week"]),
                "avg_shutdown_moer": shutdown_moer,
                "region_avg_moer": region_avg,
                "moer_above_avg": shutdown_moer - region_avg,
                "pct_above_avg": 100 * (shutdown_moer - region_avg) / region_avg,
                "cumulative_value": total_value,
                "marginal_value": marginal_value,
            })
            
            cumulative_value = total_value
    
    return pd.DataFrame(results)


def analyze_consecutive_vs_spread(weekly_rankings: pd.DataFrame, n_weeks: int = 2) -> pd.DataFrame:
    """
    Compare consecutive weeks vs spread-out maintenance.
    """
    print(f"\n  3B. Analyzing consecutive vs spread maintenance ({n_weeks} weeks)...")
    
    results = []
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        region_avg = region_data["avg_moer"].mean()
        
        # Best N consecutive weeks
        best_consecutive = None
        best_consecutive_moer = -np.inf
        
        for start_week in range(1, 53 - n_weeks + 1):
            weeks = list(range(start_week, start_week + n_weeks))
            week_data = region_data[region_data["week"].isin(weeks)]
            
            if len(week_data) == n_weeks:
                avg_moer = week_data["avg_moer"].mean()
                if avg_moer > best_consecutive_moer:
                    best_consecutive_moer = avg_moer
                    best_consecutive = weeks
        
        # Best N weeks overall (possibly spread)
        best_spread = region_data.nlargest(n_weeks, "avg_moer")
        best_spread_weeks = list(best_spread["week"].sort_values())
        best_spread_moer = best_spread["avg_moer"].mean()
        
        # Calculate gap
        moer_gap = best_spread_moer - best_consecutive_moer if best_consecutive else 0
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_weeks": n_weeks,
            "best_consecutive_weeks": best_consecutive,
            "best_consecutive_moer": best_consecutive_moer,
            "best_spread_weeks": best_spread_weeks,
            "best_spread_moer": best_spread_moer,
            "spread_advantage_moer": moer_gap,
            "spread_advantage_pct": 100 * moer_gap / region_avg if region_avg > 0 else 0,
            "recommendation": "spread" if moer_gap > 0.01 * region_avg else "either"
        })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 4: HOLIDAY ANALYSIS
# =============================================================================

def analyze_holiday_alignment(weekly_rankings: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze how common industrial shutdown periods align with optimal timing.
    """
    print("\n  4A. Analyzing holiday alignment...")
    
    results = []
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        region_avg = region_data["avg_moer"].mean()
        
        for holiday_name, holiday_weeks in COMMON_SHUTDOWNS.items():
            holiday_data = region_data[region_data["week"].isin(holiday_weeks)]
            
            if len(holiday_data) == 0:
                continue
            
            holiday_moer = holiday_data["avg_moer"].mean()
            
            # Find the best alternative weeks (same count as holiday)
            n_weeks = len(holiday_weeks)
            best_alternative = region_data.nlargest(n_weeks, "avg_moer")
            best_alt_moer = best_alternative["avg_moer"].mean()
            
            # Calculate opportunity cost
            opportunity_cost = best_alt_moer - holiday_moer
            
            # Get ranks of holiday weeks
            holiday_ranks = holiday_data["rank_for_maintenance"].values
            
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "holiday": holiday_name,
                "holiday_weeks": holiday_weeks,
                "holiday_moer": holiday_moer,
                "region_avg_moer": region_avg,
                "holiday_vs_avg_pct": 100 * (holiday_moer - region_avg) / region_avg,
                "best_alternative_moer": best_alt_moer,
                "best_alternative_weeks": list(best_alternative["week"]),
                "opportunity_cost_moer": opportunity_cost,
                "opportunity_cost_pct": 100 * opportunity_cost / region_avg,
                "holiday_rank_avg": np.mean(holiday_ranks),
                "is_good_timing": holiday_moer > region_avg,
            })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 5: PRODUCTION OPTIMIZATION
# =============================================================================

def identify_best_production_weeks(weekly_rankings: pd.DataFrame, n_weeks: int = 4) -> pd.DataFrame:
    """
    Identify the best weeks for heavy production (lowest MOER).
    """
    print(f"\n  5A. Identifying best {n_weeks} weeks for production...")
    
    results = []
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        
        # Top N weeks by lowest MOER (best for production)
        best_weeks = region_data.nsmallest(n_weeks, "rank_for_production")
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "n_weeks": n_weeks,
            "best_production_weeks": list(best_weeks["week"]),
            "avg_moer_during_production": best_weeks["avg_moer"].mean(),
            "region_avg_moer": region_data["avg_moer"].mean(),
            "emissions_reduction_pct": 100 * (region_data["avg_moer"].mean() - best_weeks["avg_moer"].mean()) / region_data["avg_moer"].mean()
        })
    
    return pd.DataFrame(results)


# =============================================================================
# PLOTTING FUNCTIONS
# =============================================================================

def plot_weekly_heatmap(weekly_rankings: pd.DataFrame, figures_dir: Path):
    """Plot 52-week heatmap of MOER by region."""
    
    if len(weekly_rankings) == 0:
        print("    No weekly data to plot")
        return
    
    regions = weekly_rankings["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(n_regions, 1, figsize=(16, 3 * n_regions), squeeze=False)
    
    for i, region in enumerate(regions):
        ax = axes[i, 0]
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        
        # Create pivot (week as x-axis)
        pivot = region_data.pivot_table(index="region", columns="week", values="avg_moer")
        
        # Ensure all 52 weeks
        for w in range(1, 53):
            if w not in pivot.columns:
                pivot[w] = np.nan
        pivot = pivot[sorted(pivot.columns)]
        
        sns.heatmap(pivot, ax=ax, cmap="RdYlGn_r", cbar_kws={"label": "MOER"},
                   xticklabels=4, yticklabels=False)
        
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}", fontsize=11)
        ax.set_xlabel("Week of Year")
        ax.set_ylabel("")
        
        # Mark common holidays
        for holiday, weeks in COMMON_SHUTDOWNS.items():
            for w in weeks:
                ax.axvline(x=w - 0.5, color='blue', linestyle='--', alpha=0.5, linewidth=1)
    
    plt.suptitle("Weekly MOER Patterns\n(Higher = better for maintenance, blue lines = common shutdown weeks)", 
                 fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "09_weekly_heatmap.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 09_weekly_heatmap.png")


def plot_diminishing_returns(returns_df: pd.DataFrame, figures_dir: Path):
    """Plot diminishing returns curve."""
    
    if len(returns_df) == 0:
        print("    No returns data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Cumulative value
    ax = axes[0]
    for region in returns_df["region"].unique():
        region_data = returns_df[returns_df["region"] == region]
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["n_weeks"], region_data["pct_above_avg"], 
                marker='o', label=REGIONS.get(region, {}).get("name", region),
                color=color, linewidth=2)
    
    ax.set_xlabel("Weeks of Maintenance")
    ax.set_ylabel("Avg MOER During Shutdown (% above baseline)")
    ax.set_title("Shutdown Timing Value\n(Higher = more emissions avoided by being offline)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(range(1, returns_df["n_weeks"].max() + 1))
    
    # Marginal value
    ax = axes[1]
    for region in returns_df["region"].unique():
        region_data = returns_df[returns_df["region"] == region]
        color = REGION_COLORS.get(region, "#333333")
        ax.bar(region_data["n_weeks"] + (list(returns_df["region"].unique()).index(region) - 1) * 0.15,
               region_data["marginal_value"], width=0.15, 
               label=REGIONS.get(region, {}).get("name", region) if region_data["n_weeks"].iloc[0] == 1 else "",
               color=color, edgecolor='black', alpha=0.7)
    
    ax.set_xlabel("Week Number of Maintenance")
    ax.set_ylabel("Marginal Value (MOER × weeks)")
    ax.set_title("Diminishing Returns of Additional Maintenance Weeks")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_xticks(range(1, returns_df["n_weeks"].max() + 1))
    
    plt.tight_layout()
    plt.savefig(figures_dir / "09_diminishing_returns.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 09_diminishing_returns.png")


def plot_holiday_analysis(holiday_df: pd.DataFrame, figures_dir: Path):
    """Plot holiday alignment analysis."""
    
    if len(holiday_df) == 0:
        print("    No holiday data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Holiday vs average MOER
    ax = axes[0]
    
    holidays = holiday_df["holiday"].unique()
    regions = holiday_df["region"].unique()
    x = np.arange(len(holidays))
    width = 0.8 / len(regions)
    
    for i, region in enumerate(regions):
        region_data = holiday_df[holiday_df["region"] == region]
        region_data = region_data.set_index("holiday").reindex(holidays)
        color = REGION_COLORS.get(region, "#333333")
        
        bars = ax.bar(x + i * width, region_data["holiday_vs_avg_pct"], width,
                     label=REGIONS.get(region, {}).get("name", region),
                     color=color, edgecolor='black', alpha=0.7)
    
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel("Holiday Period")
    ax.set_ylabel("MOER vs Annual Average (%)")
    ax.set_title("Holiday Shutdown Timing Quality\n(Positive = good timing, grid is dirty)")
    ax.set_xticks(x + width * (len(regions) - 1) / 2)
    ax.set_xticklabels([h.replace("_", " ").title() for h in holidays], rotation=45, ha='right')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Opportunity cost
    ax = axes[1]
    
    for i, region in enumerate(regions):
        region_data = holiday_df[holiday_df["region"] == region]
        region_data = region_data.set_index("holiday").reindex(holidays)
        color = REGION_COLORS.get(region, "#333333")
        
        bars = ax.bar(x + i * width, region_data["opportunity_cost_pct"], width,
                     label=REGIONS.get(region, {}).get("name", region),
                     color=color, edgecolor='black', alpha=0.7)
    
    ax.set_xlabel("Holiday Period")
    ax.set_ylabel("Opportunity Cost (% of avg MOER)")
    ax.set_title("Opportunity Cost of Holiday Shutdowns\n(vs optimal timing)")
    ax.set_xticks(x + width * (len(regions) - 1) / 2)
    ax.set_xticklabels([h.replace("_", " ").title() for h in holidays], rotation=45, ha='right')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "09_holiday_analysis.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 09_holiday_analysis.png")


def plot_monthly_rankings(monthly_df: pd.DataFrame, figures_dir: Path):
    """Plot monthly MOER patterns."""
    
    if len(monthly_df) == 0:
        print("    No monthly data to plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for region in monthly_df["region"].unique():
        region_data = monthly_df[monthly_df["region"] == region].sort_values("month")
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["month"], region_data["avg_moer"], 
                marker='o', label=REGIONS.get(region, {}).get("name", region),
                color=color, linewidth=2)
    
    ax.set_xlabel("Month")
    ax.set_ylabel("Average MOER")
    ax.set_title("Monthly MOER Patterns\n(Higher months = better for maintenance)")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(month_names)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "09_monthly_rankings.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 09_monthly_rankings.png")


def plot_recommendations_summary(weekly_rankings: pd.DataFrame, figures_dir: Path):
    """Create summary visualization of maintenance recommendations."""
    
    if len(weekly_rankings) == 0:
        print("    No data for recommendations summary")
        return
    
    regions = weekly_rankings["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(1, n_regions, figsize=(4 * n_regions, 6), squeeze=False)
    
    for i, region in enumerate(regions):
        ax = axes[0, i]
        region_data = weekly_rankings[weekly_rankings["region"] == region].sort_values("week")
        
        # Color code by quintile
        region_data["quintile"] = pd.qcut(region_data["avg_moer"], 5, labels=False)
        colors = ['#2ecc71', '#a8e6cf', '#ffffba', '#ffb3ba', '#ff6b6b']  # Green to red
        
        bars = ax.bar(region_data["week"], region_data["avg_moer"],
                     color=[colors[q] for q in region_data["quintile"]])
        
        # Mark best 4 weeks for maintenance
        best_4 = region_data.nlargest(4, "avg_moer")
        for _, row in best_4.iterrows():
            ax.annotate("★", xy=(row["week"], row["avg_moer"]), 
                       ha='center', va='bottom', fontsize=12, color='darkgreen')
        
        ax.set_xlabel("Week of Year")
        ax.set_ylabel("Average MOER")
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}\n★ = Best maintenance weeks")
        ax.set_xlim(0, 53)
        
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#ff6b6b', label='Highest MOER (best for maintenance)'),
        Patch(facecolor='#2ecc71', label='Lowest MOER (best for production)')
    ]
    fig.legend(handles=legend_elements, loc='lower center', ncol=2, bbox_to_anchor=(0.5, -0.02))
    
    plt.suptitle("Weekly MOER Rankings: Maintenance vs Production Timing", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "09_recommendations_summary.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 09_recommendations_summary.png")


# =============================================================================
# SUMMARY
# =============================================================================

def generate_summary_report(weekly_rankings: pd.DataFrame, monthly_rankings: pd.DataFrame,
                           returns_df: pd.DataFrame, holiday_df: pd.DataFrame,
                           signal: str, outputs_dir: Path):
    """Generate text summary of shutdown planning analysis."""
    
    lines = [
        "=" * 70,
        "SHUTDOWN PLANNING ANALYSIS SUMMARY",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        "",
    ]
    
    lines.extend([
        "-" * 70,
        "BEST WEEKS FOR MAINTENANCE (by region)",
        "-" * 70,
    ])
    
    for region in weekly_rankings["region"].unique():
        region_data = weekly_rankings[weekly_rankings["region"] == region]
        best_4 = region_data.nlargest(4, "avg_moer")
        
        lines.append(f"\n{REGIONS.get(region, {}).get('name', region)}:")
        lines.append(f"  Best 4 weeks: {list(best_4['week'])}")
        lines.append(f"  Avg MOER during best weeks: {best_4['avg_moer'].mean():.0f}")
        lines.append(f"  Region avg MOER: {region_data['avg_moer'].mean():.0f}")
        lines.append(f"  Premium: {100 * (best_4['avg_moer'].mean() / region_data['avg_moer'].mean() - 1):.1f}% above average")
    
    if len(monthly_rankings) > 0:
        lines.extend([
            "",
            "-" * 70,
            "BEST MONTHS FOR MAINTENANCE",
            "-" * 70,
        ])
        
        for region in monthly_rankings["region"].unique():
            region_data = monthly_rankings[monthly_rankings["region"] == region]
            best_month = region_data.loc[region_data["avg_moer"].idxmax()]
            worst_month = region_data.loc[region_data["avg_moer"].idxmin()]
            
            lines.append(f"\n{REGIONS.get(region, {}).get('name', region)}:")
            lines.append(f"  Best month for maintenance: {best_month['month_name']}")
            lines.append(f"  Best month for production: {worst_month['month_name']}")
    
    if len(holiday_df) > 0:
        lines.extend([
            "",
            "-" * 70,
            "HOLIDAY SHUTDOWN ASSESSMENT",
            "-" * 70,
        ])
        
        for holiday in holiday_df["holiday"].unique():
            holiday_data = holiday_df[holiday_df["holiday"] == holiday]
            avg_quality = holiday_data["holiday_vs_avg_pct"].mean()
            
            assessment = "good" if avg_quality > 0 else "suboptimal"
            lines.append(f"\n{holiday.replace('_', ' ').title()}:")
            lines.append(f"  Assessment: {assessment}")
            lines.append(f"  Avg MOER vs baseline: {avg_quality:+.1f}%")
    
    if len(returns_df) > 0:
        lines.extend([
            "",
            "-" * 70,
            "DIMINISHING RETURNS",
            "-" * 70,
        ])
        
        # Get 4-week data
        four_week = returns_df[returns_df["n_weeks"] == 4]
        if len(four_week) > 0:
            lines.append("\n4 weeks of maintenance:")
            for _, row in four_week.iterrows():
                lines.append(f"  {row['region_name']}: {row['pct_above_avg']:.1f}% above avg MOER")
    
    lines.extend([
        "",
        "-" * 70,
        "KEY RECOMMENDATIONS",
        "-" * 70,
        "",
        "1. Schedule maintenance during high-MOER weeks (typically summer peaks)",
        "2. Consider spreading maintenance vs consecutive weeks for maximum value",
        "3. Holiday shutdowns may not align with optimal grid timing",
        "4. Diminishing returns after 3-4 weeks of strategic scheduling",
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])
    
    report_text = "\n".join(lines)
    
    with open(outputs_dir / "09_summary_report.txt", "w", encoding="utf-8") as f:
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
    print("SHUTDOWN PLANNING ANALYSIS")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print("=" * 70)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df_hourly = load_data(run_dir)
    
    # Initialize results
    weekly_rankings = pd.DataFrame()
    weekly_detailed = pd.DataFrame()
    monthly_rankings = pd.DataFrame()
    returns_df = pd.DataFrame()
    consecutive_df = pd.DataFrame()
    holiday_df = pd.DataFrame()
    production_df = pd.DataFrame()
    
    # ==========================================================================
    # SECTION 1: WEEKLY RANKINGS
    # ==========================================================================
    if RUN_WEEKLY_RANKINGS:
        print("\n" + "=" * 70)
        print("SECTION 1: WEEKLY RANKINGS")
        print("=" * 70)
        
        weekly_rankings, weekly_detailed = calculate_weekly_rankings(df_hourly, signal)
        weekly_rankings.to_csv(outputs_dir / "09_weekly_rankings.csv", index=False)
        weekly_detailed.to_csv(outputs_dir / "09_weekly_detailed.csv", index=False)
        
        # Best maintenance weeks
        for n in SHUTDOWN_DURATIONS_WEEKS:
            best_weeks = identify_best_maintenance_weeks(weekly_rankings, n)
            best_weeks.to_csv(outputs_dir / f"09_best_{n}week_maintenance.csv", index=False)
        
        plot_weekly_heatmap(weekly_rankings, figures_dir)
        plot_recommendations_summary(weekly_rankings, figures_dir)
    
    # ==========================================================================
    # SECTION 2: MONTHLY RANKINGS
    # ==========================================================================
    if RUN_MONTHLY_RANKINGS:
        print("\n" + "=" * 70)
        print("SECTION 2: MONTHLY RANKINGS")
        print("=" * 70)
        
        monthly_rankings = calculate_monthly_rankings(df_hourly, signal)
        monthly_rankings.to_csv(outputs_dir / "09_monthly_rankings.csv", index=False)
        
        plot_monthly_rankings(monthly_rankings, figures_dir)
    
    # ==========================================================================
    # SECTION 3: OPTIMAL WINDOWS
    # ==========================================================================
    if RUN_OPTIMAL_WINDOWS and len(weekly_rankings) > 0:
        print("\n" + "=" * 70)
        print("SECTION 3: OPTIMAL MAINTENANCE WINDOWS")
        print("=" * 70)
        
        returns_df = calculate_diminishing_returns(weekly_rankings)
        returns_df.to_csv(outputs_dir / "09_diminishing_returns.csv", index=False)
        
        consecutive_df = analyze_consecutive_vs_spread(weekly_rankings)
        consecutive_df.to_csv(outputs_dir / "09_consecutive_vs_spread.csv", index=False)
        
        plot_diminishing_returns(returns_df, figures_dir)
    
    # ==========================================================================
    # SECTION 4: HOLIDAY ANALYSIS
    # ==========================================================================
    if RUN_HOLIDAY_ANALYSIS and len(weekly_rankings) > 0:
        print("\n" + "=" * 70)
        print("SECTION 4: HOLIDAY ALIGNMENT")
        print("=" * 70)
        
        holiday_df = analyze_holiday_alignment(weekly_rankings)
        holiday_df.to_csv(outputs_dir / "09_holiday_analysis.csv", index=False)
        
        plot_holiday_analysis(holiday_df, figures_dir)
    
    # ==========================================================================
    # SECTION 5: PRODUCTION OPTIMIZATION
    # ==========================================================================
    if RUN_PRODUCTION_OPTIMIZATION and len(weekly_rankings) > 0:
        print("\n" + "=" * 70)
        print("SECTION 5: PRODUCTION OPTIMIZATION")
        print("=" * 70)
        
        production_df = identify_best_production_weeks(weekly_rankings)
        production_df.to_csv(outputs_dir / "09_best_production_weeks.csv", index=False)
    
    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)
    
    generate_summary_report(weekly_rankings, monthly_rankings, returns_df, holiday_df,
                           signal, outputs_dir)
    
    # Mark script as run
    mark_script_run(run_dir, "09_shutdown_planning")
    
    print("\n" + "=" * 70)
    print("SHUTDOWN PLANNING ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/09_*.png")
    print(f"Data: {outputs_dir}/09_*.csv")
    print(f"Report: {outputs_dir}/09_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()
