"""
05_forecast_accuracy.py - Forecast Accuracy Analysis

Analyzes how well WattTime's day-ahead forecasts predict actual values.
Determines if day-ahead scheduling decisions are reliable.

Usage:
    1. Ensure you have both historical AND forecast data in library
    2. Create a run with DATA_TYPES = ["historical", "forecast"]
    3. Edit the CONFIG section below
    4. Run: python 05_forecast_accuracy.py

Output (in run folder):
    - figures/05_forecast_vs_actual_scatter.png
    - figures/05_mae_by_horizon.png
    - figures/05_scheduling_decision_accuracy.png
    - outputs/forecast_accuracy_by_horizon.csv
    - outputs/forecast_decision_accuracy.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pyarrow.parquet as pq
import json
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, RUNS_DIR,
    FIGURE_DPI, FIGURE_SIZE,
    REGION_COLORS,
    get_signal_metadata, get_unit_label
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"

# Max forecast horizon to analyze. WattTime provides up to 72h.
MAX_HORIZON_HOURS = 72.0

# Chunk size for reading the parquet file. Lower if you still hit memory issues.
CHUNK_SIZE = 2_000_000

# Target number of rows for analysis after sampling.
# 5M gives stable statistics — increasing beyond this rarely changes results.
TARGET_SAMPLE_ROWS = 5_000_000

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
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


def load_run_config(run_dir: Path) -> dict:
    with open(run_dir / "run_config.json", 'r') as f:
        return json.load(f)


def load_forecast_data_sampled(run_dir: Path) -> pd.DataFrame:
    """
    Read forecast parquet in chunks. For each chunk:
      1. Parse timestamps and compute horizon_hours
      2. Filter to 0 - MAX_HORIZON_HOURS
      3. Sample a proportional fraction so the final result is ~TARGET_SAMPLE_ROWS

    This keeps peak memory to roughly one chunk at a time.
    """
    print("Loading forecast data (chunked + sampled)...")

    forecast_path = run_dir / "processed" / "data_forecast.parquet"
    if not forecast_path.exists():
        print("  ERROR: No forecast data found.")
        return None

    pf = pq.ParquetFile(forecast_path)
    total_rows = pf.metadata.num_rows
    print(f"  Total rows in file: {total_rows:,}")

    # Sample fraction: what fraction of filtered rows do we need to hit TARGET_SAMPLE_ROWS?
    # We don't know the post-filter count yet, so estimate conservatively at 100% of file,
    # then recalculate after first chunk gives us a filter rate.
    estimated_filter_rate = 1.0  # will update after first chunk
    sample_fraction = min(1.0, TARGET_SAMPLE_ROWS / (total_rows * estimated_filter_rate))

    chunks = []
    rows_processed = 0
    rows_kept = 0
    first_chunk = True

    for batch in pf.iter_batches(batch_size=CHUNK_SIZE):
        chunk = batch.to_pandas()
        rows_processed += len(chunk)

        # Parse and compute horizon
        chunk["point_time"] = pd.to_datetime(chunk["point_time"], utc=True)
        chunk["generated_at"] = pd.to_datetime(chunk["generated_at"], utc=True)
        chunk["horizon_hours"] = (
            chunk["point_time"] - chunk["generated_at"]
        ).dt.total_seconds() / 3600

        # Filter to valid horizon window
        mask = (chunk["horizon_hours"] >= 0) & (chunk["horizon_hours"] <= MAX_HORIZON_HOURS)
        chunk = chunk[mask]

        if len(chunk) == 0:
            continue

        # After first chunk, estimate filter rate and update sample fraction
        if first_chunk:
            filter_rate = len(chunk) / CHUNK_SIZE
            estimated_filtered_total = total_rows * filter_rate
            sample_fraction = min(1.0, TARGET_SAMPLE_ROWS / estimated_filtered_total)
            print(f"  Filter rate: {filter_rate:.1%} → estimated {estimated_filtered_total:,.0f} filtered rows")
            print(f"  Sampling at {sample_fraction:.2%} per chunk to target {TARGET_SAMPLE_ROWS:,} rows")
            first_chunk = False

        # Sample this chunk
        if sample_fraction < 1.0:
            chunk = chunk.sample(frac=sample_fraction, random_state=42)

        if len(chunk) > 0:
            chunks.append(chunk)
            rows_kept += len(chunk)

        print(f"  Processed {rows_processed:,} / {total_rows:,} | Kept {rows_kept:,}", end="\r")

    print()

    if not chunks:
        print("  ERROR: No records survived filtering.")
        return None

    df = pd.concat(chunks, ignore_index=True)
    print(f"  Final sample: {len(df):,} forecast records")
    return df


def load_actual_data(run_dir: Path) -> pd.DataFrame:
    print("Loading actual data...")
    df = pd.read_parquet(run_dir / "processed" / "data_5min.parquet")
    df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
    print(f"  Loaded {len(df):,} actual records")
    return df


def merge_forecast_actual(forecasts: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Merge sampled forecasts with actuals and compute error columns."""
    print("\nMerging forecast and actual data...")

    forecasts.rename(columns={"value": "forecast_value"}, inplace=True)

    merged = forecasts.merge(
        actuals[["point_time", "value", "region"]].rename(columns={"value": "actual_value"}),
        on=["point_time", "region"],
        how="inner"
    )

    print(f"  Merged records: {len(merged):,}")
    if len(merged) == 0:
        return merged

    print(f"  Horizon range: {merged['horizon_hours'].min():.1f} to {merged['horizon_hours'].max():.1f} hours")

    merged["error"] = merged["forecast_value"] - merged["actual_value"]
    merged["abs_error"] = merged["error"].abs()
    merged["pct_error"] = 100 * merged["error"] / merged["actual_value"]
    merged["abs_pct_error"] = merged["pct_error"].abs()
    merged["squared_error"] = merged["error"] ** 2

    return merged


