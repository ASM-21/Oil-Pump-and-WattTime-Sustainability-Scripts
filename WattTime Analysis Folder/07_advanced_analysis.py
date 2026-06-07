"""
07_advanced_analysis.py - Advanced Heuristic Analysis

Comprehensive analysis to validate, stress-test, and extend scheduling heuristics.
Includes robustness checks, operational constraints, grid behavior analysis,
and forecast value quantification.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below
    3. Run: python 07_advanced_analysis.py

Sections (auto-enabled based on data availability):
    1. Robustness Analysis
       - Year-over-year stability
       - Threshold vs time-based rules
       - Holdout validation
    2. Operation Constraints
       - Duration sensitivity
       - Deadline scheduling
       - Shift-constrained windows
    3. Grid Behavior
       - Volatility analysis
       - Regime clustering
       - MISO investigation (if applicable)
    4. Forecast Value (requires forecast data)
       - Achieved vs theoretical savings

Output (in run folder):
    - figures/07_*.png
    - outputs/07_*.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import json
import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import warnings
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, SHIFTS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS, SEASON_COLORS,
    get_signal_metadata, get_unit_label
)

warnings.filterwarnings('ignore', category=FutureWarning)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run folder to analyze (created by 02_data_processing.py)
# Use the folder name from runs/, e.g., "2025-01-28_moer_temporal"
# Or set to None to use the most recent run
RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"

# Which sections to run
RUN_ROBUSTNESS = True
RUN_CONSTRAINTS = True
RUN_GRID_BEHAVIOR = True
RUN_FORECAST_VALUE = True  # Auto-disabled if no forecast data

# Section 1: Robustness parameters
STABILITY_MIN_YEARS = 2  # Minimum years needed for stability analysis
HOLDOUT_TRAIN_YEARS = [2022, 2023]  # Years for training
HOLDOUT_TEST_YEARS = [2024]  # Years for testing
THRESHOLD_PERCENTILES = [10, 25, 50]  # Percentiles for threshold rules

# Section 2: Constraint parameters
OPERATION_DURATIONS = [0.5, 1, 2, 4, 8]  # Hours
DEADLINES = [12, 14, 16, 18, 20, 22]  # Must finish by this hour
SHIFT_DEFINITIONS = {
    "first": (6, 14),
    "second": (14, 22),
    "third": (22, 6),  # Wraps midnight
}

# Section 3: Grid behavior parameters
N_REGIMES = 4  # Number of clusters for regime analysis
VOLATILITY_WINDOW_MINUTES = 60  # Rolling window for volatility

# Section 4: Forecast parameters
FORECAST_MAX_DAYS_PER_REGION = 100  # Limit days analyzed per region for speed

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


def load_data(run_dir: Path) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load processed data files from run folder."""
    print("Loading processed data...")

    processed_dir = run_dir / "processed"

    df_5min = pd.read_parquet(processed_dir / "data_5min.parquet")
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")
    df_daily = pd.read_parquet(processed_dir / "daily_statistics.parquet")

    print(f"  5-min: {len(df_5min):,} records ({df_5min.memory_usage(deep=True).sum() / 1e6:.0f} MB)")
    print(f"  Hourly: {len(df_hourly):,} records ({df_hourly.memory_usage(deep=True).sum() / 1e6:.0f} MB)")
    print(f"  Daily: {len(df_daily):,} records ({df_daily.memory_usage(deep=True).sum() / 1e6:.0f} MB)")

    return df_5min, df_hourly, df_daily


def load_forecast_data(run_dir: Path) -> Optional[pd.DataFrame]:
    """Load forecast data if available. Only loads columns we need to save memory."""
    forecast_path = run_dir / "processed" / "data_forecast.parquet"
    if not forecast_path.exists():
        return None

    # Only load the columns we actually need
    needed_cols = ["point_time", "generated_at", "region", "value"]
    try:
        available_cols = pd.read_parquet(forecast_path, columns=[]).columns.tolist()
        cols_to_load = [c for c in needed_cols if c in available_cols]
        df = pd.read_parquet(forecast_path, columns=cols_to_load)
    except Exception:
        df = pd.read_parquet(forecast_path)

    mem_mb = df.memory_usage(deep=True).sum() / 1e6
    print(f"  Forecast: {len(df):,} records ({mem_mb:.0f} MB)")
    return df


def check_data_requirements(df_5min: pd.DataFrame) -> Dict:
    """Check what analyses can run based on available data."""
    years = sorted(df_5min["year"].unique())
    regions = sorted(df_5min["region"].unique())

    requirements = {
        "years": years,
        "n_years": len(years),
        "regions": regions,
        "n_regions": len(regions),
        "can_stability": len(years) >= STABILITY_MIN_YEARS,
        "can_holdout": (
            all(y in years for y in HOLDOUT_TRAIN_YEARS) and
            all(y in years for y in HOLDOUT_TEST_YEARS)
        ),
        "has_miso": any("MISO" in r for r in regions),
    }

    return requirements


# =============================================================================
# SECTION 1: ROBUSTNESS ANALYSIS
# =============================================================================

