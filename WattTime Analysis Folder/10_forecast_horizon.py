"""
10_forecast_horizon.py - Forecast Reliability by Planning Horizon

Analyzes how forecast accuracy degrades with planning horizon to determine
when to trust forecasts vs fall back to heuristics. Provides practical
implementation guidance for system designers.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Ensure forecast data is available (collected via 01_data_collection.py)
    3. Edit the CONFIG section below
    4. Run: python 10_forecast_horizon.py

Analysis:
    1. Accuracy by Horizon
       - MAE/MAPE at various forecast horizons
       - Identify accuracy "cliff" where forecasts become unreliable
    2. Accuracy by Context
       - Season effects on forecast reliability
       - Time of day effects
       - Peak vs off-peak accuracy
    3. Decision Reliability
       - Probability of picking optimal hour
       - Probability of achieving >=X% of theoretical savings
    4. Implementation Thresholds
       - When to use forecast vs heuristic

Output (in run folder):
    - figures/10_*.png
    - outputs/10_*.csv
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import seaborn as sns
import json
import gc
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

# Forecast horizons to analyze (hours ahead)
HORIZONS = [1, 2, 4, 6, 8, 12, 18, 24, 36, 48, 72]

# Decision reliability thresholds
SAVINGS_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]  # Fraction of theoretical maximum
HOUR_TOLERANCE = [0, 1, 2, 3]  # Hours within optimal to count as "good" decision

# Peak hours definition (for peak-specific analysis)
PEAK_HOURS = list(range(16, 21))  # 4pm - 8pm

# Scheduling window (for decision simulation)
SCHEDULING_WINDOW_HOURS = 8  # Look for best hour within this window

# Analysis toggles
RUN_ACCURACY_BY_HORIZON = True
RUN_ACCURACY_BY_CONTEXT = True
RUN_DECISION_RELIABILITY = True
RUN_THRESHOLD_RECOMMENDATIONS = True

# Memory management: max forecast-actual pairs to process at once
# Reduce this if you hit memory errors
MAX_MERGE_ROWS = 5_000_000

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


def load_data(run_dir: Path) -> Tuple[pd.DataFrame, Optional[Path]]:
    """Load hourly actuals. Returns forecast *path* (not DataFrame) to avoid OOM."""
    print("Loading processed data...")
    
    processed_dir = run_dir / "processed"
    
    df_hourly = pd.read_parquet(processed_dir / "data_hourly.parquet")
    df_hourly["point_time"] = pd.to_datetime(
        df_hourly[["year", "month", "day", "hour"]].assign(minute=0, second=0)
    )
    
    print(f"  Hourly actuals: {len(df_hourly):,} records")
    
    forecast_path = processed_dir / "data_forecast.parquet"
    if not forecast_path.exists():
        print("  WARNING: No forecast data found!")
        print("  This module requires forecast data from 01_data_collection.py")
        return df_hourly, None
    
    # Peek at row count without loading into memory
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(forecast_path)
    n_rows = pf.metadata.num_rows
    print(f"  Forecast data: {n_rows:,} records (will process per-region)")
    
    return df_hourly, forecast_path


def _get_forecast_regions(forecast_path: Path) -> list:
    """Discover unique regions from the forecast parquet without reading all rows."""
    import pyarrow.parquet as pq
    import pyarrow.compute as pc
    
    pf = pq.ParquetFile(forecast_path)
    
    # Read region column from sampled row groups, using pyarrow unique()
    # to avoid materializing millions of Python strings
    regions = set()
    n_groups = pf.metadata.num_row_groups
    sample_indices = list(range(0, n_groups, max(1, n_groups // 10)))[:10]
    
    for i in sample_indices:
        rg = pf.read_row_group(i, columns=["region"])
        uniques = pc.unique(rg.column("region")).to_pylist()
        regions.update(uniques)
    
    result = sorted(regions)
    print(f"  Discovered {len(result)} regions from {len(sample_indices)} row groups: {result}")
    return result


def _load_forecast_region(forecast_path: Path, region: str,
                          needed_cols: list = None,
                          time_range: Tuple[pd.Timestamp, pd.Timestamp] = None) -> pd.DataFrame:
    """
    Load forecast data for a single region using pyarrow predicate pushdown.
    
    Args:
        forecast_path: Path to the parquet file
        region: Region string to filter on
        needed_cols: Only read these columns (massive memory savings)
        time_range: (min_time, max_time) tuple - drop rows outside this range
                    before returning to pandas
    """
    import pyarrow.parquet as pq
    import pyarrow.compute as pc
    
    # Build pyarrow filter predicates
    filters = [("region", "=", region)]
    
    try:
        table = pq.read_table(forecast_path, columns=needed_cols, filters=filters)
    except Exception as e:
        # If predicate pushdown fails, do NOT load everything - that's 408M rows.
        # Instead, explain the problem and suggest re-saving the parquet.
        print(f"    ERROR: Pyarrow filter failed for region '{region}': {e}")
        print(f"    Your parquet file may not support predicate pushdown.")
        print(f"    Fix: re-save with: df.to_parquet(path, engine='pyarrow', index=False)")
        print(f"    Or partition: df.to_parquet(dir, engine='pyarrow', partition_cols=['region'])")
        raise RuntimeError(f"Cannot filter forecast parquet by region. See above.") from e
    
    # Apply time range filter in pyarrow (before converting to pandas)
    if time_range is not None and "point_time" in table.column_names:
        min_t, max_t = time_range
        # Allow 72h buffer before min_t for horizon calculation
        buffer_min = min_t - pd.Timedelta(hours=72)
        
        pt_col = table.column("point_time")
        mask = pc.and_(
            pc.greater_equal(pt_col, buffer_min),
            pc.less_equal(pt_col, max_t)
        )
        pre_filter = len(table)
        table = table.filter(mask)
        post_filter = len(table)
        if pre_filter != post_filter:
            print(f"    Time-range filter: {pre_filter:,} -> {post_filter:,}")
    
    df = table.to_pandas()
    del table
    
    return df


def prepare_forecast_actuals(df_hourly: pd.DataFrame, forecast_path: Path) -> pd.DataFrame:
    """
    Merge forecast data with actuals and calculate horizon.
    
    Processes ONE REGION AT A TIME to avoid loading all 400M+ forecast rows.
    
    Optimizations vs naive approach:
    - Column selection: only reads needed columns from parquet (~4 vs all)
    - Time-range pre-filter: drops forecasts outside actuals time window in pyarrow
    - Hash-based dedup: groupby().last() instead of sort+drop_duplicates (O(n) vs O(n log n))
    - Point-hour pre-filter: only keeps forecasts targeting hours that exist in actuals
    - Early horizon filter: drops rows before accumulating across regions
    - Float downcast: ~50% memory savings on numeric columns
    """
    print("\n  Preparing forecast-actual pairs...")
    
    # --- Prepare actuals (small dataset ~118K rows) ---
    df_hourly["point_time"] = pd.to_datetime(df_hourly["point_time"])
    df_hourly["point_hour"] = df_hourly["point_time"].dt.floor("H")
    
    actuals_hourly = df_hourly.groupby(["region", "point_hour"]).agg(
        actual_value=("value_mean", "mean"),
        season=("season", "first"),
        hour=("hour", "first"),
        day_of_week=("day_of_week", "first"),
        is_weekend=("is_weekend", "first"),
    ).reset_index()
    
    print(f"  Actuals aggregated: {len(actuals_hourly):,} hourly records")
    
    # Compute actuals time range (used to pre-filter forecasts)
    actuals_time_min = actuals_hourly["point_hour"].min()
    actuals_time_max = actuals_hourly["point_hour"].max()
    print(f"  Actuals time range: {actuals_time_min} to {actuals_time_max}")
    
    # Build per-region sets of valid point_hours for fast pre-filtering
    valid_hours_by_region = {}
    for region in actuals_hourly["region"].unique():
        valid_hours_by_region[region] = set(
            actuals_hourly.loc[actuals_hourly["region"] == region, "point_hour"]
        )
    
    # Only read the columns we actually need from the forecast parquet
    FORECAST_COLS = ["region", "point_time", "generated_at", "value"]
    
    # Discover regions
    regions = _get_forecast_regions(forecast_path)
    n_regions = len(regions)
    per_region_limit = MAX_MERGE_ROWS // max(n_regions, 1)
    print(f"  Regions to process: {regions}")
    print(f"  Per-region row limit: {per_region_limit:,}")
    
    chunks = []
    
    for region in regions:
        print(f"\n  --- Processing region: {region} ---")
        
        # 1. Load only this region's forecasts with column + time filtering
        fc_region = _load_forecast_region(
            forecast_path, region,
            needed_cols=FORECAST_COLS,
            time_range=(actuals_time_min, actuals_time_max),
        )
        print(f"    Loaded {len(fc_region):,} forecast rows ({fc_region.memory_usage(deep=True).sum() / 1e6:.1f} MB)")
        
        if len(fc_region) == 0:
            continue
        
        # 2. Prepare datetime columns and floor to hour
        fc_region["point_time"] = pd.to_datetime(fc_region["point_time"])
        fc_region["generated_at"] = pd.to_datetime(fc_region["generated_at"])
        fc_region["point_hour"] = fc_region["point_time"].dt.floor("H")
        
        # 3. Pre-filter: only keep forecasts targeting hours that exist in actuals
        #    This can be a huge reduction if forecast covers more hours than actuals
        if region in valid_hours_by_region:
            pre_pf = len(fc_region)
            fc_region = fc_region[fc_region["point_hour"].isin(valid_hours_by_region[region])]
            if pre_pf != len(fc_region):
                print(f"    Point-hour filter: {pre_pf:,} -> {len(fc_region):,}")
        
        if len(fc_region) == 0:
            continue
        
        # 4. Drop the original point_time (we only need point_hour from here)
        fc_region.drop(columns=["point_time"], inplace=True)
        
        # 5. Deduplicate: keep latest forecast per (point_hour, generation_hour)
        #    Using idxmax to find row with latest generated_at per group.
        #    This is true O(n) — no sort needed, no argsort array allocated.
        fc_region["gen_hour"] = fc_region["generated_at"].dt.floor("H")
        pre_dedup = len(fc_region)
        
        idx_keep = fc_region.groupby(["point_hour", "gen_hour"])["generated_at"].idxmax()
        fc_region = fc_region.loc[idx_keep]
        
        print(f"    Deduplicated: {pre_dedup:,} -> {len(fc_region):,}")
        fc_region.drop(columns=["gen_hour"], inplace=True)
        
        # 6. Add region column back (was consumed by the groupby or may be missing)
        fc_region["region"] = region
        
        # 7. Merge with actuals for this region
        act_region = actuals_hourly[actuals_hourly["region"] == region]
        chunk = fc_region.merge(act_region, on=["region", "point_hour"], how="inner")
        del fc_region
        gc.collect()
        
        print(f"    Merged: {len(chunk):,} forecast-actual pairs")
        
        if len(chunk) == 0:
            continue
        
        # 8. Calculate horizon and filter EARLY
        chunk["horizon_hours"] = (
            (chunk["point_hour"] - chunk["generated_at"]).dt.total_seconds() / 3600
        )
        pre_hz = len(chunk)
        chunk = chunk[(chunk["horizon_hours"] >= 0) & (chunk["horizon_hours"] <= 72)]
        print(f"    After horizon filter: {pre_hz:,} -> {len(chunk):,}")
        
        # 9. Sample down if still too large
        if len(chunk) > per_region_limit:
            print(f"    WARNING: Sampling {len(chunk):,} -> {per_region_limit:,}")
            chunk = chunk.sample(n=per_region_limit, random_state=42)
        
        # 10. Compute errors (vectorized)
        chunk["error"] = chunk["value"] - chunk["actual_value"]
        chunk["abs_error"] = chunk["error"].abs()
        nonzero_mask = chunk["actual_value"].abs() > 1e-6
        chunk["pct_error"] = np.where(
            nonzero_mask,
            100 * chunk["error"] / chunk["actual_value"],
            np.nan
        )
        chunk["abs_pct_error"] = chunk["pct_error"].abs()
        
        # 11. Strip columns not used by downstream analysis
        #     Keep only what analyze_* and decision functions actually reference
        keep_cols = [
            "region", "point_hour", "generated_at",
            "value", "actual_value",
            "season", "hour", "day_of_week", "is_weekend",
            "horizon_hours", "error", "abs_error", "pct_error", "abs_pct_error",
        ]
        drop_cols = [c for c in chunk.columns if c not in keep_cols]
        if drop_cols:
            chunk.drop(columns=drop_cols, inplace=True)
        
        # 12. Downcast floats before accumulating
        float_cols = chunk.select_dtypes(include=["float64"]).columns
        for col in float_cols:
            chunk[col] = pd.to_numeric(chunk[col], downcast="float")
        
        mem_mb = chunk.memory_usage(deep=True).sum() / 1e6
        print(f"    Chunk: {len(chunk):,} rows, {mem_mb:.1f} MB")
        
        chunks.append(chunk)
        del chunk
        gc.collect()
    
    if not chunks:
        print("\n  ERROR: No forecast-actual pairs found for any region")
        return pd.DataFrame()
    
    # Combine all region chunks
    merged = pd.concat(chunks, ignore_index=True)
    del chunks
    gc.collect()
    
    # Bin horizons
    merged["horizon_bin"] = pd.cut(
        merged["horizon_hours"],
        bins=[0, 2, 4, 8, 12, 24, 48, 72],
        labels=["0-2h", "2-4h", "4-8h", "8-12h", "12-24h", "24-48h", "48-72h"],
    )
    
    # Add peak hour flag
    merged["is_peak"] = merged["hour"].isin(PEAK_HOURS)
    
    print(f"\n  Final merged dataset: {len(merged):,} forecast-actual pairs")
    print(f"  Memory usage: {merged.memory_usage(deep=True).sum() / 1e6:.1f} MB")
    
    return merged


# =============================================================================
# SECTION 1: ACCURACY BY HORIZON
# =============================================================================

def analyze_accuracy_by_horizon(merged: pd.DataFrame) -> pd.DataFrame:
    """Calculate MAE and MAPE at each forecast horizon."""
    print("\n  1A. Analyzing accuracy by horizon...")
    
    results = []
    
    for region in merged["region"].unique():
        region_data = merged[merged["region"] == region]
        
        for horizon in HORIZONS:
            horizon_data = region_data[
                (region_data["horizon_hours"] >= horizon - 0.5) &
                (region_data["horizon_hours"] < horizon + 0.5)
            ]
            
            if len(horizon_data) < 10:
                continue
            
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "horizon_hours": horizon,
                "n_samples": len(horizon_data),
                "mae": horizon_data["abs_error"].mean(),
                "mape": horizon_data["abs_pct_error"].mean(),
                "rmse": np.sqrt((horizon_data["error"] ** 2).mean()),
                "bias": horizon_data["error"].mean(),
                "correlation": horizon_data["value"].corr(horizon_data["actual_value"]),
                "mean_forecast": horizon_data["value"].mean(),
                "mean_actual": horizon_data["actual_value"].mean(),
            })
    
    return pd.DataFrame(results)


def identify_accuracy_cliff(accuracy_df: pd.DataFrame) -> pd.DataFrame:
    """Identify where forecast accuracy degrades significantly."""
    print("\n  1B. Identifying accuracy cliffs...")
    
    results = []
    
    for region in accuracy_df["region"].unique():
        region_data = accuracy_df[accuracy_df["region"] == region].sort_values("horizon_hours")
        
        if len(region_data) < 3:
            continue
        
        baseline_mape = region_data[region_data["horizon_hours"] == 1]["mape"].values
        if len(baseline_mape) == 0:
            baseline_mape = region_data["mape"].iloc[0]
        else:
            baseline_mape = baseline_mape[0]
        
        cliff_horizon = None
        for _, row in region_data.iterrows():
            if row["mape"] > baseline_mape * 1.2:
                cliff_horizon = row["horizon_hours"]
                break
        
        corr_drop_horizon = None
        for _, row in region_data.iterrows():
            if row["correlation"] < 0.9:
                corr_drop_horizon = row["horizon_hours"]
                break
        
        results.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "baseline_mape_1h": baseline_mape,
            "mape_cliff_horizon": cliff_horizon,
            "correlation_drop_horizon": corr_drop_horizon,
            "recommended_max_horizon": min(
                cliff_horizon or 72,
                corr_drop_horizon or 72
            ),
        })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 2: ACCURACY BY CONTEXT
# =============================================================================

def analyze_accuracy_by_season(merged: pd.DataFrame) -> pd.DataFrame:
    """Analyze how forecast accuracy varies by season."""
    print("\n  2A. Analyzing accuracy by season...")
    
    results = []
    target_horizons = [4, 12, 24]
    
    for region in merged["region"].unique():
        region_data = merged[merged["region"] == region]
        
        for season in ["winter", "spring", "summer", "fall"]:
            season_data = region_data[region_data["season"] == season]
            
            if len(season_data) < 100:
                continue
            
            for horizon in target_horizons:
                horizon_data = season_data[
                    (season_data["horizon_hours"] >= horizon - 1) &
                    (season_data["horizon_hours"] < horizon + 1)
                ]
                
                if len(horizon_data) < 10:
                    continue
                
                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "season": season,
                    "horizon_hours": horizon,
                    "n_samples": len(horizon_data),
                    "mae": horizon_data["abs_error"].mean(),
                    "mape": horizon_data["abs_pct_error"].mean(),
                    "correlation": horizon_data["value"].corr(horizon_data["actual_value"]),
                })
    
    return pd.DataFrame(results)


def analyze_accuracy_by_time_of_day(merged: pd.DataFrame) -> pd.DataFrame:
    """Analyze how forecast accuracy varies by time of day."""
    print("\n  2B. Analyzing accuracy by time of day...")
    
    results = []
    target_horizons = [4, 12, 24]
    
    for region in merged["region"].unique():
        region_data = merged[merged["region"] == region]
        
        for hour in range(24):
            hour_data = region_data[region_data["hour"] == hour]
            
            if len(hour_data) < 50:
                continue
            
            for horizon in target_horizons:
                horizon_data = hour_data[
                    (hour_data["horizon_hours"] >= horizon - 1) &
                    (hour_data["horizon_hours"] < horizon + 1)
                ]
                
                if len(horizon_data) < 10:
                    continue
                
                results.append({
                    "region": region,
                    "region_name": REGIONS.get(region, {}).get("name", region),
                    "target_hour": hour,
                    "horizon_hours": horizon,
                    "n_samples": len(horizon_data),
                    "mae": horizon_data["abs_error"].mean(),
                    "mape": horizon_data["abs_pct_error"].mean(),
                    "is_peak": hour in PEAK_HOURS,
                })
    
    return pd.DataFrame(results)


def analyze_peak_vs_offpeak(merged: pd.DataFrame) -> pd.DataFrame:
    """Compare forecast accuracy during peak vs off-peak hours."""
    print("\n  2C. Comparing peak vs off-peak accuracy...")
    
    results = []
    
    for region in merged["region"].unique():
        region_data = merged[merged["region"] == region]
        
        for horizon in [4, 12, 24, 48]:
            horizon_data = region_data[
                (region_data["horizon_hours"] >= horizon - 1) &
                (region_data["horizon_hours"] < horizon + 1)
            ]
            
            if len(horizon_data) < 50:
                continue
            
            peak_data = horizon_data[horizon_data["is_peak"]]
            offpeak_data = horizon_data[~horizon_data["is_peak"]]
            
            if len(peak_data) < 10 or len(offpeak_data) < 10:
                continue
            
            offpeak_mae = offpeak_data["abs_error"].mean()
            peak_mae = peak_data["abs_error"].mean()
            
            results.append({
                "region": region,
                "region_name": REGIONS.get(region, {}).get("name", region),
                "horizon_hours": horizon,
                "peak_mae": peak_mae,
                "peak_mape": peak_data["abs_pct_error"].mean(),
                "offpeak_mae": offpeak_mae,
                "offpeak_mape": offpeak_data["abs_pct_error"].mean(),
                "peak_vs_offpeak_ratio": peak_mae / offpeak_mae if offpeak_mae > 0 else np.nan,
                "peak_harder_to_forecast": peak_mae > offpeak_mae,
            })
    
    return pd.DataFrame(results)


# =============================================================================
# SECTION 3: DECISION RELIABILITY (vectorized - replaces row-by-row loop)
# =============================================================================

def analyze_decision_reliability(merged: pd.DataFrame, df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Analyze: if you use the forecast to pick the best hour, how often do you get it right?
    
    Fully vectorized using groupby + idxmin instead of iterating row-by-row.
    This is the main performance fix - the original looped over every unique
    generated_at timestamp and appended dicts, which is O(n) slow and O(n) memory.
    """
    print("\n  3A. Analyzing decision reliability...")
    
    # Filter to scheduling window
    window_data = merged[
        (merged["horizon_hours"] >= 0) &
        (merged["horizon_hours"] <= SCHEDULING_WINDOW_HOURS)
    ].copy()
    
    if len(window_data) == 0:
        print("    No data in scheduling window")
        return pd.DataFrame()
    
    # Group key: one scheduling decision = (region, forecast generation hour)
    window_data["gen_hour"] = window_data["generated_at"].dt.floor("H")
    group_cols = ["region", "gen_hour"]
    
    # Filter to groups with enough hours to choose from
    group_sizes = window_data.groupby(group_cols).size()
    valid_groups = group_sizes[group_sizes >= 4].reset_index()[group_cols]
    window_data = window_data.merge(valid_groups, on=group_cols, how="inner")
    
    n_decisions = len(valid_groups)
    print(f"    Valid scheduling decisions: {n_decisions:,}")
    
    if n_decisions == 0:
        return pd.DataFrame()
    
    # --- Vectorized decision analysis ---
    # For each group, find the row with min forecast value and min actual value
    idx_forecast_best = window_data.groupby(group_cols)["value"].idxmin()
    idx_actual_best = window_data.groupby(group_cols)["actual_value"].idxmin()
    
    # Extract the rows we picked via forecast
    forecast_picks = window_data.loc[idx_forecast_best,
        group_cols + ["point_hour", "actual_value"]
    ].rename(columns={
        "point_hour": "forecast_pick_hour",
        "actual_value": "forecast_pick_actual",
    }).set_index(group_cols)
    
    # Extract the actual-best rows
    actual_bests = window_data.loc[idx_actual_best,
        group_cols + ["point_hour", "actual_value"]
    ].rename(columns={
        "point_hour": "actual_best_hour",
        "actual_value": "actual_best_value",
    }).set_index(group_cols)
    
    # Group mean actual (baseline for savings calculation)
    baselines = window_data.groupby(group_cols)["actual_value"].mean().rename("baseline")
    
    # Join everything together
    decisions = forecast_picks.join(actual_bests).join(baselines).reset_index()
    
    # Vectorized metric calculation
    decisions["hours_off"] = (
        (decisions["forecast_pick_hour"] - decisions["actual_best_hour"])
        .dt.total_seconds().abs() / 3600
    )
    
    decisions["theoretical_savings_pct"] = np.where(
        decisions["baseline"] > 0,
        100 * (decisions["baseline"] - decisions["actual_best_value"]) / decisions["baseline"],
        0
    )
    
    decisions["achieved_savings_pct"] = np.where(
        decisions["baseline"] > 0,
        100 * (decisions["baseline"] - decisions["forecast_pick_actual"]) / decisions["baseline"],
        0
    )
    
    decisions["capture_rate"] = np.where(
        decisions["theoretical_savings_pct"] > 0,
        decisions["achieved_savings_pct"] / decisions["theoretical_savings_pct"],
        1.0
    )
    decisions["capture_rate"] = decisions["capture_rate"].clip(0, 1)
    
    decisions["picked_optimal"] = decisions["hours_off"] == 0
    decisions["within_1_hour"] = decisions["hours_off"] <= 1
    decisions["within_2_hours"] = decisions["hours_off"] <= 2
    decisions["achieved_80pct"] = decisions["capture_rate"] >= 0.8
    decisions["achieved_90pct"] = decisions["capture_rate"] >= 0.9
    decisions["horizon_bucket"] = f"{SCHEDULING_WINDOW_HOURS}h"
    
    # Rename gen_hour for output clarity
    decisions.rename(columns={"gen_hour": "forecast_time"}, inplace=True)
    
    print(f"    Computed {len(decisions):,} decision outcomes")
    
    return decisions