def analyze_accuracy_by_horizon(merged: pd.DataFrame) -> pd.DataFrame:
    """Accuracy metrics binned by forecast horizon."""

    horizon_bins   = [0, 1, 2, 4, 8, 12, 24, 48, 72, float('inf')]
    horizon_labels = ['0-1h', '1-2h', '2-4h', '4-8h', '8-12h', '12-24h', '24-48h', '48-72h', '72h+']

    merged["horizon_bin"] = pd.cut(
        merged["horizon_hours"], bins=horizon_bins, labels=horizon_labels
    )

    # Use pre-computed squared_error with mean() to avoid lambda + sort on huge arrays
    accuracy = merged.groupby("horizon_bin", observed=True).agg(
        mae        =("abs_error",     "mean"),
        mse        =("squared_error", "mean"),
        mape       =("abs_pct_error", "mean"),
        mean_error =("error",         "mean"),
        std_error  =("error",         "std"),
        n_samples  =("error",         "count"),
    ).reset_index()

    accuracy["rmse"] = np.sqrt(accuracy["mse"])
    accuracy.drop(columns=["mse"], inplace=True)

    return accuracy


def analyze_scheduling_decision_accuracy(merged: pd.DataFrame) -> pd.DataFrame:
    """
    For each day, check whether the day-ahead forecast (12-36h horizon)
    correctly identifies the best hour to run a job.
    """
    day_ahead = merged[
        (merged["horizon_hours"] >= 12) & (merged["horizon_hours"] <= 36)
    ].copy()

    if len(day_ahead) == 0:
        print("  WARNING: No data in 12-36h horizon window.")
        return None

    day_ahead["date"] = day_ahead["point_time"].dt.date
    day_ahead["hour"] = day_ahead["point_time"].dt.hour

    results = []
    for date, day_data in day_ahead.groupby("date"):
        if len(day_data) < 12:
            continue

        forecast_hourly = day_data.groupby("hour")["forecast_value"].mean()
        actual_hourly   = day_data.groupby("hour")["actual_value"].mean()

        forecast_best_hour = forecast_hourly.idxmin()
        actual_best_hour   = actual_hourly.idxmin()

        hours_off = abs(forecast_best_hour - actual_best_hour)
        if hours_off > 12:
            hours_off = 24 - hours_off

        actual_range = actual_hourly.max() - actual_hourly.min()
        forecast_chosen_value = actual_hourly.get(forecast_best_hour, actual_hourly.mean())

        pct_of_optimal = (
            100 * (actual_hourly.max() - forecast_chosen_value) / actual_range
            if actual_range > 0 else 100.0
        )

        results.append({
            "date":               date,
            "forecast_best_hour": forecast_best_hour,
            "actual_best_hour":   actual_best_hour,
            "hours_off":          hours_off,
            "exact_match":        forecast_best_hour == actual_best_hour,
            "within_2_hours":     hours_off <= 2,
            "pct_of_optimal":     min(pct_of_optimal, 100.0),
            "achieved_80pct":     pct_of_optimal >= 80,
        })

    return pd.DataFrame(results)


