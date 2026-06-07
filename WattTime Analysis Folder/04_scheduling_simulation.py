"""
04_scheduling_simulation.py - Scheduling Flexibility Simulation

Quantifies emissions savings from flexible CNC job scheduling.
Simulates optimal vs baseline scheduling within shift windows.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit the CONFIG section below to point to your run folder
    3. Run: python 04_scheduling_simulation.py

Output (in run folder):
    - figures/04_savings_by_duration_{region}.png
    - figures/04_savings_by_season_{region}.png
    - figures/04_savings_distribution_{region}.png
    - figures/04_savings_comparison_all_regions.png
    - figures/04_consistency_heatmap.png
    - figures/04_flexibility_vs_savings.png
    - outputs/scheduling_simulation_results.parquet
    - outputs/scheduling_summary.csv
    - outputs/consistency_scores.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, SHIFTS, JOB_DURATIONS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS, SEASON_COLORS,
    CONSISTENCY_THRESHOLD, FLEXIBILITY_WINDOWS_HOURS,
    REFERENCE_JOB_KWH,
    get_signal_metadata, get_unit_label
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run folder to analyze (created by 02_data_processing.py)
# Use the folder name from runs/, e.g., "2025-01-28_moer_temporal"
# Or set to None to use the most recent run
RUN_FOLDER = "2026-03-04_AOER_6RegionSummary_V1" # Will auto-detect most recent run

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================


def get_run_dir() -> Path:
    """Get the run directory, auto-detecting if not specified."""
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
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
    """Load 5-minute processed data."""
    print("Loading 5-minute data...")
    df = pd.read_parquet(run_dir / "processed" / "data_5min.parquet")
    print(f"  Loaded {len(df):,} records")
    return df


def get_shift_data(df: pd.DataFrame, date: pd.Timestamp, shift: str, region: str) -> pd.DataFrame:
    """Extract data for a specific shift on a specific date."""
    
    shift_config = SHIFTS[shift]
    start_hour = shift_config["start"]
    end_hour = shift_config["end"]
    
    region_data = df[df["region"] == region].copy()
    
    # Normalize the target date for comparison (strip time component)
    target_date = pd.Timestamp(date).normalize()
    
    # Ensure date column is datetime
    if not pd.api.types.is_datetime64_any_dtype(region_data["date"]):
        region_data["date"] = pd.to_datetime(region_data["date"])
    
    # Normalize dates in data for comparison
    region_data["date_normalized"] = region_data["date"].dt.normalize()
    
    if shift == "night":
        # Night shift crosses midnight: 22:00 to 06:00
        evening_mask = (region_data["date_normalized"] == target_date) & (region_data["hour"] >= start_hour)
        next_date = target_date + pd.Timedelta(days=1)
        morning_mask = (region_data["date_normalized"] == next_date) & (region_data["hour"] < end_hour)
        shift_data = region_data[evening_mask | morning_mask]
    else:
        shift_data = region_data[
            (region_data["date_normalized"] == target_date) & 
            (region_data["hour"] >= start_hour) & 
            (region_data["hour"] < end_hour)
        ]
    
    return shift_data.sort_values("point_time_local")


def calculate_optimal_window(moer_values: np.ndarray, job_duration_intervals: int) -> Tuple[int, float, float]:
    """Find the optimal (lowest value) window for a job of given duration."""
    if len(moer_values) < job_duration_intervals:
        return None, None, None
    
    rolling_mean = pd.Series(moer_values).rolling(window=job_duration_intervals).mean()
    valid_means = rolling_mean.dropna()
    
    if len(valid_means) == 0:
        return None, None, None
    
    best_idx = valid_means.idxmin()
    worst_idx = valid_means.idxmax()
    
    optimal_value = valid_means[best_idx]
    worst_value = valid_means[worst_idx]
    
    return best_idx - job_duration_intervals + 1, optimal_value, worst_value


def simulate_single_day(df: pd.DataFrame, date: pd.Timestamp, region: str, 
                        shift: str, job_duration_hours: float, signal: str) -> Dict:
    """Simulate scheduling for a single day/shift/job combination."""
    
    shift_data = get_shift_data(df, date, shift, region)
    
    if len(shift_data) < 12:
        return None
    
    values = shift_data["value"].values
    job_intervals = int(job_duration_hours * 12)
    
    if len(values) < job_intervals:
        return None
    
    baseline_value = values.mean()
    best_start, optimal_value, worst_value = calculate_optimal_window(values, job_intervals)
    
    if optimal_value is None:
        return None
    
    savings_vs_baseline_pct = 100 * (baseline_value - optimal_value) / baseline_value
    savings_vs_worst_pct = 100 * (worst_value - optimal_value) / worst_value
    
    # Absolute savings for reference job (only meaningful for MOER)
    if signal == "co2_moer":
        baseline_co2_g = baseline_value * REFERENCE_JOB_KWH * 0.001 * 453.592
        optimal_co2_g = optimal_value * REFERENCE_JOB_KWH * 0.001 * 453.592
        saved_co2_g = baseline_co2_g - optimal_co2_g
    else:
        baseline_co2_g = None
        optimal_co2_g = None
        saved_co2_g = None
    
    optimal_start_hour = shift_data.iloc[best_start]["hour"] if best_start is not None else None
    optimal_start_minute = shift_data.iloc[best_start]["minute"] if best_start is not None else None
    
    return {
        "date": date,
        "region": region,
        "shift": shift,
        "job_duration_hours": job_duration_hours,
        "baseline_value": baseline_value,
        "optimal_value": optimal_value,
        "worst_value": worst_value,
        "savings_vs_baseline_pct": savings_vs_baseline_pct,
        "savings_vs_worst_pct": savings_vs_worst_pct,
        "baseline_co2_g": baseline_co2_g,
        "optimal_co2_g": optimal_co2_g,
        "saved_co2_g": saved_co2_g,
        "optimal_start_hour": optimal_start_hour,
        "optimal_start_minute": optimal_start_minute,
        "n_intervals": len(values),
    }

def get_shift_data_fast(region_data: pd.DataFrame, date: pd.Timestamp, shift: str) -> pd.DataFrame:
    """Extract data for a specific shift - assumes region already filtered."""
    
    shift_config = SHIFTS[shift]
    start_hour = shift_config["start"]
    end_hour = shift_config["end"]
    
    if shift == "night":
        # Night shift crosses midnight: 22:00 to 06:00
        next_date = date + pd.Timedelta(days=1)
        evening_mask = (region_data["date_normalized"] == date) & (region_data["hour"] >= start_hour)
        morning_mask = (region_data["date_normalized"] == next_date) & (region_data["hour"] < end_hour)
        shift_data = region_data[evening_mask | morning_mask]
    else:
        shift_data = region_data[
            (region_data["date_normalized"] == date) & 
            (region_data["hour"] >= start_hour) & 
            (region_data["hour"] < end_hour)
        ]
    
    return shift_data.sort_values("point_time_local")


def simulate_single_day_fast(shift_data: pd.DataFrame, date: pd.Timestamp, region: str,
                              shift: str, job_duration_hours: float, signal: str) -> Dict:
    """Simulate scheduling - shift_data already extracted."""
    
    values = shift_data["value"].values
    job_intervals = int(job_duration_hours * 12)
    
    if len(values) < job_intervals:
        return None
    
    baseline_value = values.mean()
    best_start, optimal_value, worst_value = calculate_optimal_window(values, job_intervals)
    
    if optimal_value is None:
        return None
    
    savings_vs_baseline_pct = 100 * (baseline_value - optimal_value) / baseline_value
    savings_vs_worst_pct = 100 * (worst_value - optimal_value) / worst_value
    
    # Absolute savings for reference job (only meaningful for MOER)
    if signal == "co2_moer":
        baseline_co2_g = baseline_value * REFERENCE_JOB_KWH * 0.001 * 453.592
        optimal_co2_g = optimal_value * REFERENCE_JOB_KWH * 0.001 * 453.592
        saved_co2_g = baseline_co2_g - optimal_co2_g
    else:
        baseline_co2_g = None
        optimal_co2_g = None
        saved_co2_g = None
    
    optimal_start_hour = shift_data.iloc[best_start]["hour"] if best_start is not None and best_start < len(shift_data) else None
    optimal_start_minute = shift_data.iloc[best_start]["minute"] if best_start is not None and best_start < len(shift_data) else None
    
    return {
        "date": date,
        "region": region,
        "shift": shift,
        "job_duration_hours": job_duration_hours,
        "baseline_value": baseline_value,
        "optimal_value": optimal_value,
        "worst_value": worst_value,
        "savings_vs_baseline_pct": savings_vs_baseline_pct,
        "savings_vs_worst_pct": savings_vs_worst_pct,
        "baseline_co2_g": baseline_co2_g,
        "optimal_co2_g": optimal_co2_g,
        "saved_co2_g": saved_co2_g,
        "optimal_start_hour": optimal_start_hour,
        "optimal_start_minute": optimal_start_minute,
        "n_intervals": len(values),
    }

def run_simulation(df: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Run full scheduling simulation across all combinations."""
    
    print("\nRunning scheduling simulation...")
    
    results = []
    regions_in_data = sorted(df["region"].unique())
    
    total_combos = 0
    for region in regions_in_data:
        dates = df[df["region"] == region]["date"].unique()
        total_combos += len(dates) * len(SHIFTS) * len(JOB_DURATIONS)
    
    print(f"  Total combinations to simulate: {total_combos:,}")
    
    # Pre-process date column once
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"])
    df["date_normalized"] = df["date"].dt.normalize()
    
    for region in regions_in_data:
        # Filter by region ONCE
        region_data = df[df["region"] == region].copy()
        dates = sorted(region_data["date_normalized"].unique())
        
        for date in dates:
            date_ts = pd.Timestamp(date).normalize()
            
            for shift in SHIFTS.keys():
                # Get shift data using pre-filtered region_data
                shift_data = get_shift_data_fast(region_data, date_ts, shift)
                
                if len(shift_data) < 12:
                    continue
                
                for job_duration in JOB_DURATIONS:
                    result = simulate_single_day_fast(shift_data, date_ts, region, shift, job_duration, signal)
                    if result:
                        results.append(result)
        
        print(f"  {region}: completed")
    
    results_df = pd.DataFrame(results)
    print(f"  Valid simulations: {len(results_df):,}")
    
    return results_df


