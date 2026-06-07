"""
Data Quality Validation

Checks library data for:
- Gaps in time series
- Missing data percentages
- Outliers and anomalies
- Coverage completeness
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import LIBRARY_DIR, SIGNALS, REGIONS, MAX_MISSING_PCT_PER_DAY
from utils.library_manager import (
    load_catalog, get_library_file_path, get_available_signals,
    get_available_regions, get_available_data_types
)


def check_time_series_gaps(df: pd.DataFrame, expected_interval_minutes: int = 5) -> dict:
    """
    Check for gaps in time series data.
    
    Returns dict with gap statistics.
    """
    if "point_time" not in df.columns or len(df) == 0:
        return {"error": "No point_time column or empty dataframe"}
    
    df = df.sort_values("point_time")
    
    # Calculate time differences
    time_diffs = df["point_time"].diff().dt.total_seconds() / 60
    
    # Expected interval
    expected = expected_interval_minutes
    tolerance = expected * 0.5  # Allow 50% tolerance
    
    # Find gaps (where diff is more than expected + tolerance)
    gaps = time_diffs[time_diffs > expected + tolerance]
    
    return {
        "total_records": len(df),
        "expected_interval_minutes": expected,
        "n_gaps": len(gaps),
        "max_gap_minutes": gaps.max() if len(gaps) > 0 else 0,
        "total_gap_minutes": gaps.sum() if len(gaps) > 0 else 0,
        "gap_locations": gaps.index.tolist()[:10],  # First 10 gap locations
    }


def check_daily_completeness(df: pd.DataFrame, expected_per_day: int = 288) -> pd.DataFrame:
    """
    Check completeness for each day.
    
    Args:
        df: DataFrame with point_time column
        expected_per_day: Expected records per day (288 for 5-min data)
    
    Returns:
        DataFrame with daily completeness stats
    """
    if "point_time" not in df.columns:
        return pd.DataFrame()
    
    df = df.copy()
    df["date"] = pd.to_datetime(df["point_time"]).dt.date
    
    daily = df.groupby("date").agg(
        n_records=("point_time", "count"),
    ).reset_index()
    
    daily["expected"] = expected_per_day
    daily["completeness_pct"] = 100 * daily["n_records"] / expected_per_day
    daily["missing_pct"] = 100 - daily["completeness_pct"]
    daily["has_quality_issues"] = daily["missing_pct"] > MAX_MISSING_PCT_PER_DAY
    
    return daily


def check_value_statistics(df: pd.DataFrame, signal: str) -> dict:
    """
    Check value statistics and potential outliers.
    """
    if "value" not in df.columns:
        return {"error": "No value column"}
    
    values = df["value"].dropna()
    
    if len(values) == 0:
        return {"error": "No values"}
    
    # Get expected range from signal metadata
    signal_meta = SIGNALS.get(signal, {})
    expected_range = signal_meta.get("typical_range", (0, 10000))
    
    # Calculate statistics
    stats = {
        "count": len(values),
        "mean": values.mean(),
        "std": values.std(),
        "min": values.min(),
        "max": values.max(),
        "median": values.median(),
        "p01": values.quantile(0.01),
        "p99": values.quantile(0.99),
    }
    
    # Check for potential issues
    stats["n_negative"] = (values < 0).sum()
    stats["n_zero"] = (values == 0).sum()
    stats["n_below_expected"] = (values < expected_range[0]).sum()
    stats["n_above_expected"] = (values > expected_range[1]).sum()
    
    # Outlier detection (values beyond 3 std from mean)
    mean, std = values.mean(), values.std()
    stats["n_outliers_3std"] = ((values < mean - 3*std) | (values > mean + 3*std)).sum()
    
    return stats


def validate_library_data(signal: str, region: str, data_type: str = "historical") -> dict:
    """
    Run full validation on a library dataset.
    """
    file_path = get_library_file_path(signal, region, data_type)
    
    if not file_path.exists():
        return {"error": f"No data file for {signal}/{region}/{data_type}"}
    
    print(f"Validating {signal}/{region}/{data_type}...")
    
    df = pd.read_parquet(file_path)
    df["point_time"] = pd.to_datetime(df["point_time"])
    
    # Run checks
    gaps = check_time_series_gaps(df)
    daily = check_daily_completeness(df)
    values = check_value_statistics(df, signal)
    
    # Summary
    result = {
        "signal": signal,
        "region": region,
        "data_type": data_type,
        "file_path": str(file_path),
        "date_range": {
            "start": df["point_time"].min().isoformat() if len(df) > 0 else None,
            "end": df["point_time"].max().isoformat() if len(df) > 0 else None,
        },
        "gaps": gaps,
        "daily_completeness": {
            "total_days": len(daily),
            "complete_days": (daily["completeness_pct"] >= 100 - MAX_MISSING_PCT_PER_DAY).sum() if len(daily) > 0 else 0,
            "days_with_issues": daily["has_quality_issues"].sum() if len(daily) > 0 else 0,
            "avg_completeness_pct": daily["completeness_pct"].mean() if len(daily) > 0 else 0,
        },
        "value_stats": values,
    }
    
    # Overall quality score
    issues = []
    if gaps.get("n_gaps", 0) > 10:
        issues.append(f"{gaps['n_gaps']} time gaps detected")
    if result["daily_completeness"]["days_with_issues"] > 0:
        issues.append(f"{result['daily_completeness']['days_with_issues']} days with quality issues")
    if values.get("n_negative", 0) > 0:
        issues.append(f"{values['n_negative']} negative values")
    if values.get("n_outliers_3std", 0) > 100:
        issues.append(f"{values['n_outliers_3std']} outliers (>3 std)")
    
    result["issues"] = issues
    result["quality_ok"] = len(issues) == 0
    
    return result


def validate_all_library() -> List[dict]:
    """Validate all data in library."""
    results = []
    
    for signal in get_available_signals():
        for region in get_available_regions(signal):
            for data_type in get_available_data_types(signal, region):
                result = validate_library_data(signal, region, data_type)
                results.append(result)
    
    return results


def print_validation_report(results: List[dict]) -> None:
    """Print formatted validation report."""
    print("=" * 70)
    print("LIBRARY DATA QUALITY REPORT")
    print("=" * 70)
    
    if not results:
        print("\n  No data in library to validate.")
        return
    
    # Summary
    total = len(results)
    ok = sum(1 for r in results if r.get("quality_ok", False))
    with_issues = total - ok
    
    print(f"\nDatasets validated: {total}")
    print(f"  ✓ Quality OK: {ok}")
    print(f"  ⚠ With issues: {with_issues}")
    
    # Details for each dataset
    for result in results:
        if "error" in result:
            print(f"\n{result.get('signal', '?')}/{result.get('region', '?')}/{result.get('data_type', '?')}: ERROR")
            print(f"  {result['error']}")
            continue
        
        signal = result["signal"]
        region = result["region"]
        data_type = result.get("data_type", "historical")
        status = "✓" if result["quality_ok"] else "⚠"
        
        print(f"\n{status} {signal}/{region}/{data_type}")
        
        # Date range
        dr = result.get("date_range", {})
        if dr.get("start"):
            print(f"  Date range: {dr['start'][:10]} to {dr['end'][:10]}")
        
        # Completeness
        dc = result.get("daily_completeness", {})
        print(f"  Days: {dc.get('total_days', '?')} total, {dc.get('complete_days', '?')} complete")
        print(f"  Avg completeness: {dc.get('avg_completeness_pct', 0):.1f}%")
        
        # Value stats
        vs = result.get("value_stats", {})
        if "mean" in vs:
            print(f"  Values: mean={vs['mean']:.1f}, range=[{vs['min']:.1f}, {vs['max']:.1f}]")
        
        # Issues
        issues = result.get("issues", [])
        if issues:
            print(f"  Issues:")
            for issue in issues:
                print(f"    - {issue}")
    
    print("\n" + "=" * 70)


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate library data quality")
    parser.add_argument("--signal", "-s", help="Specific signal to validate")
    parser.add_argument("--region", "-r", help="Specific region to validate")
    parser.add_argument("--data-type", "-t", default="historical",
                        choices=["historical", "forecast"],
                        help="Data type to validate (default: historical)")
    
    args = parser.parse_args()
    
    if args.signal and args.region:
        # Validate specific dataset
        result = validate_library_data(args.signal, args.region, args.data_type)
        print_validation_report([result])
    else:
        # Validate all
        results = validate_all_library()
        print_validation_report(results)
