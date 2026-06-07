"""
02_data_processing.py - Data Processing

Loads data from library, processes it, and saves to a run folder.

Usage:
    1. Edit the CONFIG section below
    2. Run: python 02_data_processing.py
    
The script will:
    1. Auto-create a run folder based on your config
    2. Validate library has required data
    3. Load and combine data from library
    4. Add time features (hour, day, season, etc.)
    5. Calculate daily statistics
    6. Save processed data to run folder
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import json
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, MAX_MISSING_PCT_PER_DAY, SIGNALS, RUNS_DIR,
    get_signal_metadata, get_unit_label, expand_region_group
)
from utils.library_manager import (
    load_library_data, validate_library_requirements, list_library_contents
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Run name (will be prefixed with date, e.g., "2025-01-28_moer_temporal")
RUN_NAME = "AOER_6RegionSummary_V1"

# Signal to analyze: "co2_moer", "co2_aoer", or "health_damage"
SIGNAL = "co2_aoer"

# Regions to analyze - use a group name OR a list of specific regions
# Group options: "US_5REG", "MOER_REGIONS", "HEALTH_REGIONS", "INDY_ONLY", "EAST_COAST"
# Or list specific regions: ["MISO_INDIANAPOLIS", "PJM_NJ"]
REGIONS_TO_ANALYZE = "AOER_6RegionSummary"

# Data types needed: ["historical"], ["forecast"], or ["historical", "forecast"]
DATA_TYPES = ["historical"]

# Date range filter (None = use all available data)
START_DATE = datetime(2022, 10, 1)  # or None #2022-09-30 should be the start date for forcast
END_DATE = datetime(2024, 12, 31)    # or None

# Description (optional, for your reference)
DESCRIPTION = "AOER_6RegionSummary_V1 Run"

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================


def create_run_folder() -> Path:
    """Create a run folder based on config and return its path."""
    timestamp = datetime.now().strftime("%Y-%m-%d")
    run_dir_name = f"{timestamp}_{RUN_NAME}"
    run_dir = RUNS_DIR / run_dir_name
    
    # Handle duplicate names
    counter = 1
    while run_dir.exists():
        run_dir_name = f"{timestamp}_{RUN_NAME}_{counter}"
        run_dir = RUNS_DIR / run_dir_name
        counter += 1
    
    # Create directory structure
    run_dir.mkdir(parents=True)
    (run_dir / "processed").mkdir()
    (run_dir / "outputs").mkdir()
    (run_dir / "figures").mkdir()
    
    # Save run config
    regions = expand_region_group(REGIONS_TO_ANALYZE)
    config = {
        "name": RUN_NAME,
        "created": datetime.now().isoformat(),
        "signal": SIGNAL,
        "regions": regions,
        "data_types": DATA_TYPES,
        "date_range": {
            "start": START_DATE.isoformat() if START_DATE else None,
            "end": END_DATE.isoformat() if END_DATE else None,
        },
        "description": DESCRIPTION,
        "scripts_run": [],
        "signal_metadata": SIGNALS.get(SIGNAL, {}),
    }
    
    with open(run_dir / "run_config.json", 'w') as f:
        json.dump(config, f, indent=2, default=str)
    
    return run_dir


def convert_to_local_time(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert UTC timestamps to local time for each region.
    Uses tz_localize(None) to allow concatenation of multiple regions.
    """
    print("Converting to local time...")
    
    df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
    
    result_dfs = []
    
    for region in df["region"].unique():
        if region not in REGIONS:
            print(f"  Warning: Unknown region {region}, using UTC")
            region_df = df[df["region"] == region].copy()
            region_df["point_time_local"] = region_df["point_time"].dt.tz_localize(None)
        else:
            tz_str = REGIONS[region]["timezone"]
            region_df = df[df["region"] == region].copy()
            region_df["point_time_local"] = (
                region_df["point_time"]
                .dt.tz_convert(tz_str)
                .dt.tz_localize(None)
            )
            print(f"  {region}: converted to {tz_str}")
        
        result_dfs.append(region_df)
    
    df = pd.concat(result_dfs, ignore_index=True)
    
    null_count = df["point_time_local"].isna().sum()
    if null_count > 0:
        print(f"  Warning: {null_count} records have null local times")
    
    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time-based features for analysis."""
    print("Adding time features...")
    
    df["year"] = df["point_time_local"].dt.year
    df["month"] = df["point_time_local"].dt.month
    df["day"] = df["point_time_local"].dt.day
    df["hour"] = df["point_time_local"].dt.hour
    df["minute"] = df["point_time_local"].dt.minute
    df["day_of_week"] = df["point_time_local"].dt.dayofweek
    df["day_name"] = df["point_time_local"].dt.day_name()
    df["is_weekend"] = df["day_of_week"].isin([5, 6])
    
    # Date (normalized to midnight for easier grouping)
    df["date"] = df["point_time_local"].dt.normalize()
    
    # Season mapping
    def get_season(month):
        for season, months in SEASONS.items():
            if month in months:
                return season
        return None
    
    df["season"] = df["month"].apply(get_season)
    
    # Time of day category
    def get_time_of_day(hour):
        if 6 <= hour < 12: return "morning"
        elif 12 <= hour < 18: return "afternoon"
        elif 18 <= hour < 22: return "evening"
        else: return "night"
    
    df["time_of_day"] = df["hour"].apply(get_time_of_day)
    
    print("  Added: year, month, day, hour, minute, day_of_week, day_name, is_weekend, date, season, time_of_day")
    return df


def calculate_daily_statistics(df: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Calculate daily summary statistics for each region."""
    print("Calculating daily statistics...")
    
    unit_label = get_unit_label(signal)
    
    daily = df.groupby(["region", "date"]).agg(
        value_mean=("value", "mean"),
        value_std=("value", "std"),
        value_min=("value", "min"),
        value_max=("value", "max"),
        value_median=("value", "median"),
        value_p10=("value", lambda x: x.quantile(0.10)),
        value_p90=("value", lambda x: x.quantile(0.90)),
        n_records=("value", "count"),
    ).reset_index()
    
    daily["n_expected"] = 288  # 5-min intervals
    daily["value_range"] = daily["value_max"] - daily["value_min"]
    daily["value_cv"] = daily["value_std"] / daily["value_mean"]
    daily["missing_pct"] = 100 * (1 - daily["n_records"] / 288)
    daily["has_quality_issues"] = daily["missing_pct"] > MAX_MISSING_PCT_PER_DAY
    
    # Add signal metadata
    daily["signal"] = signal
    daily["unit_label"] = unit_label
    
    # Extract date parts
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    daily["day_of_week"] = daily["date"].dt.dayofweek
    daily["is_weekend"] = daily["day_of_week"].isin([5, 6])
    
    def get_season(month):
        for season, months in SEASONS.items():
            if month in months:
                return season
        return None
    daily["season"] = daily["month"].apply(get_season)
    
    print(f"  Calculated stats for {len(daily):,} region-days")
    return daily