def summarize_decision_reliability(decision_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize decision reliability by region and horizon."""
    print("\n  3B. Summarizing decision reliability...")
    
    if len(decision_df) == 0:
        return pd.DataFrame()
    
    summary = decision_df.groupby(["region", "horizon_bucket"]).agg(
        pct_optimal=("picked_optimal", "mean"),
        pct_within_1h=("within_1_hour", "mean"),
        pct_within_2h=("within_2_hours", "mean"),
        pct_achieved_80=("achieved_80pct", "mean"),
        pct_achieved_90=("achieved_90pct", "mean"),
        mean_capture_rate=("capture_rate", "mean"),
        std_capture_rate=("capture_rate", "std"),
        mean_hours_off=("hours_off", "mean"),
        median_hours_off=("hours_off", "median"),
        n_decisions=("picked_optimal", "count"),
    ).reset_index()
    
    # Convert to percentages
    for col in ["pct_optimal", "pct_within_1h", "pct_within_2h", "pct_achieved_80", "pct_achieved_90"]:
        summary[col] = 100 * summary[col]
    
    summary["region_name"] = summary["region"].map(
        lambda r: REGIONS.get(r, {}).get("name", r)
    )
    
    return summary


# =============================================================================
# SECTION 4: THRESHOLD RECOMMENDATIONS
# =============================================================================

def generate_threshold_recommendations(accuracy_df: pd.DataFrame, cliff_df: pd.DataFrame,
                                       reliability_summary: pd.DataFrame) -> pd.DataFrame:
    """Generate practical recommendations for when to use forecasts vs heuristics."""
    print("\n  4A. Generating threshold recommendations...")
    
    recommendations = []
    
    for region in accuracy_df["region"].unique():
        region_accuracy = accuracy_df[accuracy_df["region"] == region]
        region_cliff = cliff_df[cliff_df["region"] == region]
        
        if len(region_cliff) == 0:
            continue
        
        cliff_horizon = region_cliff["recommended_max_horizon"].values[0]
        
        good_accuracy = region_accuracy[region_accuracy["mape"] < 10]
        good_horizon = good_accuracy["horizon_hours"].max() if len(good_accuracy) > 0 else 0
        
        acceptable_accuracy = region_accuracy[region_accuracy["mape"] < 15]
        acceptable_horizon = acceptable_accuracy["horizon_hours"].max() if len(acceptable_accuracy) > 0 else 0
        
        forecast_upper = min(cliff_horizon, acceptable_horizon)
        heuristic_lower = max(cliff_horizon, acceptable_horizon)
        
        recommendations.append({
            "region": region,
            "region_name": REGIONS.get(region, {}).get("name", region),
            "use_realtime_up_to": 1,
            "use_forecast_up_to": forecast_upper,
            "use_heuristic_beyond": heuristic_lower,
            "good_accuracy_horizon": good_horizon,
            "acceptable_accuracy_horizon": acceptable_horizon,
            "cliff_horizon": cliff_horizon,
            "recommendation_summary": (
                f"Use real-time for <1h; forecast for 1-{forecast_upper:.0f}h; "
                f"heuristics for >{heuristic_lower:.0f}h"
            )
        })
    
    return pd.DataFrame(recommendations)


# =============================================================================
# PLOTTING FUNCTIONS
# =============================================================================

def plot_accuracy_by_horizon(accuracy_df: pd.DataFrame, figures_dir: Path):
    """Plot accuracy metrics vs forecast horizon."""
    
    if len(accuracy_df) == 0:
        print("    No accuracy data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    ax = axes[0]
    for region in accuracy_df["region"].unique():
        region_data = accuracy_df[accuracy_df["region"] == region].sort_values("horizon_hours")
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["horizon_hours"], region_data["mae"],
                marker='o', label=REGIONS.get(region, {}).get("name", region),
                color=color, linewidth=2)
    
    ax.set_xlabel("Forecast Horizon (hours)")
    ax.set_ylabel("Mean Absolute Error (MOER)")
    ax.set_title("Forecast Accuracy Degradation: MAE")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 75)
    
    ax = axes[1]
    for region in accuracy_df["region"].unique():
        region_data = accuracy_df[accuracy_df["region"] == region].sort_values("horizon_hours")
        color = REGION_COLORS.get(region, "#333333")
        ax.plot(region_data["horizon_hours"], region_data["mape"],
                marker='s', label=REGIONS.get(region, {}).get("name", region),
                color=color, linewidth=2)
    
    ax.axhline(y=10, color='green', linestyle='--', alpha=0.5, label='10% threshold')
    ax.axhline(y=15, color='orange', linestyle='--', alpha=0.5, label='15% threshold')
    
    ax.set_xlabel("Forecast Horizon (hours)")
    ax.set_ylabel("Mean Absolute Percentage Error (%)")
    ax.set_title("Forecast Accuracy Degradation: MAPE")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 75)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "10_accuracy_by_horizon.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 10_accuracy_by_horizon.png")


def plot_accuracy_by_season_horizon(season_df: pd.DataFrame, figures_dir: Path):
    """Plot accuracy heatmap by season and horizon."""
    
    if len(season_df) == 0:
        print("    No season data to plot")
        return
    
    regions = season_df["region"].unique()
    n_regions = len(regions)
    
    fig, axes = plt.subplots(1, n_regions, figsize=(5 * n_regions, 5), squeeze=False)
    
    season_order = ["winter", "spring", "summer", "fall"]
    
    for i, region in enumerate(regions):
        ax = axes[0, i]
        region_data = season_df[season_df["region"] == region]
        
        pivot = region_data.pivot_table(index="season", columns="horizon_hours", values="mape")
        pivot = pivot.reindex(season_order)
        
        sns.heatmap(pivot, ax=ax, cmap="RdYlGn_r", annot=True, fmt=".1f",
                    cbar_kws={"label": "MAPE (%)"})
        
        ax.set_title(REGIONS.get(region, {}).get("name", region))
        ax.set_xlabel("Horizon (hours)")
        ax.set_ylabel("Season")
        ax.set_yticklabels([s.capitalize() for s in season_order], rotation=0)
    
    plt.suptitle("Forecast Accuracy by Season and Horizon\n(Lower = better)", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(figures_dir / "10_accuracy_by_season_horizon.png", dpi=FIGURE_DPI, bbox_inches='tight')
    plt.close()
    print("    Saved: 10_accuracy_by_season_horizon.png")


def plot_decision_reliability(reliability_df: pd.DataFrame, figures_dir: Path):
    """Plot decision reliability summary."""
    
    if len(reliability_df) == 0:
        print("    No reliability data to plot")
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    regions = reliability_df["region"].unique()
    x = np.arange(len(regions))
    
    # Capture rate by region
    ax = axes[0]
    for i, region in enumerate(regions):
        row = reliability_df[reliability_df["region"] == region].iloc[0]
        color = REGION_COLORS.get(region, "#333333")
        ax.bar(i, row["mean_capture_rate"], color=color, edgecolor="black",
               label=REGIONS.get(region, {}).get("name", region))
        if not np.isnan(row["std_capture_rate"]):
            ax.errorbar(i, row["mean_capture_rate"], yerr=row["std_capture_rate"],
                        fmt="none", color="black", capsize=4)
    
    ax.axhline(y=0.8, color='green', linestyle='--', alpha=0.5, label='80% target')
    ax.axhline(y=0.9, color='blue', linestyle='--', alpha=0.5, label='90% target')
    ax.set_xticks(x)
    ax.set_xticklabels([REGIONS.get(r, {}).get("name", r) for r in regions], rotation=30, ha="right")
    ax.set_ylabel("Mean Capture Rate")
    ax.set_title(f"Scheduling Decision Quality\n({SCHEDULING_WINDOW_HOURS}h window)")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_ylim(0, 1.05)
    
    # % achieving 80% savings
    ax = axes[1]
    for i, region in enumerate(regions):
        row = reliability_df[reliability_df["region"] == region].iloc[0]
        color = REGION_COLORS.get(region, "#333333")
        ax.bar(i, row["pct_achieved_80"], color=color, edgecolor="black")
    
    ax.axhline(y=80, color='orange', linestyle='--', alpha=0.5, label='80% threshold')
    ax.set_xticks(x)
    ax.set_xticklabels([REGIONS.get(r, {}).get("name", r) for r in regions], rotation=30, ha="right")
    ax.set_ylabel("% of Decisions Achieving >=80% Savings")
    ax.set_title("Decision Reliability\n(How often do forecasts deliver?)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_ylim(0, 105)
    
    plt.tight_layout()
    plt.savefig(figures_dir / "10_decision_reliability.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 10_decision_reliability.png")


def plot_recommendations_visual(recommendations: pd.DataFrame, figures_dir: Path):
    """Create visual summary of forecast usage recommendations."""
    
    if len(recommendations) == 0:
        print("    No recommendations to plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    regions = recommendations["region_name"].values
    y_positions = range(len(regions))
    
    for i, (_, row) in enumerate(recommendations.iterrows()):
        ax.barh(i, row["use_realtime_up_to"], left=0, height=0.6,
                color='#2ecc71', edgecolor='black', label='Real-time' if i == 0 else "")
        
        ax.barh(i, row["use_forecast_up_to"] - row["use_realtime_up_to"],
                left=row["use_realtime_up_to"], height=0.6,
                color='#3498db', edgecolor='black', label='Forecast' if i == 0 else "")
        
        ax.barh(i, 72 - row["use_forecast_up_to"],
                left=row["use_forecast_up_to"], height=0.6,
                color='#e67e22', edgecolor='black', label='Heuristic' if i == 0 else "")
        
        ax.axvline(x=row["cliff_horizon"], color='red', linestyle='--', alpha=0.3)
    
    ax.set_yticks(y_positions)
    ax.set_yticklabels(regions)
    ax.set_xlabel("Planning Horizon (hours)")
    ax.set_title("When to Use Forecast vs Heuristic\n(based on accuracy analysis)")
    ax.legend(loc='upper right')
    ax.set_xlim(0, 72)
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    plt.savefig(figures_dir / "10_recommendations_visual.png", dpi=FIGURE_DPI)
    plt.close()
    print("    Saved: 10_recommendations_visual.png")


# =============================================================================
# SUMMARY
# =============================================================================

def generate_summary_report(accuracy_df: pd.DataFrame, cliff_df: pd.DataFrame,
                            reliability_df: pd.DataFrame, recommendations: pd.DataFrame,
                            signal: str, outputs_dir: Path):
    """Generate text summary of forecast horizon analysis."""
    
    lines = [
        "=" * 70,
        "FORECAST HORIZON ANALYSIS SUMMARY",
        "=" * 70,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Signal: {signal}",
        "",
    ]
    
    if len(accuracy_df) > 0:
        lines.extend([
            "-" * 70,
            "FORECAST ACCURACY BY HORIZON",
            "-" * 70,
        ])
        
        for region in accuracy_df["region"].unique():
            region_data = accuracy_df[accuracy_df["region"] == region]
            lines.append(f"\n{REGIONS.get(region, {}).get('name', region)}:")
            
            for horizon in [1, 4, 12, 24, 48]:
                horizon_data = region_data[region_data["horizon_hours"] == horizon]
                if len(horizon_data) > 0:
                    row = horizon_data.iloc[0]
                    lines.append(
                        f"  {horizon:2d}h: MAE={row['mae']:.0f}, "
                        f"MAPE={row['mape']:.1f}%, corr={row['correlation']:.3f}"
                    )
    
    if len(cliff_df) > 0:
        lines.extend([
            "",
            "-" * 70,
            "ACCURACY CLIFF DETECTION",
            "-" * 70,
        ])
        
        for _, row in cliff_df.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  MAPE cliff at: {row['mape_cliff_horizon']}h")
            lines.append(f"  Correlation drop at: {row['correlation_drop_horizon']}h")
            lines.append(f"  Recommended max horizon: {row['recommended_max_horizon']}h")
    
    if len(reliability_df) > 0:
        lines.extend([
            "",
            "-" * 70,
            "DECISION RELIABILITY",
            "-" * 70,
        ])
        
        for _, row in reliability_df.iterrows():
            lines.append(f"\n{REGIONS.get(row['region'], {}).get('name', row['region'])}:")
            lines.append(f"  Capture rate: {row['mean_capture_rate']:.2f}")
            lines.append(f"  Achieved >=80% savings: {row['pct_achieved_80']:.0f}% of time")
    
    if len(recommendations) > 0:
        lines.extend([
            "",
            "-" * 70,
            "RECOMMENDATIONS",
            "-" * 70,
        ])
        
        for _, row in recommendations.iterrows():
            lines.append(f"\n{row['region_name']}:")
            lines.append(f"  {row['recommendation_summary']}")
    
    lines.extend([
        "",
        "-" * 70,
        "KEY TAKEAWAYS",
        "-" * 70,
        "",
        "1. Forecast accuracy degrades with horizon - identify your region's cliff",
        "2. Use real-time data for immediate scheduling (< 1 hour)",
        "3. Day-ahead forecasts typically reliable for most regions",
        "4. Beyond 24-48 hours, heuristics may perform as well as forecasts",
        "",
        "=" * 70,
        "END OF REPORT",
        "=" * 70,
    ])
    
    report_text = "\n".join(lines)
    
    with open(outputs_dir / "10_summary_report.txt", "w", encoding="utf-8") as f:
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
    run_dir = get_run_dir()
    config = load_run_config(run_dir)
    signal = config["signal"]
    
    print("=" * 70)
    print("FORECAST HORIZON ANALYSIS")
    print("=" * 70)
    print(f"Run: {run_dir.name}")
    print(f"Signal: {signal}")
    print("=" * 70)
    
    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    
    # Load data (forecast returned as Path, not loaded into memory)
    df_hourly, forecast_path = load_data(run_dir)
    
    if forecast_path is None:
        print("\nERROR: This module requires forecast data.")
        print("Ensure 01_data_collection.py collected forecast data.")
        sys.exit(1)
    
    # Prepare merged data (loads forecast per-region internally)
    merged = prepare_forecast_actuals(df_hourly, forecast_path)
    
    if len(merged) == 0:
        print("\nERROR: Could not match forecasts to actuals.")
        sys.exit(1)
    
    gc.collect()
    
    # Initialize results
    accuracy_df = pd.DataFrame()
    cliff_df = pd.DataFrame()
    season_df = pd.DataFrame()
    tod_df = pd.DataFrame()
    peak_df = pd.DataFrame()
    decision_df = pd.DataFrame()
    reliability_df = pd.DataFrame()
    recommendations = pd.DataFrame()
    
    # ======================================================================
    # SECTION 1: ACCURACY BY HORIZON
    # ======================================================================
    if RUN_ACCURACY_BY_HORIZON:
        print("\n" + "=" * 70)
        print("SECTION 1: ACCURACY BY HORIZON")
        print("=" * 70)
        
        accuracy_df = analyze_accuracy_by_horizon(merged)
        accuracy_df.to_csv(outputs_dir / "10_accuracy_by_horizon.csv", index=False)
        
        cliff_df = identify_accuracy_cliff(accuracy_df)
        cliff_df.to_csv(outputs_dir / "10_accuracy_cliff.csv", index=False)
        
        plot_accuracy_by_horizon(accuracy_df, figures_dir)
    
    # ======================================================================
    # SECTION 2: ACCURACY BY CONTEXT
    # ======================================================================
    if RUN_ACCURACY_BY_CONTEXT:
        print("\n" + "=" * 70)
        print("SECTION 2: ACCURACY BY CONTEXT")
        print("=" * 70)
        
        season_df = analyze_accuracy_by_season(merged)
        season_df.to_csv(outputs_dir / "10_accuracy_by_season.csv", index=False)
        
        tod_df = analyze_accuracy_by_time_of_day(merged)
        tod_df.to_csv(outputs_dir / "10_accuracy_by_time_of_day.csv", index=False)
        
        peak_df = analyze_peak_vs_offpeak(merged)
        peak_df.to_csv(outputs_dir / "10_peak_vs_offpeak.csv", index=False)
        
        plot_accuracy_by_season_horizon(season_df, figures_dir)
    
    # ======================================================================
    # SECTION 3: DECISION RELIABILITY
    # ======================================================================
    if RUN_DECISION_RELIABILITY:
        print("\n" + "=" * 70)
        print("SECTION 3: DECISION RELIABILITY")
        print("=" * 70)
        
        decision_df = analyze_decision_reliability(merged, df_hourly)
        if len(decision_df) > 0:
            decision_df.to_csv(outputs_dir / "10_decision_details.csv", index=False)
            
            reliability_df = summarize_decision_reliability(decision_df)
            reliability_df.to_csv(outputs_dir / "10_decision_reliability.csv", index=False)
            
            plot_decision_reliability(reliability_df, figures_dir)
    
    # ======================================================================
    # SECTION 4: THRESHOLD RECOMMENDATIONS
    # ======================================================================
    if RUN_THRESHOLD_RECOMMENDATIONS and len(accuracy_df) > 0:
        print("\n" + "=" * 70)
        print("SECTION 4: THRESHOLD RECOMMENDATIONS")
        print("=" * 70)
        
        recommendations = generate_threshold_recommendations(accuracy_df, cliff_df, reliability_df)
        recommendations.to_csv(outputs_dir / "10_recommendations.csv", index=False)
        
        plot_recommendations_visual(recommendations, figures_dir)
    
    # ======================================================================
    # SUMMARY
    # ======================================================================
    print("\n" + "=" * 70)
    print("GENERATING SUMMARY")
    print("=" * 70)
    
    generate_summary_report(accuracy_df, cliff_df, reliability_df, recommendations,
                            signal, outputs_dir)
    
    mark_script_run(run_dir, "10_forecast_horizon")
    
    print("\n" + "=" * 70)
    print("FORECAST HORIZON ANALYSIS COMPLETE")
    print("=" * 70)
    print(f"Figures: {figures_dir}/10_*.png")
    print(f"Data: {outputs_dir}/10_*.csv")
    print(f"Report: {outputs_dir}/10_summary_report.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()