def analyze_year_over_year_stability(df_hourly: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Analyze if best hours are stable across years.

    For each region/season, find the best hour per year and measure consistency.
    Stability score = 1 - (std of best hours / 12)
    """
    print("\n  1A. Year-over-year stability...")

    results = []

    for region in df_hourly["region"].unique():
        for season in ["winter", "spring", "summer", "fall"]:
            subset = df_hourly[
                (df_hourly["region"] == region) &
                (df_hourly["season"] == season)
            ]

            if len(subset) == 0:
                continue

            # Find best hour per year
            best_hours = []
            year_data = {}

            for year in sorted(subset["year"].unique()):
                year_subset = subset[subset["year"] == year]
                hourly_mean = year_subset.groupby("hour")["value_mean"].mean()

                if len(hourly_mean) < 20:  # Need most hours represented
                    continue

                best_hour = hourly_mean.idxmin()
                best_hours.append(best_hour)
                year_data[year] = {
                    "best_hour": int(best_hour),
                    "best_value": float(hourly_mean[best_hour]),
                    "worst_hour": int(hourly_mean.idxmax()),
                    "worst_value": float(hourly_mean.max()),
                }

            if len(best_hours) < 2:
                continue

            # Calculate stability using circular statistics (23 and 0 are close)
            best_hours_array = np.array(best_hours)
            angles = best_hours_array * (2 * np.pi / 24)
            mean_sin = np.mean(np.sin(angles))
            mean_cos = np.mean(np.cos(angles))
            circular_mean = np.arctan2(mean_sin, mean_cos)
            if circular_mean < 0:
                circular_mean += 2 * np.pi
            mean_hour = circular_mean * 24 / (2 * np.pi)

            # Circular standard deviation approximation
            R = np.sqrt(mean_sin**2 + mean_cos**2)
            circular_std = np.sqrt(-2 * np.log(max(R, 1e-10))) * 24 / (2 * np.pi)

            stability_score = max(0, 1 - (circular_std / 12))

            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "season": season,
                "n_years": len(best_hours),
                "best_hours_by_year": year_data,
                "mean_best_hour": mean_hour,
                "std_best_hour": circular_std,
                "stability_score": stability_score,
                "is_stable": stability_score >= 0.7,
                "best_hour_range": max(best_hours) - min(best_hours),
            })

    return pd.DataFrame(results)


def analyze_threshold_vs_time_rules(df_5min: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Compare time-based rules ("run at 2pm") vs threshold rules ("run when MOER < P25").

    For each region/season:
    1. Time-based: schedule at the historically best hour
    2. Threshold: schedule when value drops below Pxx percentile
    3. Compare total emissions under each strategy
    """
    print("\n  1B. Threshold vs time-based rules...")

    results = []

    for region in df_5min["region"].unique():
        region_data = df_5min[df_5min["region"] == region]

        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]

            if len(season_data) < 1000:
                continue

            # Find best hour (time-based rule)
            hourly_mean = season_data.groupby("hour")["value"].mean()
            best_hour = hourly_mean.idxmin()

            # Baseline: random scheduling (daily mean)
            daily_means = season_data.groupby("date")["value"].mean()
            baseline_emissions = daily_means.mean()

            # Time-based strategy: always schedule at best hour
            best_hour_data = season_data[season_data["hour"] == best_hour]
            time_based_emissions = best_hour_data.groupby("date")["value"].mean().mean()

            for percentile in THRESHOLD_PERCENTILES:
                # Threshold strategy
                threshold = season_data["value"].quantile(percentile / 100)

                threshold_emissions_list = []
                for date in season_data["date"].unique():
                    day_data = season_data[season_data["date"] == date]
                    below_threshold = day_data[day_data["value"] < threshold]

                    if len(below_threshold) > 0:
                        threshold_emissions_list.append(below_threshold["value"].min())
                    else:
                        threshold_emissions_list.append(day_data["value"].min())

                threshold_emissions = np.mean(threshold_emissions_list)

                # Calculate savings
                if baseline_emissions > 0:
                    time_savings_pct = 100 * (baseline_emissions - time_based_emissions) / baseline_emissions
                    threshold_savings_pct = 100 * (baseline_emissions - threshold_emissions) / baseline_emissions
                else:
                    time_savings_pct = 0.0
                    threshold_savings_pct = 0.0

                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "threshold_percentile": percentile,
                    "threshold_value": threshold,
                    "best_hour": best_hour,
                    "baseline_emissions": baseline_emissions,
                    "time_based_emissions": time_based_emissions,
                    "threshold_emissions": threshold_emissions,
                    "time_savings_pct": time_savings_pct,
                    "threshold_savings_pct": threshold_savings_pct,
                    "threshold_advantage_pct": threshold_savings_pct - time_savings_pct,
                    "winner": "threshold" if threshold_savings_pct > time_savings_pct else "time",
                })

    return pd.DataFrame(results)


