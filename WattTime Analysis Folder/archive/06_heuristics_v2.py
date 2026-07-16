"""
06_heuristics.py - Heuristics Synthesis

Synthesizes all analysis results into actionable scheduling heuristics
for manufacturing operations.

Usage:
    1. Run scripts 02-04 first
    2. Edit the CONFIG section below
    3. Run: python 06_heuristics.py

Output (in run folder):
    - outputs/heuristics_table.csv
    - outputs/heuristics_report.md
    - figures/06_heuristics_summary.png
    - figures/06_seasonal_recommendations.png
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
    REGIONS, SEASONS, SHIFTS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS, SEASON_COLORS,
    REFERENCE_JOB_KWH,
    get_signal_metadata, get_unit_label
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run folder to analyze (must have run 03 and 04 first)
# Use the folder name from runs/, e.g., "2025-01-28_moer_temporal"
# Or set to None to use the most recent run
RUN_FOLDER = "2026-01-30__ALL_test_peep_this"  # Will auto-detect most recent run

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================


def get_run_dir() -> Path:
    """Get the run directory."""
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


def load_run_config(run_dir: Path) -> dict:
    """Load run configuration."""
    config_path = run_dir / "run_config.json"
    with open(config_path, 'r') as f:
        return json.load(f)


def load_results(run_dir: Path) -> dict:
    """Load all analysis results."""
    print("Loading analysis results...")
    
    results = {}
    outputs_dir = run_dir / "outputs"
    processed_dir = run_dir / "processed"
    
    # Scheduling simulation results
    sched_path = outputs_dir / "scheduling_simulation_results.parquet"
    if sched_path.exists():
        results["scheduling"] = pd.read_parquet(sched_path)
        print(f"  Scheduling results: {len(results['scheduling']):,} records")
    else:
        print("  WARNING: No scheduling results found. Run 04_scheduling_simulation.py first.")
    
    # Consistency scores
    consistency_path = outputs_dir / "consistency_scores.csv"
    if consistency_path.exists():
        results["consistency"] = pd.read_csv(consistency_path)
        print(f"  Consistency scores: {len(results['consistency']):,} records")
    
    # Temporal pattern summary
    temporal_path = outputs_dir / "temporal_pattern_summary.csv"
    if temporal_path.exists():
        results["temporal"] = pd.read_csv(temporal_path)
        print(f"  Temporal patterns: {len(results['temporal']):,} records")
    
    # 5-min data
    data_path = processed_dir / "data_5min.parquet"
    if data_path.exists():
        results["data_5min"] = pd.read_parquet(data_path)
        print(f"  5-min data: {len(results['data_5min']):,} records")
    
    return results


def calculate_best_windows(results: dict, signal: str) -> pd.DataFrame:
    """For each region/season/shift, determine the recommended scheduling window."""
    print("\nCalculating best scheduling windows...")
    
    if "scheduling" not in results:
        return None
    
    scheduling = results["scheduling"]
    data = scheduling[scheduling["job_duration_hours"] == 2.0].copy()
    
    heuristics = []
    
    for region in data["region"].unique():
        for season in data["season"].unique():
            for shift in data["shift"].unique():
                subset = data[(data["region"] == region) & 
                              (data["season"] == season) &
                              (data["shift"] == shift)]
                
                if len(subset) < 30:
                    continue
                
                modal_hour = subset["optimal_start_hour"].mode()
                if len(modal_hour) == 0:
                    continue
                modal_hour = int(modal_hour.iloc[0])
                
                avg_savings = subset["savings_vs_baseline_pct"].mean()
                std_savings = subset["savings_vs_baseline_pct"].std()
                median_savings = subset["savings_vs_baseline_pct"].median()
                
                consistency = 100 * (subset["optimal_start_hour"] == modal_hour).mean()
                within_2hr = 100 * ((subset["optimal_start_hour"] >= modal_hour - 1) & 
                                    (subset["optimal_start_hour"] <= modal_hour + 1)).mean()
                
                # CO2 savings (only for MOER)
                if signal == "co2_moer" and "saved_co2_g" in subset.columns:
                    avg_co2_saved = subset["saved_co2_g"].mean()
                else:
                    avg_co2_saved = None
                
                heuristics.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "shift": shift,
                    "recommended_start_hour": modal_hour,
                    "recommended_window": f"{modal_hour:02d}:00-{(modal_hour+2)%24:02d}:00",
                    "avg_savings_pct": round(avg_savings, 1),
                    "std_savings_pct": round(std_savings, 1),
                    "median_savings_pct": round(median_savings, 1),
                    "consistency_pct": round(consistency, 0),
                    "within_2hr_pct": round(within_2hr, 0),
                    "avg_co2_saved_g": round(avg_co2_saved, 0) if avg_co2_saved else None,
                    "n_days": len(subset),
                })
    
    heuristics_df = pd.DataFrame(heuristics)
    print(f"  Generated {len(heuristics_df)} heuristics")
    
    return heuristics_df


def calculate_simple_rules(results: dict, signal: str) -> dict:
    """Generate simplified rules of thumb for each region."""
    print("\nGenerating simple rules...")
    
    if "data_5min" not in results:
        return {}
    
    df = results["data_5min"]
    rules = {}
    
    for region in df["region"].unique():
        region_data = df[df["region"] == region]
        
        hourly_avg = region_data.groupby("hour")["value"].mean()
        best_hour = int(hourly_avg.idxmin())
        worst_hour = int(hourly_avg.idxmax())
        best_value = hourly_avg.min()
        worst_value = hourly_avg.max()
        potential_reduction = 100 * (worst_value - best_value) / worst_value
        
        # Best 3-hour window
        best_windows = []
        for start in range(0, 24):
            hours = [(start + i) % 24 for i in range(3)]
            avg = hourly_avg[hours].mean()
            best_windows.append((start, avg))
        best_window_start = min(best_windows, key=lambda x: x[1])[0]
        
        # Seasonal variation
        seasonal_best = {}
        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]
            if len(season_data) > 0:
                season_hourly = season_data.groupby("hour")["value"].mean()
                seasonal_best[season] = int(season_hourly.idxmin())
        
        # Weekday vs weekend
        weekday_avg = region_data[~region_data["is_weekend"]]["value"].mean()
        weekend_avg = region_data[region_data["is_weekend"]]["value"].mean()
        weekend_better = weekend_avg < weekday_avg
        
        rules[region] = {
            "region_name": REGIONS.get(region, {}).get("name", region),
            "overall_best_hour": best_hour,
            "overall_worst_hour": worst_hour,
            "potential_reduction_pct": round(potential_reduction, 1),
            "recommended_3hr_window": f"{best_window_start:02d}:00-{(best_window_start+3)%24:02d}:00",
            "seasonal_best_hours": seasonal_best,
            "weekend_better": weekend_better,
            "weekend_vs_weekday_diff": round(weekday_avg - weekend_avg, 0),
        }
    
    return rules


def generate_report(heuristics: pd.DataFrame, rules: dict, signal: str) -> str:
    """Generate markdown report with findings."""
    
    signal_meta = get_signal_metadata(signal)
    unit_label = get_unit_label(signal)
    
    lines = [
        f"# Carbon-Aware Scheduling Heuristics",
        f"",
        f"**Signal:** {signal_meta['name']} ({unit_label})",
        f"",
        f"## Executive Summary",
        f"",
        f"This report provides actionable scheduling heuristics derived from historical data analysis.",
        f"",
        f"## Key Findings by Region",
        f"",
    ]
    
    for region, rule in rules.items():
        lines.append(f"### {rule['region_name']}")
        lines.append(f"")
        lines.append(f"- **Best time:** {rule['recommended_3hr_window']} ({rule['potential_reduction_pct']:.0f}% potential reduction)")
        lines.append(f"- **Cleanest hour:** {rule['overall_best_hour']:02d}:00")
        lines.append(f"- **Avoid:** {rule['overall_worst_hour']:02d}:00 (highest values)")
        
        if rule['weekend_better']:
            lines.append(f"- **Weekend bonus:** Weekends are cleaner by ~{abs(rule['weekend_vs_weekday_diff']):.0f} {unit_label}")
        
        if rule['seasonal_best_hours']:
            lines.append(f"- **Seasonal adjustment:**")
            for season, hour in rule['seasonal_best_hours'].items():
                lines.append(f"  - {season.capitalize()}: Best around {hour:02d}:00")
        
        lines.append(f"")
    
    lines.extend([
        f"## Methodology",
        f"",
        f"- **Signal:** {signal_meta['name']}",
        f"- **Resolution:** 5-minute intervals",
        f"- **Job duration:** 2-hour reference job",
        f"- **Baseline:** Average value across shift (uniform scheduling)",
        f"- **Optimal:** Best contiguous 2-hour window within shift",
        f"- **Savings:** (Baseline - Optimal) / Baseline x 100%",
        f"",
        f"## Limitations",
        f"",
        f"1. Values vary daily; heuristics represent averages",
        f"2. Real-time monitoring would outperform static rules",
        f"3. Grid mix is evolving; patterns may shift over time",
        f"",
    ])
    
    return "\n".join(lines)


def plot_heuristics_summary(heuristics: pd.DataFrame, rules: dict, signal: str, figures_dir: Path):
    """Create summary visualization."""
    
    if heuristics is None or len(heuristics) == 0:
        print("  No heuristics data for plotting")
        return
    
    unit_label = get_unit_label(signal)
    day_shift = heuristics[heuristics["shift"] == "day"]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Left: Average savings by region
    ax1 = axes[0]
    region_avg = day_shift.groupby("region")["avg_savings_pct"].mean().sort_values(ascending=True)
    colors = [REGION_COLORS.get(r, "#333333") for r in region_avg.index]
    
    bars = ax1.barh(range(len(region_avg)), region_avg.values, color=colors, edgecolor='black')
    ax1.set_yticks(range(len(region_avg)))
    ax1.set_yticklabels([REGIONS.get(r, {}).get("name", r) for r in region_avg.index])
    ax1.set_xlabel("Average Savings (%)")
    ax1.set_title("Scheduling Savings Potential by Region\n(Day Shift, 2hr Job)")
    ax1.grid(True, alpha=0.3, axis='x')
    
    for bar, val in zip(bars, region_avg.values):
        ax1.annotate(f'{val:.1f}%', xy=(val + 0.2, bar.get_y() + bar.get_height()/2),
                    va='center', fontsize=10)
    
    # Right: Best hours by region
    ax2 = axes[1]
    best_hours = [rules[r]["overall_best_hour"] for r in rules.keys()]
    region_names = [rules[r]["region_name"] for r in rules.keys()]
    colors = [REGION_COLORS.get(r, "#333333") for r in rules.keys()]
    
    ax2.barh(range(len(best_hours)), best_hours, color=colors, edgecolor='black')
    ax2.set_yticks(range(len(region_names)))
    ax2.set_yticklabels(region_names)
    ax2.set_xlabel("Best Hour (24hr)")
    ax2.set_title("Cleanest Hour of Day by Region")
    ax2.set_xlim(0, 24)
    ax2.set_xticks([0, 6, 12, 18, 24])
    ax2.set_xticklabels(["00:00", "06:00", "12:00", "18:00", "24:00"])
    ax2.grid(True, alpha=0.3, axis='x')
    
    for i, hour in enumerate(best_hours):
        ax2.annotate(f'{hour:02d}:00', xy=(hour + 0.5, i), va='center', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "06_heuristics_summary.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: 06_heuristics_summary.png")


def plot_seasonal_recommendations(heuristics: pd.DataFrame, signal: str, figures_dir: Path):
    """Plot seasonal variation in recommendations."""
    
    if heuristics is None or len(heuristics) == 0:
        return
    
    day_shift = heuristics[heuristics["shift"] == "day"]
    regions = sorted(day_shift["region"].unique())
    
    n_regions = min(len(regions), 5)
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()
    
    # Shared y-axis for fair comparison across regions
    all_savings = day_shift["avg_savings_pct"]
    shared_ylim = (0, all_savings.max() * 1.15)
    
    for i, region in enumerate(regions[:n_regions]):
        ax = axes[i]
        region_data = day_shift[day_shift["region"] == region]
        
        seasons = ["winter", "spring", "summer", "fall"]
        savings = []
        for s in seasons:
            s_data = region_data[region_data["season"] == s]
            if len(s_data) > 0:
                savings.append(s_data["avg_savings_pct"].values[0])
            else:
                savings.append(0)
        
        colors = [SEASON_COLORS[s] for s in seasons]
        ax.bar(range(len(seasons)), savings, color=colors, edgecolor='black')
        
        ax.set_xticks(range(len(seasons)))
        ax.set_xticklabels([s.capitalize() for s in seasons])
        ax.set_ylabel("Savings (%)")
        ax.set_title(REGIONS.get(region, {}).get("name", region))
        ax.set_ylim(shared_ylim)
        ax.grid(True, alpha=0.3, axis='y')
    
    # Hide unused subplots
    for i in range(n_regions, 6):
        axes[i].set_visible(False)
    
    fig.suptitle("Seasonal Variation in Scheduling Savings (Day Shift, 2hr Job)", fontsize=14)
    plt.tight_layout()
    plt.savefig(figures_dir / "06_seasonal_recommendations.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: 06_seasonal_recommendations.png")


def print_actionable_summary(rules: dict, signal: str):
    """Print actionable summary."""
    
    unit_label = get_unit_label(signal)
    
    print("\n" + "=" * 70)
    print("ACTIONABLE SCHEDULING HEURISTICS")
    print("=" * 70)
    
    for region, rule in rules.items():
        print(f"\n{'=' * 50}")
        print(f"{rule['region_name'].upper()}")
        print(f"{'=' * 50}")
        print(f"\n  SIMPLE RULE: Schedule jobs between {rule['recommended_3hr_window']}")
        print(f"     - Potential reduction: {rule['potential_reduction_pct']:.0f}%")
        print(f"     - Cleanest hour: {rule['overall_best_hour']:02d}:00")
        print(f"     - Avoid: {rule['overall_worst_hour']:02d}:00 (highest values)")
        
        if rule['weekend_better']:
            print(f"\n  WEEKEND BONUS: Weekends are cleaner by ~{abs(rule['weekend_vs_weekday_diff']):.0f} {unit_label}")
        
        if rule['seasonal_best_hours']:
            print(f"\n  SEASONAL ADJUSTMENT:")
            for season, hour in rule['seasonal_best_hours'].items():
                print(f"     - {season.capitalize()}: Best around {hour:02d}:00")
    
    print("\n" + "=" * 70)
    print("IMPLEMENTATION NOTES")
    print("=" * 70)
    print("""
  1. These are AVERAGE patterns - daily variation exists
  2. For maximum savings, use real-time WattTime API when possible
  3. Even simple scheduling shifts can reduce emissions 5-15%
  4. Combine with energy efficiency measures for compound impact
  5. Review quarterly as grid mix evolves
    """)


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
    run_dir = get_run_dir()
    config = load_run_config(run_dir)
    signal = config["signal"]
    
    print("=" * 60)
    print("HEURISTICS SYNTHESIS")
    print("=" * 60)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print("=" * 60)
    
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load results
    results = load_results(run_dir)
    
    if not results:
        print("\nNo analysis results found. Run scripts 03-04 first.")
        sys.exit(1)
    
    # Calculate heuristics
    heuristics = calculate_best_windows(results, signal)
    rules = calculate_simple_rules(results, signal)
    
    # Generate plots
    print("\nGenerating figures...")
    plot_heuristics_summary(heuristics, rules, signal, figures_dir)
    plot_seasonal_recommendations(heuristics, signal, figures_dir)
    
    # Save outputs
    if heuristics is not None:
        heuristics.to_csv(outputs_dir / "heuristics_table.csv", index=False)
        print(f"\nSaved: heuristics_table.csv")
    
    # Generate and save report (with explicit UTF-8 encoding)
    report = generate_report(heuristics, rules, signal)
    report_path = outputs_dir / "heuristics_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Saved: heuristics_report.md")
    
    # Print summary
    print_actionable_summary(rules, signal)
    
    # Mark script as run
    mark_script_run(run_dir, "06_heuristics")
    
    print("\n" + "=" * 60)
    print("HEURISTICS SYNTHESIS COMPLETE")
    print(f"Reports saved to: {outputs_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