def create_hourly_summary(df: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Create hourly aggregated dataset for profile visualizations."""
    print("Creating hourly summary...")
    
    hourly = df.groupby(["region", "year", "month", "day", "hour", "date"]).agg(
        value_mean=("value", "mean"),
        value_std=("value", "std"),
        value_min=("value", "min"),
        value_max=("value", "max"),
        n_records=("value", "count"),
    ).reset_index()
    
    # Add signal metadata
    hourly["signal"] = signal
    hourly["unit_label"] = get_unit_label(signal)
    
    hourly["day_of_week"] = hourly["date"].dt.dayofweek
    hourly["is_weekend"] = hourly["day_of_week"].isin([5, 6])
    
    def get_season(month):
        for season, months in SEASONS.items():
            if month in months:
                return season
        return None
    hourly["season"] = hourly["month"].apply(get_season)
    
    print(f"  Created {len(hourly):,} hourly records")
    return hourly


def print_data_summary(df: pd.DataFrame, daily: pd.DataFrame, signal: str):
    """Print summary of processed data."""
    signal_meta = get_signal_metadata(signal)
    unit_label = signal_meta["unit_label"]
    
    print("\n" + "=" * 60)
    print("DATA PROCESSING SUMMARY")
    print("=" * 60)
    
    print(f"\nSignal: {signal} ({signal_meta['name']})")
    print(f"\n5-minute dataset: {len(df):,} records")
    print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")
    
    print("\nRecords by region:")
    for region in sorted(df["region"].unique()):
        n = len(df[df["region"] == region])
        region_name = REGIONS.get(region, {}).get("name", region)
        print(f"  {region_name}: {n:,}")
    
    print(f"\nValue statistics (all regions combined):")
    print(f"  Mean: {df['value'].mean():.1f} {unit_label}")
    print(f"  Std:  {df['value'].std():.1f} {unit_label}")
    print(f"  Min:  {df['value'].min():.1f} {unit_label}")
    print(f"  Max:  {df['value'].max():.1f} {unit_label}")
    
    print("\nData quality:")
    quality_issues = daily["has_quality_issues"].sum()
    print(f"  Days with >{MAX_MISSING_PCT_PER_DAY}% missing: {quality_issues} / {len(daily)}")
    
    print("=" * 60)


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
    # Resolve regions from config
    regions = expand_region_group(REGIONS_TO_ANALYZE)
    
    print("=" * 60)
    print("DATA PROCESSING")
    print("=" * 60)
    print(f"Run name: {RUN_NAME}")
    print(f"Signal: {SIGNAL} ({SIGNALS[SIGNAL]['name']})")
    print(f"Regions: {', '.join(regions)}")
    print(f"Data types: {', '.join(DATA_TYPES)}")
    if START_DATE and END_DATE:
        print(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    print("=" * 60)
    
    # Validate signal
    if SIGNAL not in SIGNALS:
        print(f"\nERROR: Unknown signal '{SIGNAL}'")
        print(f"Valid options: {list(SIGNALS.keys())}")
        sys.exit(1)
    
    # Validate library has required data
    print("\nValidating library data...")
    all_missing = []
    for data_type in DATA_TYPES:
        is_valid, missing = validate_library_requirements(
            SIGNAL, regions, data_type, START_DATE, END_DATE
        )
        all_missing.extend(missing)
    
    if all_missing:
        print("\nERROR: Missing library data:")
        for m in all_missing:
            print(f"  - {m}")
        print("\nRun data collection first. Edit 01_data_collection.py with:")
        print(f"  SIGNAL = \"{SIGNAL}\"")
        print(f"  REGIONS_TO_FETCH = {regions}")
        print("\nThen run: python scripts/01_data_collection.py")
        sys.exit(1)
    print("  Library data: OK")
    
    # Create run folder
    print("\nCreating run folder...")
    run_dir = create_run_folder()
    print(f"  Created: {run_dir}")
    
    # Process historical data
    if "historical" in DATA_TYPES:
        print("\nLoading historical data from library...")
        df = load_library_data(SIGNAL, regions, "historical", START_DATE, END_DATE)
        
        if len(df) == 0:
            print("ERROR: No historical data loaded")
            sys.exit(1)
        
        print(f"  Total records: {len(df):,}")
        
        # Process
        df = convert_to_local_time(df)
        df = add_time_features(df)
        
        # Calculate aggregates
        daily = calculate_daily_statistics(df, SIGNAL)
        hourly = create_hourly_summary(df, SIGNAL)
        
        # Save to run folder
        print("\nSaving processed data to run folder...")
        processed_dir = run_dir / "processed"
        
        df.to_parquet(processed_dir / "data_5min.parquet", index=False)
        hourly.to_parquet(processed_dir / "data_hourly.parquet", index=False)
        daily.to_parquet(processed_dir / "daily_statistics.parquet", index=False)
        
        print(f"  Saved: data_5min.parquet ({len(df):,} records)")
        print(f"  Saved: data_hourly.parquet ({len(hourly):,} records)")
        print(f"  Saved: daily_statistics.parquet ({len(daily):,} records)")
        
        print_data_summary(df, daily, SIGNAL)
    
    # Process forecast data if needed
    if "forecast" in DATA_TYPES:
        print("\nLoading forecast data from library...")
        df_forecast = load_library_data(SIGNAL, regions, "forecast", START_DATE, END_DATE)
        
        if len(df_forecast) == 0:
            print("  Warning: No forecast data loaded")
        else:
            print(f"  Total forecast records: {len(df_forecast):,}")
            
            # Save forecast data (minimal processing - keep generated_at)
            processed_dir = run_dir / "processed"
            df_forecast.to_parquet(processed_dir / "data_forecast.parquet", index=False)
            print(f"  Saved: data_forecast.parquet ({len(df_forecast):,} records)")
    
    # Mark script as run
    mark_script_run(run_dir, "02_data_processing")
    
    print("\n" + "=" * 60)
    print("DATA PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Run folder: {run_dir}")
    print(f"Processed data: {run_dir / 'processed'}")
    print("\nNext steps:")
    print("  1. Update RUN_FOLDER in 03_temporal_patterns.py")
    print("  2. Run: python scripts/03_temporal_patterns.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