def analyze_holdout_validation(df_hourly: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Train heuristics on historical data, test on holdout period.

    Train: Find best hours using HOLDOUT_TRAIN_YEARS
    Test: Apply those rules to HOLDOUT_TEST_YEARS, compare to theoretical optimum
    """
    print("\n  1C. Holdout validation...")

    results = []

    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region]

        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]

            # Split train/test
            train_data = season_data[season_data["year"].isin(HOLDOUT_TRAIN_YEARS)]
            test_data = season_data[season_data["year"].isin(HOLDOUT_TEST_YEARS)]

            if len(train_data) < 100 or len(test_data) < 100:
                continue

            # Train: find best hour
            train_hourly = train_data.groupby("hour")["value_mean"].mean()
            trained_best_hour = train_hourly.idxmin()

            # Test: theoretical best (if we had perfect knowledge)
            test_hourly = test_data.groupby("hour")["value_mean"].mean()
            theoretical_best_hour = test_hourly.idxmin()

            # Calculate emissions
            test_baseline = test_hourly.mean()
            test_theoretical = test_hourly[theoretical_best_hour]
            test_achieved = test_hourly[trained_best_hour]

            if test_baseline <= 0:
                continue

            theoretical_savings = (test_baseline - test_theoretical) / test_baseline
            achieved_savings = (test_baseline - test_achieved) / test_baseline

            if theoretical_savings > 0:
                generalization_ratio = achieved_savings / theoretical_savings
            else:
                generalization_ratio = 1.0

            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "season": season,
                "trained_best_hour": trained_best_hour,
                "theoretical_best_hour": theoretical_best_hour,
                "hours_off": abs(trained_best_hour - theoretical_best_hour),
                "test_baseline": test_baseline,
                "test_theoretical": test_theoretical,
                "test_achieved": test_achieved,
                "theoretical_savings_pct": 100 * theoretical_savings,
                "achieved_savings_pct": 100 * achieved_savings,
                "generalization_ratio": generalization_ratio,
                "generalizes_well": generalization_ratio >= 0.8,
            })

    return pd.DataFrame(results)


def plot_stability_heatmap(stability: pd.DataFrame, figures_dir: Path):
    """Plot heatmap of stability scores by region and season."""

    if len(stability) == 0:
        print("    No stability data to plot")
        return

    pivot = stability.pivot(index="region", columns="season", values="stability_score")

    season_order = ["winter", "spring", "summer", "fall"]
    pivot = pivot[[s for s in season_order if s in pivot.columns]]

    fig, ax = plt.subplots(figsize=(10, max(6, len(pivot) * 0.5)))

    im = ax.imshow(pivot.values, cmap='RdYlGn', vmin=0, vmax=1, aspect='auto')

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([s.capitalize() for s in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([REGIONS.get(r, {}).get("name", r) for r in pivot.index], fontsize=9)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.iloc[i, j]
            if pd.notna(val):
                color = 'white' if val < 0.5 else 'black'
                ax.text(j, i, f"{val:.2f}", ha='center', va='center', fontsize=9, color=color)

    ax.set_title("Year-over-Year Stability Score\n(1.0 = same best hour every year)", fontsize=12)

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Stability Score", fontsize=10)

    plt.tight_layout()
    plt.savefig(figures_dir / "07_stability_heatmap.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_stability_heatmap.png")


def plot_threshold_vs_time(threshold_results: pd.DataFrame, figures_dir: Path):
    """Plot comparison of threshold vs time-based rules."""

    if len(threshold_results) == 0:
        print("    No threshold comparison data to plot")
        return

    # Use P25 as the main comparison
    p25_results = threshold_results[threshold_results["threshold_percentile"] == 25]

    if len(p25_results) == 0:
        p25_results = threshold_results[
            threshold_results["threshold_percentile"] == threshold_results["threshold_percentile"].min()
        ]

    # Aggregate by region
    region_summary = p25_results.groupby("region").agg({
        "time_savings_pct": "mean",
        "threshold_savings_pct": "mean",
        "threshold_advantage_pct": "mean",
    }).reset_index()

    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(region_summary))
    width = 0.35

    ax.bar(x - width/2, region_summary["time_savings_pct"], width,
           label="Time-based (fixed hour)", color="#1f77b4", edgecolor='black')
    ax.bar(x + width/2, region_summary["threshold_savings_pct"], width,
           label="Threshold (P25)", color="#ff7f0e", edgecolor='black')

    ax.set_xlabel("Region")
    ax.set_ylabel("Average Savings vs Baseline (%)")
    ax.set_title("Threshold vs Time-Based Rules: Which Saves More?")
    ax.set_xticks(x)
    ax.set_xticklabels([REGIONS.get(r, {}).get("name", r) for r in region_summary["region"]],
                       rotation=45, ha='right', fontsize=9)
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Add winner indicators
    for i, (_, row) in enumerate(region_summary.iterrows()):
        if row["threshold_advantage_pct"] > 0.5:
            ax.annotate("▲", xy=(i + width/2, row["threshold_savings_pct"] + 0.3),
                        ha='center', fontsize=12, color='green')
        elif row["threshold_advantage_pct"] < -0.5:
            ax.annotate("▲", xy=(i - width/2, row["time_savings_pct"] + 0.3),
                        ha='center', fontsize=12, color='green')

    plt.tight_layout()
    plt.savefig(figures_dir / "07_threshold_vs_time.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_threshold_vs_time.png")


def plot_holdout_validation(holdout_results: pd.DataFrame, figures_dir: Path):
    """Plot holdout validation results."""

    if len(holdout_results) == 0:
        print("    No holdout validation data to plot")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: Scatter of theoretical vs achieved savings
    ax1 = axes[0]
    ax1.scatter(holdout_results["theoretical_savings_pct"],
                holdout_results["achieved_savings_pct"],
                c=[REGION_COLORS.get(r, "#333333") for r in holdout_results["region"]],
                alpha=0.7, s=60, edgecolor='black', linewidth=0.5)

    max_val = max(holdout_results["theoretical_savings_pct"].max(),
                  holdout_results["achieved_savings_pct"].max()) * 1.1
    ax1.plot([0, max_val], [0, max_val], 'r--', linewidth=2, label="Perfect generalization")
    ax1.plot([0, max_val], [0, max_val * 0.8], 'orange', linestyle='--',
             linewidth=1, alpha=0.7, label="80% of theoretical")

    ax1.set_xlabel("Theoretical Savings (%) - Perfect 2024 Knowledge")
    ax1.set_ylabel("Achieved Savings (%) - Using 2022-23 Rules")
    ax1.set_title("Holdout Validation: Do Trained Rules Generalize?")
    ax1.legend(loc='lower right')
    ax1.grid(True, alpha=0.3)

    # Right: Distribution of generalization ratios
    ax2 = axes[1]
    ax2.hist(holdout_results["generalization_ratio"], bins=20,
             color="#1f77b4", edgecolor='black', alpha=0.7)
    ax2.axvline(0.8, color='red', linestyle='--', linewidth=2, label='80% threshold')
    ax2.axvline(holdout_results["generalization_ratio"].mean(), color='green',
                linestyle='-', linewidth=2,
                label=f'Mean: {holdout_results["generalization_ratio"].mean():.2f}')

    ax2.set_xlabel("Generalization Ratio (Achieved / Theoretical)")
    ax2.set_ylabel("Count")
    ax2.set_title("How Well Do Historical Rules Predict Future Savings?")
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')

    pct_good = 100 * (holdout_results["generalization_ratio"] >= 0.8).mean()
    ax2.annotate(f"{pct_good:.0f}% achieve ≥80%\nof theoretical savings",
                 xy=(0.95, 0.95), xycoords='axes fraction', ha='right', va='top',
                 fontsize=10, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig(figures_dir / "07_holdout_validation.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_holdout_validation.png")


# =============================================================================
# SECTION 2: OPERATION CONSTRAINTS
# =============================================================================

def analyze_duration_sensitivity(df_5min: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Analyze how optimal timing changes with operation duration.

    For each duration, slide a window across each day to find the lowest-emission window.
    """
    print("\n  2A. Duration sensitivity...")

    from scipy import stats as sp_stats

    results = []

    for region in df_5min["region"].unique():
        region_data = df_5min[df_5min["region"] == region]

        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]

            if len(season_data) < 1000:
                continue

            dates = season_data["date"].unique()

            for duration in OPERATION_DURATIONS:
                n_intervals = int(duration * 12)  # 5-min intervals

                best_starts = []
                savings_list = []

                for date in dates:
                    day_data = season_data[season_data["date"] == date].sort_values("hour")
                    values = day_data["value"].values
                    hours = day_data["hour"].values

                    if len(values) < n_intervals + 12:
                        continue

                    # Use cumsum for efficient sliding window means
                    cumsum = np.concatenate(([0], np.cumsum(values)))
                    window_sums = cumsum[n_intervals:] - cumsum[:-n_intervals]
                    window_means = window_sums / n_intervals

                    if len(window_means) == 0:
                        continue

                    best_idx = np.argmin(window_means)

                    if best_idx < len(hours):
                        best_starts.append(hours[best_idx])

                    baseline = np.mean(values)
                    if baseline > 0:
                        savings = (baseline - window_means[best_idx]) / baseline
                        savings_list.append(savings)

                if len(best_starts) < 10:
                    continue

                modal_start = sp_stats.mode(best_starts, keepdims=True).mode[0]

                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "duration_hours": duration,
                    "modal_best_start": modal_start,
                    "mean_savings_pct": 100 * np.mean(savings_list),
                    "std_savings_pct": 100 * np.std(savings_list),
                    "n_days": len(best_starts),
                    "start_hour_std": np.std(best_starts),
                })

    return pd.DataFrame(results)