def add_result_features(results: pd.DataFrame) -> pd.DataFrame:
    """Add season, year, etc. to results."""
    
    results["date"] = pd.to_datetime(results["date"])
    results["year"] = results["date"].dt.year
    results["month"] = results["date"].dt.month
    results["day_of_week"] = results["date"].dt.dayofweek
    results["is_weekend"] = results["day_of_week"].isin([5, 6])
    
    def get_season(month):
        for season, months in SEASONS.items():
            if month in months:
                return season
        return None
    
    results["season"] = results["month"].apply(get_season)
    results["optimal_start_hour_bin"] = results["optimal_start_hour"].apply(
        lambda x: f"{int(x):02d}:00" if pd.notna(x) else None
    )
    
    return results


def plot_savings_comparison_all_regions(results: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot savings comparison across all regions."""
    
    unit_label = get_unit_label(signal)
    
    # Focus on 2-hour job, day shift
    subset = results[(results["job_duration_hours"] == 2.0) & (results["shift"] == "day")]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    regions = sorted(subset["region"].unique())
    data_to_plot = [subset[subset["region"] == r]["savings_vs_baseline_pct"].values for r in regions]
    
    bp = ax.boxplot(data_to_plot,
                    tick_labels=[REGIONS.get(r, {}).get("name", r) for r in regions],
                    patch_artist=True)
    
    for patch, region in zip(bp['boxes'], regions):
        patch.set_facecolor(REGION_COLORS.get(region, "#cccccc"))
        patch.set_alpha(0.7)
    
    ax.set_ylabel("Savings vs Baseline (%)", fontsize=12)
    ax.set_title("Scheduling Savings Potential by Region\n(2hr Job, Day Shift)", fontsize=14)
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True, alpha=0.3, axis='y')
    ax.axhline(0, color='black', linewidth=1)
    
    plt.tight_layout()
    
    outpath = figures_dir / "04_savings_comparison_all_regions.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def plot_savings_by_season(results: pd.DataFrame, region: str, signal: str, figures_dir: Path):
    """Plot savings by season for a region."""
    
    subset = results[(results["region"] == region) & 
                     (results["job_duration_hours"] == 2.0) &
                     (results["shift"] == "day")]
    
    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    
    seasons = ["winter", "spring", "summer", "fall"]
    data_to_plot = [subset[subset["season"] == s]["savings_vs_baseline_pct"].values for s in seasons]
    
    bp = ax.boxplot(data_to_plot, tick_labels=[s.capitalize() for s in seasons], patch_artist=True)
    
    for patch, season in zip(bp['boxes'], seasons):
        patch.set_facecolor(SEASON_COLORS[season])
        patch.set_alpha(0.7)
    
    ax.set_ylabel("Savings vs Baseline (%)", fontsize=12)
    ax.set_title(f"Seasonal Savings: {REGIONS[region]['name']}\n(2hr Job, Day Shift)", fontsize=14)
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    
    outpath = figures_dir / f"04_savings_by_season_{region}.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def calculate_consistency_scores(results: pd.DataFrame) -> pd.DataFrame:
    """Calculate how often the same hour is optimal."""
    
    consistency_rows = []
    
    for region in results["region"].unique():
        for season in results["season"].unique():
            for shift in results["shift"].unique():
                subset = results[(results["region"] == region) &
                                (results["season"] == season) &
                                (results["shift"] == shift) &
                                (results["job_duration_hours"] == 2.0)]
                
                if len(subset) < 30:
                    continue
                
                modal_hour = subset["optimal_start_hour"].mode()
                if len(modal_hour) == 0:
                    continue
                modal_hour = int(modal_hour.iloc[0])
                
                consistency_pct = 100 * (subset["optimal_start_hour"] == modal_hour).mean()
                
                consistency_rows.append({
                    "region": region,
                    "season": season,
                    "shift": shift,
                    "modal_hour": modal_hour,
                    "consistency_pct": consistency_pct,
                    "n_days": len(subset),
                })
    
    return pd.DataFrame(consistency_rows)


def plot_consistency_heatmap(consistency: pd.DataFrame, figures_dir: Path):
    """Plot heatmap of consistency scores."""
    
    day_shift = consistency[consistency["shift"] == "day"]
    
    if len(day_shift) == 0:
        return
    
    pivot = day_shift.pivot(index="region", columns="season", values="consistency_pct")
    pivot = pivot[["winter", "spring", "summer", "fall"]]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    im = ax.imshow(pivot.values, cmap='RdYlGn', vmin=0, vmax=100)
    
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([s.capitalize() for s in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([REGIONS.get(r, {}).get("name", r) for r in pivot.index])
    
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.iloc[i, j]
            if pd.notna(val):
                ax.text(j, i, f"{val:.0f}%", ha='center', va='center', fontsize=11)
    
    ax.set_title("Consistency Score: How Often Does Best Hour = Modal Hour? (Day Shift)", fontsize=14)
    
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Consistency (%)", fontsize=11)
    
    plt.tight_layout()
    
    outpath = figures_dir / "04_consistency_heatmap.png"
    plt.savefig(outpath, dpi=FIGURE_DPI)
    plt.close()
    print(f"  Saved: {outpath.name}")


def generate_summary_table(results: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Generate summary table of scheduling results."""
    
    unit_label = get_unit_label(signal)
    
    summary_rows = []
    
    for region in results["region"].unique():
        for shift in results["shift"].unique():
            for duration in results["job_duration_hours"].unique():
                subset = results[(results["region"] == region) & 
                                (results["shift"] == shift) &
                                (results["job_duration_hours"] == duration)]
                
                if len(subset) == 0:
                    continue
                
                row = {
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "shift": shift,
                    "job_duration_hours": duration,
                    "signal": signal,
                    "unit": unit_label,
                    "n_days": len(subset),
                    "mean_baseline_value": subset["baseline_value"].mean(),
                    "mean_optimal_value": subset["optimal_value"].mean(),
                    "mean_savings_pct": subset["savings_vs_baseline_pct"].mean(),
                    "std_savings_pct": subset["savings_vs_baseline_pct"].std(),
                    "median_savings_pct": subset["savings_vs_baseline_pct"].median(),
                    "p10_savings_pct": subset["savings_vs_baseline_pct"].quantile(0.10),
                    "p90_savings_pct": subset["savings_vs_baseline_pct"].quantile(0.90),
                }
                
                if signal == "co2_moer" and subset["saved_co2_g"].notna().any():
                    row["mean_saved_co2_g"] = subset["saved_co2_g"].mean()
                
                summary_rows.append(row)
    
    return pd.DataFrame(summary_rows)


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
    print("SCHEDULING SIMULATION")
    print("=" * 60)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print("=" * 60)
    
    # Set up paths
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data
    df = load_data(run_dir)
    
    # Run simulation
    results = run_simulation(df, signal)
    
    # Check if we got any results
    if len(results) == 0:
        print("\nERROR: No valid simulations produced.")
        print("This usually means the date/shift filtering isn't matching any data.")
        print("\nDebug info:")
        print(f"  Data columns: {df.columns.tolist()}")
        print(f"  Date column type: {df['date'].dtype}")
        print(f"  Sample dates: {df['date'].head(3).tolist()}")
        print(f"  Regions in data: {df['region'].unique().tolist()}")
        sys.exit(1)
    
    # Add features
    results = add_result_features(results)
    
    # Save raw results
    results.to_parquet(outputs_dir / "scheduling_simulation_results.parquet", index=False)
    print(f"\nSaved: scheduling_simulation_results.parquet")
    
    # Generate plots
    print("\nGenerating figures...")
    plot_savings_comparison_all_regions(results, signal, figures_dir)
    
    regions_in_data = sorted(results["region"].unique())
    for region in regions_in_data:
        plot_savings_by_season(results, region, signal, figures_dir)
    
    # Consistency analysis
    print("\nCalculating consistency scores...")
    consistency = calculate_consistency_scores(results)
    consistency.to_csv(outputs_dir / "consistency_scores.csv", index=False)
    plot_consistency_heatmap(consistency, figures_dir)
    
    # Summary table
    summary = generate_summary_table(results, signal)
    summary.to_csv(outputs_dir / "scheduling_summary.csv", index=False)
    
    # Print key findings
    unit_label = get_unit_label(signal)
    print("\n" + "=" * 60)
    print("KEY FINDINGS (2hr job, Day Shift)")
    print("=" * 60)
    
    for region in regions_in_data:
        subset = summary[(summary["region"] == region) & 
                        (summary["shift"] == "day") &
                        (summary["job_duration_hours"] == 2.0)]
        if len(subset) > 0:
            row = subset.iloc[0]
            print(f"\n{row['region_name']}:")
            print(f"  Baseline: {row['mean_baseline_value']:.0f} {unit_label}")
            print(f"  Optimal:  {row['mean_optimal_value']:.0f} {unit_label}")
            print(f"  Savings: {row['mean_savings_pct']:.1f}% +/- {row['std_savings_pct']:.1f}%")
            if signal == "co2_moer" and "mean_saved_co2_g" in row:
                print(f"  CO2 saved per 2kWh job: {row['mean_saved_co2_g']:.0f}g")
    
    # Mark script as run
    mark_script_run(run_dir, "04_scheduling_simulation")
    
    print("\n" + "=" * 60)
    print("SCHEDULING SIMULATION COMPLETE")
    print(f"Figures saved to: {figures_dir}")
    print(f"Data saved to: {outputs_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