def plot_forecast_vs_actual_scatter(merged: pd.DataFrame, signal: str, figures_dir: Path):
    unit_label = get_unit_label(signal)

    sample = merged.sample(n=min(10_000, len(merged)), random_state=42)

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    scatter = ax.scatter(
        sample["actual_value"], sample["forecast_value"],
        alpha=0.1, s=5, c=sample["horizon_hours"], cmap="viridis"
    )

    lims = [
        min(sample["actual_value"].min(), sample["forecast_value"].min()),
        max(sample["actual_value"].max(), sample["forecast_value"].max()),
    ]
    ax.plot(lims, lims, 'r--', linewidth=2, label="Perfect Forecast")

    cbar = plt.colorbar(scatter, ax=ax)
    cbar.set_label("Horizon (hours)")

    r2 = sample["actual_value"].corr(sample["forecast_value"]) ** 2
    ax.annotate(f"R² = {r2:.3f}", xy=(0.05, 0.95), xycoords='axes fraction',
                fontsize=11, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    ax.set_xlabel(f"Actual ({unit_label})")
    ax.set_ylabel(f"Forecast ({unit_label})")
    ax.set_title("Forecast vs Actual")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(figures_dir / "05_forecast_vs_actual_scatter.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: 05_forecast_vs_actual_scatter.png")


def plot_mae_by_horizon(accuracy: pd.DataFrame, signal: str, figures_dir: Path):
    unit_label = get_unit_label(signal)

    # Drop any empty bins
    accuracy = accuracy[accuracy["n_samples"] > 0]

    fig, ax = plt.subplots(figsize=FIGURE_SIZE)
    x = range(len(accuracy))
    ax.bar(x, accuracy["mae"], color="#1f77b4", edgecolor='black')

    for i, (_, row) in enumerate(accuracy.iterrows()):
        ax.annotate(f"{row['mae']:.1f}", xy=(i, row['mae']),
                    ha='center', va='bottom', fontsize=9)

    ax.set_xlabel("Forecast Horizon")
    ax.set_ylabel(f"Mean Absolute Error ({unit_label})")
    ax.set_title("Forecast Accuracy by Horizon")
    ax.set_xticks(x)
    ax.set_xticklabels(accuracy["horizon_bin"], rotation=45, ha='right')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(figures_dir / "05_mae_by_horizon.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: 05_mae_by_horizon.png")


def plot_scheduling_decision_accuracy(decision_accuracy: pd.DataFrame, figures_dir: Path):
    if decision_accuracy is None or len(decision_accuracy) == 0:
        print("  No decision accuracy data to plot")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax1 = axes[0]
    hours_off_counts = decision_accuracy["hours_off"].value_counts().sort_index()
    ax1.bar(hours_off_counts.index, hours_off_counts.values, color="#1f77b4", edgecolor='black')
    ax1.set_xlabel("Hours Off from Optimal")
    ax1.set_ylabel("Number of Days")
    ax1.set_title("How Far Off is the Day-Ahead Best Hour Forecast?")
    ax1.grid(True, alpha=0.3, axis='y')

    exact_pct   = 100 * decision_accuracy["exact_match"].mean()
    within2_pct = 100 * decision_accuracy["within_2_hours"].mean()
    ax1.annotate(
        f"Exact match: {exact_pct:.0f}%\nWithin 2 hrs: {within2_pct:.0f}%",
        xy=(0.95, 0.95), xycoords='axes fraction', ha='right', va='top',
        fontsize=10, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8)
    )

    ax2 = axes[1]
    mean_pct = decision_accuracy["pct_of_optimal"].mean()
    ax2.hist(decision_accuracy["pct_of_optimal"], bins=20,
             color="#1f77b4", edgecolor='black', alpha=0.7)
    ax2.axvline(80, color='red', linestyle='--', linewidth=2, label='80% threshold')
    ax2.axvline(mean_pct, color='green', linestyle='-', linewidth=2,
                label=f'Mean: {mean_pct:.0f}%')
    ax2.set_xlabel("% of Optimal Savings Achieved")
    ax2.set_ylabel("Number of Days")
    ax2.set_title("Savings Achieved Using Day-Ahead Forecast")
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(figures_dir / "05_scheduling_decision_accuracy.png", dpi=FIGURE_DPI)
    plt.close()
    print("  Saved: 05_scheduling_decision_accuracy.png")