def analyze_deadline_scheduling(df_5min: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Analyze savings when operations must finish by a deadline.

    For each deadline, find optimal start within allowed window.
    Compare to unconstrained optimum.
    """
    print("\n  2B. Deadline scheduling...")

    results = []

    # Use fixed 2-hour duration for this analysis
    duration = 2.0
    n_intervals = int(duration * 12)

    for region in df_5min["region"].unique():
        region_data = df_5min[df_5min["region"] == region]

        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]

            if len(season_data) < 1000:
                continue

            dates = season_data["date"].unique()

            for deadline in DEADLINES:
                latest_start = deadline - duration

                constrained_savings = []
                unconstrained_savings = []

                for date in dates:
                    day_data = season_data[season_data["date"] == date].sort_values("hour")
                    values = day_data["value"].values
                    hours = day_data["hour"].values

                    if len(values) < n_intervals + 12:
                        continue

                    # Use cumsum for efficient sliding window
                    cumsum = np.concatenate(([0], np.cumsum(values)))
                    window_sums = cumsum[n_intervals:] - cumsum[:-n_intervals]
                    window_means = window_sums / n_intervals

                    # Build arrays of (start_hour, mean) efficiently
                    valid_len = min(len(window_means), len(hours))
                    if valid_len == 0:
                        continue

                    w_hours = hours[:valid_len]
                    w_means = window_means[:valid_len]

                    baseline = np.mean(values)
                    if baseline <= 0:
                        continue

                    # Unconstrained best
                    unconstrained_best = w_means.min()
                    unconstrained_savings.append((baseline - unconstrained_best) / baseline)

                    # Constrained best (start <= latest_start)
                    constrained_mask = w_hours <= latest_start
                    if constrained_mask.any():
                        constrained_best = w_means[constrained_mask].min()
                    else:
                        constrained_best = w_means.min()  # fallback
                    constrained_savings.append((baseline - constrained_best) / baseline)

                if len(constrained_savings) < 10:
                    continue

                mean_unconstrained = 100 * np.mean(unconstrained_savings)
                mean_constrained = 100 * np.mean(constrained_savings)

                if mean_unconstrained > 0:
                    flexibility_penalty = (mean_unconstrained - mean_constrained) / mean_unconstrained
                else:
                    flexibility_penalty = 0

                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "deadline": deadline,
                    "duration_hours": duration,
                    "latest_start": latest_start,
                    "unconstrained_savings_pct": mean_unconstrained,
                    "constrained_savings_pct": mean_constrained,
                    "flexibility_penalty_pct": 100 * flexibility_penalty,
                    "n_days": len(constrained_savings),
                })

    return pd.DataFrame(results)


def analyze_shift_constraints(df_5min: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Analyze optimal timing within realistic manufacturing shifts.
    """
    print("\n  2C. Shift-constrained windows...")

    results = []

    for region in df_5min["region"].unique():
        region_data = df_5min[df_5min["region"] == region]

        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]

            if len(season_data) < 1000:
                continue

            # Unconstrained analysis
            hourly_mean = season_data.groupby("hour")["value"].mean()
            unconstrained_best = hourly_mean.min()
            unconstrained_best_hour = hourly_mean.idxmin()
            baseline = hourly_mean.mean()

            if baseline <= 0:
                continue

            unconstrained_savings = (baseline - unconstrained_best) / baseline

            for shift_name, (start, end) in SHIFT_DEFINITIONS.items():
                # Handle overnight shift
                if start > end:
                    shift_hours = list(range(start, 24)) + list(range(0, end))
                else:
                    shift_hours = list(range(start, end))

                shift_data = season_data[season_data["hour"].isin(shift_hours)]

                if len(shift_data) < 100:
                    continue

                shift_hourly = shift_data.groupby("hour")["value"].mean()
                shift_baseline = shift_hourly.mean()
                shift_best = shift_hourly.min()
                shift_best_hour = shift_hourly.idxmin()

                if shift_baseline <= 0:
                    continue

                shift_savings = (shift_baseline - shift_best) / shift_baseline

                if unconstrained_savings > 0:
                    vs_unconstrained = shift_savings / unconstrained_savings
                else:
                    vs_unconstrained = 1.0

                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "shift": shift_name,
                    "shift_hours": f"{start}:00-{end}:00",
                    "best_hour_in_shift": shift_best_hour,
                    "shift_savings_pct": 100 * shift_savings,
                    "unconstrained_savings_pct": 100 * unconstrained_savings,
                    "pct_of_unconstrained": 100 * vs_unconstrained,
                })

    return pd.DataFrame(results)


def plot_duration_heatmap(duration_results: pd.DataFrame, figures_dir: Path):
    """Plot heatmap of optimal start hour by duration and season."""

    if len(duration_results) == 0:
        print("    No duration sensitivity data to plot")
        return

    regions = duration_results["region"].unique()

    if len(regions) <= 2:
        fig, axes = plt.subplots(1, len(regions), figsize=(7 * len(regions), 5))
        if len(regions) == 1:
            axes = [axes]
    else:
        region_counts = duration_results.groupby("region").size().nlargest(4)
        regions = region_counts.index.tolist()
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()

    last_im = None
    for ax, region in zip(axes, regions):
        region_data = duration_results[duration_results["region"] == region]

        pivot = region_data.pivot(index="duration_hours", columns="season", values="modal_best_start")
        pivot = pivot[[s for s in ["winter", "spring", "summer", "fall"] if s in pivot.columns]]

        if pivot.empty:
            ax.set_visible(False)
            continue

        im = ax.imshow(pivot.values, cmap='viridis', aspect='auto', vmin=0, vmax=23)
        last_im = im

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([s.capitalize() for s in pivot.columns])
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([f"{d}h" for d in pivot.index])

        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                val = pivot.iloc[i, j]
                if pd.notna(val):
                    ax.text(j, i, f"{int(val)}:00", ha='center', va='center',
                            fontsize=9, color='white')

        ax.set_xlabel("Season")
        ax.set_ylabel("Operation Duration")
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}")

    # Hide unused axes
    for ax in axes[len(regions):]:
        ax.set_visible(False)

    fig.suptitle("Optimal Start Hour by Duration and Season", fontsize=14)

    if last_im is not None:
        fig.colorbar(last_im, ax=axes[:len(regions)], label="Best Start Hour",
                     shrink=0.6, pad=0.04)

    plt.savefig(figures_dir / "07_duration_heatmap.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 07_duration_heatmap.png")


def plot_deadline_curves(deadline_results: pd.DataFrame, figures_dir: Path):
    """Plot how savings degrade as deadlines tighten."""

    if len(deadline_results) == 0:
        print("    No deadline scheduling data to plot")
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    for region in deadline_results["region"].unique():
        region_data = deadline_results[deadline_results["region"] == region]

        by_deadline = region_data.groupby("deadline").agg({
            "constrained_savings_pct": "mean",
            "unconstrained_savings_pct": "mean",
        }).reset_index()

        ax.plot(by_deadline["deadline"], by_deadline["constrained_savings_pct"],
                color=REGION_COLORS.get(region, "#333333"), linewidth=2, marker='o',
                label=REGIONS.get(region, {}).get("name", region))

    ax.set_xlabel("Deadline (Must Finish By Hour)")
    ax.set_ylabel("Average Savings (%)")
    ax.set_title("How Tight Deadlines Reduce Scheduling Flexibility")
    ax.legend(loc='lower right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(DEADLINES)

    plt.tight_layout()
    plt.savefig(figures_dir / "07_deadline_curves.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_deadline_curves.png")


def plot_shift_comparison(shift_results: pd.DataFrame, figures_dir: Path):
    """Plot savings by shift."""

    if len(shift_results) == 0:
        print("    No shift constraint data to plot")
        return

    shift_summary = shift_results.groupby("shift").agg({
        "shift_savings_pct": ["mean", "std"],
        "pct_of_unconstrained": "mean",
    }).reset_index()
    shift_summary.columns = ["shift", "mean_savings", "std_savings", "pct_of_unconstrained"]

    shift_order = ["first", "second", "third"]
    shift_summary["shift"] = pd.Categorical(shift_summary["shift"], categories=shift_order, ordered=True)
    shift_summary = shift_summary.sort_values("shift")

    fig, ax = plt.subplots(figsize=(8, 5))

    x = np.arange(len(shift_summary))
    ax.bar(x, shift_summary["mean_savings"], yerr=shift_summary["std_savings"],
           color=["#1f77b4", "#ff7f0e", "#2ca02c"], edgecolor='black', capsize=5)

    ax.set_xlabel("Shift")
    ax.set_ylabel("Average Savings (%)")
    ax.set_title("Scheduling Savings by Manufacturing Shift")
    ax.set_xticks(x)
    ax.set_xticklabels(["1st (6am-2pm)", "2nd (2pm-10pm)", "3rd (10pm-6am)"])
    ax.grid(True, alpha=0.3, axis='y')

    for i, (_, row) in enumerate(shift_summary.iterrows()):
        ax.annotate(f"{row['pct_of_unconstrained']:.0f}% of\nmax possible",
                    xy=(i, row['mean_savings'] + row['std_savings'] + 0.5),
                    ha='center', fontsize=9)

    plt.tight_layout()
    plt.savefig(figures_dir / "07_shift_comparison.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_shift_comparison.png")


# =============================================================================
# SECTION 3: GRID BEHAVIOR
# =============================================================================

def analyze_volatility(df_5min: pd.DataFrame, signal: str) -> pd.DataFrame:
    """
    Analyze MOER volatility and ramp rates.

    High volatility = real-time response is valuable
    Low volatility = commit-ahead is fine
    """
    print("\n  3A. Volatility analysis...")

    results = []

    for region in df_5min["region"].unique():
        region_data = df_5min[df_5min["region"] == region].sort_values("point_time_local")

        # Calculate ramp rate (change per 5-min interval)
        ramp = region_data["value"].diff().abs()

        for hour in range(24):
            hour_mask = region_data["hour"] == hour
            hour_values = region_data.loc[hour_mask, "value"]
            hour_ramp = ramp.loc[hour_mask]

            if len(hour_values) < 100:
                continue

            mean_val = hour_values.mean()
            if mean_val <= 0:
                continue

            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "hour": hour,
                "mean_value": mean_val,
                "std_value": hour_values.std(),
                "cv": hour_values.std() / mean_val,
                "mean_ramp": hour_ramp.mean(),
                "p95_ramp": hour_ramp.quantile(0.95),
                "max_ramp": hour_ramp.max(),
            })

    return pd.DataFrame(results)