def mark_script_run(run_dir: Path, script_name: str):
    config_path = run_dir / "run_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    config["scripts_run"].append({
        "script":    script_name,
        "timestamp": datetime.now().isoformat(),
    })
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2, default=str)


def main():
    run_dir = get_run_dir()
    config  = load_run_config(run_dir)
    signal  = config["signal"]

    print("=" * 60)
    print("FORECAST ACCURACY ANALYSIS")
    print("=" * 60)
    print(f"Run:          {run_dir.name}")
    print(f"Signal:       {signal}")
    print(f"Max horizon:  {MAX_HORIZON_HOURS:.0f}h")
    print(f"Target rows:  {TARGET_SAMPLE_ROWS:,}")
    print("=" * 60)

    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"

    forecasts = load_forecast_data_sampled(run_dir)
    if forecasts is None:
        sys.exit(1)

    actuals = load_actual_data(run_dir)

    merged = merge_forecast_actual(forecasts, actuals)
    if len(merged) == 0:
        print("\nNo matching forecast/actual data. Check that regions and time ranges overlap.")
        sys.exit(1)

    print("\nCalculating accuracy metrics...")
    accuracy          = analyze_accuracy_by_horizon(merged)
    decision_accuracy = analyze_scheduling_decision_accuracy(merged)

    print("\nGenerating figures...")
    plot_forecast_vs_actual_scatter(merged, signal, figures_dir)
    plot_mae_by_horizon(accuracy, signal, figures_dir)
    if decision_accuracy is not None:
        plot_scheduling_decision_accuracy(decision_accuracy, figures_dir)

    accuracy.to_csv(outputs_dir / "forecast_accuracy_by_horizon.csv", index=False)
    if decision_accuracy is not None:
        decision_accuracy.to_csv(outputs_dir / "forecast_decision_accuracy.csv", index=False)

    print("\n" + "=" * 60)
    print("FORECAST ACCURACY SUMMARY")
    print("=" * 60)
    print("\nAccuracy by Horizon:")
    print(accuracy[["horizon_bin", "mae", "rmse", "mape", "n_samples"]].to_string(index=False))

    if decision_accuracy is not None and len(decision_accuracy) > 0:
        print("\nDay-Ahead Scheduling Decision Accuracy:")
        print(f"  Exact best-hour match:        {100*decision_accuracy['exact_match'].mean():.1f}%")
        print(f"  Within 2 hours:               {100*decision_accuracy['within_2_hours'].mean():.1f}%")
        print(f"  Days achieving >=80% optimal: {100*decision_accuracy['achieved_80pct'].mean():.1f}%")

    mark_script_run(run_dir, "05_forecast_accuracy")

    print("\n" + "=" * 60)
    print("FORECAST ACCURACY ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()