def analyze_regimes(df_hourly: pd.DataFrame, signal: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cluster daily profiles into regimes.

    Method:
    1. Create normalized daily profiles (24 hourly values / daily mean)
    2. K-means cluster
    3. Characterize each regime
    """
    print("\n  3B. Regime clustering...")

    regime_results = []
    cluster_info = []

    for region in df_hourly["region"].unique():
        region_data = df_hourly[df_hourly["region"] == region]

        # Create daily profiles
        daily_profiles = region_data.pivot_table(
            index="date", columns="hour", values="value_mean", aggfunc="mean"
        ).dropna()

        if len(daily_profiles) < 50:
            continue

        # Normalize each day to its mean
        daily_means = daily_profiles.mean(axis=1)
        # Avoid division by zero
        daily_means = daily_means.replace(0, np.nan)
        normalized = daily_profiles.div(daily_means, axis=0).dropna()

        if len(normalized) < 50:
            continue

        # Cluster
        n_clusters = min(N_REGIMES, len(normalized) // 10)
        if n_clusters < 2:
            n_clusters = 2

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(normalized.values)

        # Analyze each cluster
        for cluster_id in range(kmeans.n_clusters):
            cluster_mask = labels == cluster_id
            centroid = kmeans.cluster_centers_[cluster_id]
            best_hour = int(np.argmin(centroid))
            worst_hour = int(np.argmax(centroid))

            # Characterize shape
            morning_avg = centroid[6:12].mean()
            afternoon_avg = centroid[12:18].mean()
            evening_avg = centroid[18:22].mean()
            night_avg = np.concatenate([centroid[0:6], centroid[22:24]]).mean()

            if afternoon_avg < morning_avg and afternoon_avg < evening_avg:
                shape = "midday_dip"
            elif evening_avg < morning_avg and evening_avg < afternoon_avg:
                shape = "evening_dip"
            elif morning_avg < afternoon_avg and morning_avg < evening_avg:
                shape = "morning_dip"
            elif np.std(centroid) < 0.05:
                shape = "flat"
            else:
                shape = "other"

            cluster_info.append({
                "region": region,
                "cluster_id": cluster_id,
                "n_days": int(cluster_mask.sum()),
                "pct_of_days": 100 * cluster_mask.sum() / len(labels),
                "best_hour": best_hour,
                "worst_hour": worst_hour,
                "shape": shape,
                "centroid": centroid.tolist(),
            })

        # Add cluster labels to results
        for date, label in zip(normalized.index, labels):
            month = date.month
            if month in [12, 1, 2]:
                season = "winter"
            elif month in [3, 4, 5]:
                season = "spring"
            elif month in [6, 7, 8]:
                season = "summer"
            else:
                season = "fall"

            regime_results.append({
                "region": region,
                "date": date,
                "cluster_id": int(label),
                "season": season,
            })

    return pd.DataFrame(regime_results), pd.DataFrame(cluster_info)


def analyze_miso_investigation(df_hourly: pd.DataFrame, signal: str) -> Optional[pd.DataFrame]:
    """
    Investigate MISO 6pm anomaly (evening minimum).
    """
    print("\n  3C. MISO investigation...")

    miso_regions = [r for r in df_hourly["region"].unique() if "MISO" in r]

    if not miso_regions:
        print("    No MISO regions in data")
        return None

    results = []

    for region in miso_regions:
        region_data = df_hourly[df_hourly["region"] == region]

        for year in region_data["year"].unique():
            year_data = region_data[region_data["year"] == year]

            hourly_mean = year_data.groupby("hour")["value_mean"].mean()

            if len(hourly_mean) < 20:
                continue

            best_hour = hourly_mean.idxmin()
            afternoon_mean = hourly_mean[12:17].mean()
            evening_mean = hourly_mean[17:21].mean()

            has_evening_dip = evening_mean < afternoon_mean
            dip_magnitude = afternoon_mean - evening_mean

            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "year": int(year),
                "best_hour": int(best_hour),
                "has_evening_dip": has_evening_dip,
                "evening_dip_magnitude": float(dip_magnitude) if has_evening_dip else 0,
                "afternoon_mean": float(afternoon_mean),
                "evening_mean": float(evening_mean),
            })

    return pd.DataFrame(results) if results else None


def plot_volatility_heatmap(volatility: pd.DataFrame, figures_dir: Path):
    """Plot volatility by hour and region."""

    if len(volatility) == 0:
        print("    No volatility data to plot")
        return

    pivot = volatility.pivot(index="region", columns="hour", values="cv")

    fig, ax = plt.subplots(figsize=(14, max(4, len(pivot) * 0.4)))

    im = ax.imshow(pivot.values, cmap='YlOrRd', aspect='auto')

    ax.set_xticks(range(24))
    ax.set_xticklabels(range(24))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([REGIONS.get(r, {}).get("name", r) for r in pivot.index], fontsize=9)

    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Region")
    ax.set_title("MOER Volatility (Coefficient of Variation) by Hour")

    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("CV (σ/μ)")

    plt.tight_layout()
    plt.savefig(figures_dir / "07_volatility_heatmap.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_volatility_heatmap.png")


def plot_regime_profiles(cluster_info: pd.DataFrame, figures_dir: Path):
    """Plot cluster centroid profiles."""

    if len(cluster_info) == 0:
        print("    No regime clustering data to plot")
        return

    regions = cluster_info["region"].unique()

    n_regions = min(4, len(regions))
    fig, axes = plt.subplots(1, n_regions, figsize=(5 * n_regions, 4))

    if n_regions == 1:
        axes = [axes]

    for ax, region in zip(axes, regions[:n_regions]):
        region_clusters = cluster_info[cluster_info["region"] == region]

        for _, row in region_clusters.iterrows():
            centroid = np.array(row["centroid"])
            label = f"{row['shape']} ({row['pct_of_days']:.0f}%)"
            ax.plot(range(24), centroid, linewidth=2, label=label, marker='o', markersize=3)

        ax.axhline(1.0, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlabel("Hour of Day")
        ax.set_ylabel("Normalized Value (1.0 = daily mean)")
        ax.set_title(f"{REGIONS.get(region, {}).get('name', region)}")
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0, 23)

    fig.suptitle("Daily Profile Regimes (Cluster Centroids)", fontsize=14)
    plt.tight_layout()
    plt.savefig(figures_dir / "07_regime_profiles.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 07_regime_profiles.png")


def plot_miso_investigation(miso_results: pd.DataFrame, figures_dir: Path):
    """Plot MISO investigation results."""

    if miso_results is None or len(miso_results) == 0:
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    regions = miso_results["region"].unique()

    # Left: Best hour by year
    ax1 = axes[0]
    for region in regions:
        region_data = miso_results[miso_results["region"] == region]
        ax1.plot(region_data["year"], region_data["best_hour"],
                 marker='o', linewidth=2, label=REGIONS.get(region, {}).get("name", region))

    ax1.set_xlabel("Year")
    ax1.set_ylabel("Best Hour")
    ax1.set_title("MISO Best Hour by Year")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Right: Evening dip magnitude
    ax2 = axes[1]
    n_regions = len(regions)
    bar_width = 0.8 / max(n_regions, 1)
    for i, region in enumerate(regions):
        region_data = miso_results[miso_results["region"] == region]
        offset = (i - n_regions / 2 + 0.5) * bar_width
        ax2.bar(region_data["year"].astype(float) + offset,
                region_data["evening_dip_magnitude"], width=bar_width,
                label=REGIONS.get(region, {}).get("name", region))

    ax2.set_xlabel("Year")
    ax2.set_ylabel("Evening Dip Magnitude")
    ax2.set_title("MISO Evening Dip (Afternoon - Evening Mean)")
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(figures_dir / "07_miso_investigation.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_miso_investigation.png")


# =============================================================================
# SECTION 4: FORECAST VALUE
# =============================================================================

def analyze_forecast_value(
    df_5min: pd.DataFrame,
    df_forecast: pd.DataFrame,
    signal: str
) -> pd.DataFrame:
    """
    Analyze achieved vs theoretical savings given forecast errors.

    Processes per-region to avoid memory blowup on large forecast datasets.
    The forecast DataFrame can be 400M+ rows, so we never filter/copy globally.
    """
    print("\n  4A. Forecast value analysis...")

    # Ensure datetime types (in-place, no copy)
    if not pd.api.types.is_datetime64_any_dtype(df_forecast["point_time"]):
        df_forecast["point_time"] = pd.to_datetime(df_forecast["point_time"], utc=True)
    if not pd.api.types.is_datetime64_any_dtype(df_forecast["generated_at"]):
        df_forecast["generated_at"] = pd.to_datetime(df_forecast["generated_at"], utc=True)
    if not pd.api.types.is_datetime64_any_dtype(df_5min["point_time"]):
        df_5min["point_time"] = pd.to_datetime(df_5min["point_time"], utc=True)

    results = []
    regions = df_forecast["region"].unique()

    for region in regions:
        print(f"    Processing region: {region}")

        # ---- Filter to region FIRST (reduces from 400M to ~68M rows) ----
        forecast_region = df_forecast.loc[df_forecast["region"] == region]
        actual_region = df_5min.loc[df_5min["region"] == region]

        if len(forecast_region) == 0 or len(actual_region) == 0:
            print(f"      Skipping {region}: no data")
            continue

        # ---- Compute horizon on regional subset only (no new column on full df) ----
        horizon_seconds = (
            forecast_region["point_time"] - forecast_region["generated_at"]
        ).dt.total_seconds()

        # ---- Filter to day-ahead window via boolean mask (no .copy()) ----
        day_ahead_mask = (horizon_seconds >= 12 * 3600) & (horizon_seconds <= 36 * 3600)
        forecast_region = forecast_region.loc[day_ahead_mask]

        if len(forecast_region) == 0:
            print(f"      No day-ahead forecast data for {region}")
            continue

        print(f"      Day-ahead records: {len(forecast_region):,}")

        # Free the mask memory
        del horizon_seconds, day_ahead_mask
        gc.collect()

        # ---- Get overlapping dates ----
        forecast_dates = set(forecast_region["point_time"].dt.date.unique())
        actual_dates = set(actual_region["point_time"].dt.date.unique())
        common_dates = sorted(forecast_dates & actual_dates)

        n_dates = min(len(common_dates), FORECAST_MAX_DAYS_PER_REGION)
        print(f"      Analyzing {n_dates} of {len(common_dates)} common dates")

        for date in common_dates[:n_dates]:
            day_forecast = forecast_region[forecast_region["point_time"].dt.date == date]
            day_actual = actual_region[actual_region["point_time"].dt.date == date]

            if len(day_forecast) < 12 or len(day_actual) < 200:
                continue

            # Aggregate to hourly
            forecast_hourly = day_forecast.groupby(
                day_forecast["point_time"].dt.hour
            )["value"].mean()
            actual_hourly = day_actual.groupby("hour")["value"].mean()

            if len(forecast_hourly) < 20 or len(actual_hourly) < 20:
                continue

            forecast_best_hour = forecast_hourly.idxmin()
            actual_best_hour = actual_hourly.idxmin()

            baseline = actual_hourly.mean()
            theoretical_best = actual_hourly[actual_best_hour]
            achieved = actual_hourly.get(forecast_best_hour, baseline)

            if baseline <= 0:
                continue

            theoretical_savings = (baseline - theoretical_best) / baseline
            achieved_savings = (baseline - achieved) / baseline
            capture_rate = (achieved_savings / theoretical_savings) if theoretical_savings > 0 else 1.0

            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "date": date,
                "forecast_best_hour": int(forecast_best_hour),
                "actual_best_hour": int(actual_best_hour),
                "hours_off": abs(int(forecast_best_hour) - int(actual_best_hour)),
                "theoretical_savings_pct": 100 * theoretical_savings,
                "achieved_savings_pct": 100 * achieved_savings,
                "capture_rate": capture_rate,
            })

        # Free regional data before next iteration
        del forecast_region, actual_region
        gc.collect()

    return pd.DataFrame(results)


def plot_forecast_value(forecast_value: pd.DataFrame, figures_dir: Path):
    """Plot forecast value analysis results."""

    if len(forecast_value) == 0:
        print("    No forecast value data to plot")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Capture rate distribution
    ax1 = axes[0]
    ax1.hist(forecast_value["capture_rate"], bins=20, color="#1f77b4",
             edgecolor='black', alpha=0.7)
    ax1.axvline(0.8, color='red', linestyle='--', linewidth=2, label='80% threshold')
    ax1.axvline(forecast_value["capture_rate"].mean(), color='green',
                linestyle='-', linewidth=2,
                label=f'Mean: {forecast_value["capture_rate"].mean():.2f}')

    ax1.set_xlabel("Capture Rate (Achieved / Theoretical)")
    ax1.set_ylabel("Number of Days")
    ax1.set_title("How Much of Theoretical Savings Does Forecast Achieve?")
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')

    pct_good = 100 * (forecast_value["capture_rate"] >= 0.8).mean()
    ax1.annotate(f"{pct_good:.0f}% of days\nachieve ≥80%",
                 xy=(0.95, 0.95), xycoords='axes fraction', ha='right', va='top',
                 fontsize=10, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    # Right: Hours off distribution
    ax2 = axes[1]
    hours_off_counts = forecast_value["hours_off"].value_counts().sort_index()
    ax2.bar(hours_off_counts.index, hours_off_counts.values,
            color="#ff7f0e", edgecolor='black')

    ax2.set_xlabel("Hours Off from Actual Best Hour")
    ax2.set_ylabel("Number of Days")
    ax2.set_title("How Accurate is the Day-Ahead Best Hour Forecast?")
    ax2.grid(True, alpha=0.3, axis='y')

    exact_pct = 100 * (forecast_value["hours_off"] == 0).mean()
    within2_pct = 100 * (forecast_value["hours_off"] <= 2).mean()
    ax2.annotate(f"Exact: {exact_pct:.0f}%\nWithin 2h: {within2_pct:.0f}%",
                 xy=(0.95, 0.95), xycoords='axes fraction', ha='right', va='top',
                 fontsize=10, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig(figures_dir / "07_forecast_value.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 07_forecast_value.png")


# =============================================================================
# SUMMARY AND MAIN
# =============================================================================

def generate_summary_report(
    stability: pd.DataFrame,
    threshold_results: pd.DataFrame,
    holdout_results: pd.DataFrame,
    duration_results: pd.DataFrame,
    shift_results: pd.DataFrame,
    cluster_info: pd.DataFrame,
    forecast_value: pd.DataFrame,
    signal: str,
    outputs_dir: Path
):
    """Generate a text summary report."""

    unit_label = get_unit_label(signal)

    lines = [
        "=" * 70,
        "ADVANCED ANALYSIS SUMMARY REPORT",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        "",
    ]

    # Robustness
    lines.extend([
        "-" * 70,
        "1. ROBUSTNESS ANALYSIS",
        "-" * 70,
    ])

    if len(stability) > 0:
        stable_pct = 100 * stability["is_stable"].mean()
        lines.append(f"\nYear-over-Year Stability:")
        lines.append(f"  {stable_pct:.0f}% of region/season combinations are stable (score >= 0.7)")
        lines.append(f"  Mean stability score: {stability['stability_score'].mean():.2f}")

    if len(threshold_results) > 0:
        threshold_wins = (threshold_results["winner"] == "threshold").mean()
        lines.append(f"\nThreshold vs Time-Based Rules:")
        lines.append(f"  Threshold rules win {100*threshold_wins:.0f}% of comparisons")
        lines.append(f"  Average threshold advantage: {threshold_results['threshold_advantage_pct'].mean():.1f}%")

    if len(holdout_results) > 0:
        gen_good = (holdout_results["generalization_ratio"] >= 0.8).mean()
        lines.append(f"\nHoldout Validation (2022-23 -> 2024):")
        lines.append(f"  {100*gen_good:.0f}% achieve >=80% of theoretical savings")
        lines.append(f"  Mean generalization ratio: {holdout_results['generalization_ratio'].mean():.2f}")

    # Constraints
    lines.extend([
        "",
        "-" * 70,
        "2. OPERATION CONSTRAINTS",
        "-" * 70,
    ])

    if len(duration_results) > 0:
        lines.append(f"\nDuration Sensitivity:")
        for dur in sorted(duration_results["duration_hours"].unique()):
            dur_data = duration_results[duration_results["duration_hours"] == dur]
            lines.append(f"  {dur}h operation: {dur_data['mean_savings_pct'].mean():.1f}% avg savings")

    if len(shift_results) > 0:
        lines.append(f"\nShift Constraints:")
        for shift in ["first", "second", "third"]:
            shift_data = shift_results[shift_results["shift"] == shift]
            if len(shift_data) > 0:
                lines.append(f"  {shift.capitalize()} shift: {shift_data['pct_of_unconstrained'].mean():.0f}% of unconstrained savings")

    # Grid behavior
    lines.extend([
        "",
        "-" * 70,
        "3. GRID BEHAVIOR",
        "-" * 70,
    ])

    if len(cluster_info) > 0:
        lines.append(f"\nRegime Analysis:")
        for region in cluster_info["region"].unique():
            region_clusters = cluster_info[cluster_info["region"] == region]
            shapes = region_clusters["shape"].value_counts()
            lines.append(f"  {REGIONS.get(region, {}).get('name', region)}:")
            for shape, count in shapes.items():
                pct = region_clusters[region_clusters["shape"] == shape]["pct_of_days"].sum()
                lines.append(f"    {shape}: {pct:.0f}% of days")

    # Forecast
    if len(forecast_value) > 0:
        lines.extend([
            "",
            "-" * 70,
            "4. FORECAST VALUE",
            "-" * 70,
        ])
        lines.append(f"\nDay-Ahead Forecast Performance:")
        lines.append(f"  Mean capture rate: {forecast_value['capture_rate'].mean():.2f}")
        lines.append(f"  Days achieving >=80%: {100*(forecast_value['capture_rate'] >= 0.8).mean():.0f}%")
        lines.append(f"  Exact best-hour match: {100*(forecast_value['hours_off'] == 0).mean():.0f}%")

    lines.extend([
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])

    report_text = "\n".join(lines)

    with open(outputs_dir / "07_summary_report.txt", "w", encoding="utf-8") as f:
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
    print("ADVANCED HEURISTIC ANALYSIS")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print(f"Regions: {len(config['regions'])} regions")
    print("=" * 70)

    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"

    # Load data
    df_5min, df_hourly, df_daily = load_data(run_dir)
    df_forecast = load_forecast_data(run_dir) if RUN_FORECAST_VALUE else None

    # Check requirements
    requirements = check_data_requirements(df_5min)
    print(f"\nData: {requirements['n_years']} years, {requirements['n_regions']} regions")
    print(f"  Years: {requirements['years']}")

    # Initialize result containers
    stability = pd.DataFrame()
    threshold_results = pd.DataFrame()
    holdout_results = pd.DataFrame()
    duration_results = pd.DataFrame()
    deadline_results = pd.DataFrame()
    shift_results = pd.DataFrame()
    volatility = pd.DataFrame()
    regime_results = pd.DataFrame()
    cluster_info = pd.DataFrame()
    miso_results = None
    forecast_value = pd.DataFrame()

    # ==========================================================================
    # SECTION 1: ROBUSTNESS
    # ==========================================================================
    if RUN_ROBUSTNESS:
        print("\n" + "=" * 70)
        print("SECTION 1: ROBUSTNESS ANALYSIS")
        print("=" * 70)

        if requirements["can_stability"]:
            stability = analyze_year_over_year_stability(df_hourly, signal)
            stability.to_csv(outputs_dir / "07_stability.csv", index=False)
            plot_stability_heatmap(stability, figures_dir)
        else:
            print(f"  Skipping stability (need {STABILITY_MIN_YEARS}+ years)")

        threshold_results = analyze_threshold_vs_time_rules(df_5min, signal)
        threshold_results.to_csv(outputs_dir / "07_threshold_vs_time.csv", index=False)
        plot_threshold_vs_time(threshold_results, figures_dir)

        if requirements["can_holdout"]:
            holdout_results = analyze_holdout_validation(df_hourly, signal)
            holdout_results.to_csv(outputs_dir / "07_holdout_validation.csv", index=False)
            plot_holdout_validation(holdout_results, figures_dir)
        else:
            print(f"  Skipping holdout (need years {HOLDOUT_TRAIN_YEARS} and {HOLDOUT_TEST_YEARS})")

    # ==========================================================================
    # SECTION 2: CONSTRAINTS
    # ==========================================================================
    if RUN_CONSTRAINTS:
        print("\n" + "=" * 70)
        print("SECTION 2: OPERATION CONSTRAINTS")
        print("=" * 70)

        duration_results = analyze_duration_sensitivity(df_5min, signal)
        duration_results.to_csv(outputs_dir / "07_duration_sensitivity.csv", index=False)
        plot_duration_heatmap(duration_results, figures_dir)

        deadline_results = analyze_deadline_scheduling(df_5min, signal)
        deadline_results.to_csv(outputs_dir / "07_deadline_scheduling.csv", index=False)
        plot_deadline_curves(deadline_results, figures_dir)

        shift_results = analyze_shift_constraints(df_5min, signal)
        shift_results.to_csv(outputs_dir / "07_shift_constraints.csv", index=False)
        plot_shift_comparison(shift_results, figures_dir)

    # ==========================================================================
    # SECTION 3: GRID BEHAVIOR
    # ==========================================================================
    if RUN_GRID_BEHAVIOR:
        print("\n" + "=" * 70)
        print("SECTION 3: GRID BEHAVIOR")
        print("=" * 70)

        volatility = analyze_volatility(df_5min, signal)
        volatility.to_csv(outputs_dir / "07_volatility.csv", index=False)
        plot_volatility_heatmap(volatility, figures_dir)

        regime_results, cluster_info = analyze_regimes(df_hourly, signal)
        regime_results.to_csv(outputs_dir / "07_regime_assignments.csv", index=False)
        cluster_info.to_csv(outputs_dir / "07_regime_clusters.csv", index=False)
        plot_regime_profiles(cluster_info, figures_dir)

        if requirements["has_miso"]:
            miso_results = analyze_miso_investigation(df_hourly, signal)
            if miso_results is not None and len(miso_results) > 0:
                miso_results.to_csv(outputs_dir / "07_miso_investigation.csv", index=False)
                plot_miso_investigation(miso_results, figures_dir)

    # ==========================================================================
    # SECTION 4: FORECAST VALUE
    # ==========================================================================
    if RUN_FORECAST_VALUE and df_forecast is not None:
        print("\n" + "=" * 70)
        print("SECTION 4: FORECAST VALUE")
        print("=" * 70)

        forecast_value = analyze_forecast_value(df_5min, df_forecast, signal)
        if len(forecast_value) > 0:
            forecast_value.to_csv(outputs_dir / "07_forecast_value.csv", index=False)
            plot_forecast_value(forecast_value, figures_dir)

        # Free forecast data after use
        del df_forecast
        gc.collect()

    elif RUN_FORECAST_VALUE:
        print("\n  Skipping forecast value (no forecast data in run)")

    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)

    generate_summary_report(
        stability, threshold_results, holdout_results,
        duration_results, shift_results, cluster_info,
        forecast_value, signal, outputs_dir
    )

    # Mark script as run
    mark_script_run(run_dir, "07_advanced_analysis")

    print("\n" + "=" * 70)
    print("ADVANCED ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/07_*.png")
    print(f"Data: {outputs_dir}/07_*.csv")
    print(f"Report: {outputs_dir}/07_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()