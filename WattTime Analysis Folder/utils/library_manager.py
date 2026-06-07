"""
Library Manager - Catalog and Data Access

Manages the append-only data library:
- Catalog tracking (what data exists)
- File naming conventions
- Data retrieval and filtering

Library structure:
    library/
    ├── catalog.json
    ├── co2_moer/
    │   ├── historical/
    │   │   └── {REGION}.parquet
    │   └── forecast/
    │       └── {REGION}.parquet
    └── ...
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import LIBRARY_DIR, get_catalog_path, SIGNALS, REGIONS

# Valid data types
DataType = Literal["historical", "forecast"]


def load_catalog() -> dict:
    """Load the library catalog, creating if doesn't exist."""
    catalog_path = get_catalog_path()
    
    if catalog_path.exists():
        with open(catalog_path, 'r') as f:
            return json.load(f)
    
    # Initialize empty catalog
    return {
        "version": "2.0",
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "signals": {}
    }


def save_catalog(catalog: dict) -> None:
    """Save the library catalog."""
    catalog_path = get_catalog_path()
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    
    catalog["updated"] = datetime.now().isoformat()
    
    with open(catalog_path, 'w') as f:
        json.dump(catalog, f, indent=2)


def get_library_file_path(signal: str, region: str, data_type: DataType = "historical") -> Path:
    """
    Get the file path for a signal/region/data_type combination.
    
    Structure: library/{signal}/{data_type}/{region}.parquet
    """
    path = LIBRARY_DIR / signal / data_type / f"{region}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def check_data_exists(signal: str, region: str, data_type: DataType = "historical") -> Optional[dict]:
    """
    Check if data exists for a signal/region/data_type.
    Returns metadata dict if exists, None otherwise.
    """
    catalog = load_catalog()
    
    if signal not in catalog["signals"]:
        return None
    
    if region not in catalog["signals"][signal]:
        return None
    
    if data_type not in catalog["signals"][signal][region]:
        return None
    
    return catalog["signals"][signal][region][data_type]


def get_data_coverage(
    signal: str, 
    region: str, 
    data_type: DataType = "historical"
) -> Optional[Tuple[datetime, datetime]]:
    """
    Get the date range covered for a signal/region/data_type.
    Returns (start, end) tuple or None if no data.
    """
    metadata = check_data_exists(signal, region, data_type)
    if metadata is None:
        return None
    
    return (
        datetime.fromisoformat(metadata["start"]),
        datetime.fromisoformat(metadata["end"])
    )


def register_data(
    signal: str,
    region: str,
    data_type: DataType,
    start: datetime,
    end: datetime,
    n_records: int,
    file_path: Path
) -> None:
    """Register new or updated data in the catalog."""
    catalog = load_catalog()
    
    # Build nested structure
    if signal not in catalog["signals"]:
        catalog["signals"][signal] = {}
    
    if region not in catalog["signals"][signal]:
        catalog["signals"][signal][region] = {}
    
    catalog["signals"][signal][region][data_type] = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "n_records": n_records,
        "file": str(file_path.relative_to(LIBRARY_DIR)),
        "updated": datetime.now().isoformat(),
    }
    
    save_catalog(catalog)


def load_library_data(
    signal: str,
    regions: List[str],
    data_type: DataType = "historical",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Load data from library for specified signal, regions, and data type.
    Optionally filter by date range.
    
    Args:
        signal: Signal type (e.g., 'co2_moer')
        regions: List of region codes
        data_type: 'historical' or 'forecast'
        start: Optional start date filter
        end: Optional end date filter
    
    Returns:
        Combined DataFrame with 'region' column
    """
    dfs = []
    
    for region in regions:
        file_path = get_library_file_path(signal, region, data_type)
        
        if not file_path.exists():
            print(f"  Warning: No {data_type} data for {signal}/{region}")
            continue
        
        df = pd.read_parquet(file_path)
        
        # Apply date filters based on data type
        time_col = "point_time"  # Both historical and forecast have this
        
        if time_col in df.columns:
            df[time_col] = pd.to_datetime(df[time_col])
            
            if start is not None:
                df = df[df[time_col] >= pd.Timestamp(start, tz='UTC')]
            if end is not None:
                df = df[df[time_col] <= pd.Timestamp(end, tz='UTC')]
        
        if len(df) > 0:
            dfs.append(df)
            print(f"  Loaded {region} ({data_type}): {len(df):,} records")
    
    if not dfs:
        return pd.DataFrame()
    
    return pd.concat(dfs, ignore_index=True)


def list_library_contents() -> None:
    """Print summary of library contents."""
    catalog = load_catalog()
    
    print("=" * 70)
    print("LIBRARY CONTENTS")
    print("=" * 70)
    
    if not catalog["signals"]:
        print("\n  Library is empty. Run data collection first.")
        return
    
    total_records = 0
    
    for signal, regions in catalog["signals"].items():
        signal_meta = SIGNALS.get(signal, {})
        signal_name = signal_meta.get("name", signal)
        unit_label = signal_meta.get("unit_label", "value")
        
        print(f"\n{signal} ({signal_name}) [{unit_label}]:")
        print("-" * 50)
        
        for region, data_types in regions.items():
            region_name = REGIONS.get(region, {}).get("name", region)
            print(f"\n  {region_name}:")
            
            for data_type, metadata in data_types.items():
                n_records = metadata.get("n_records", "?")
                start = metadata.get("start", "?")[:10]
                end = metadata.get("end", "?")[:10]
                
                records_str = f"{n_records:,}" if isinstance(n_records, int) else str(n_records)
                print(f"    {data_type}: {records_str} records ({start} to {end})")
                
                if isinstance(n_records, int):
                    total_records += n_records
    
    print(f"\n{'=' * 70}")
    print(f"Total records in library: {total_records:,}")
    print("=" * 70)


def get_available_signals() -> List[str]:
    """Get list of signals that have data in library."""
    catalog = load_catalog()
    return list(catalog["signals"].keys())


def get_available_regions(signal: str, data_type: Optional[DataType] = None) -> List[str]:
    """
    Get list of regions that have data for a signal.
    Optionally filter by data_type.
    """
    catalog = load_catalog()
    if signal not in catalog["signals"]:
        return []
    
    if data_type is None:
        return list(catalog["signals"][signal].keys())
    
    # Filter to regions that have the specific data type
    return [
        region for region, types in catalog["signals"][signal].items()
        if data_type in types
    ]


def get_available_data_types(signal: str, region: str) -> List[str]:
    """Get list of data types available for a signal/region."""
    catalog = load_catalog()
    
    if signal not in catalog["signals"]:
        return []
    if region not in catalog["signals"][signal]:
        return []
    
    return list(catalog["signals"][signal][region].keys())


def calculate_missing_ranges(
    signal: str,
    region: str,
    data_type: DataType,
    target_start: datetime,
    target_end: datetime
) -> List[Tuple[datetime, datetime]]:
    """
    Calculate what date ranges need to be fetched.
    Returns list of (start, end) tuples for missing ranges.
    """
    existing = get_data_coverage(signal, region, data_type)
    
    if existing is None:
        # No data at all, need everything
        return [(target_start, target_end)]
    
    existing_start, existing_end = existing
    
    # Strip timezone info for comparison
    existing_start_naive = existing_start.replace(tzinfo=None) if existing_start.tzinfo else existing_start
    existing_end_naive = existing_end.replace(tzinfo=None) if existing_end.tzinfo else existing_end
    target_start_naive = target_start.replace(tzinfo=None) if target_start.tzinfo else target_start
    target_end_naive = target_end.replace(tzinfo=None) if target_end.tzinfo else target_end
    
    missing = []
    
    # Check if we need data before existing
    if target_start_naive < existing_start_naive:
        missing.append((target_start, existing_start_naive))
    
    # Check if we need data after existing
    if target_end_naive > existing_end_naive:
        missing.append((existing_end_naive, target_end))
    
    return missing


def validate_library_requirements(
    signal: str,
    regions: List[str],
    data_type: DataType,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> Tuple[bool, List[str]]:
    """
    Validate that required data exists in library.
    
    Returns:
        (is_valid, list_of_missing_items)
    """
    missing = []
    
    for region in regions:
        if not check_data_exists(signal, region, data_type):
            missing.append(f"{signal}/{region}/{data_type}")
            continue
        
        # Check date coverage if specified
        if start and end:
            coverage = get_data_coverage(signal, region, data_type)
            if coverage:
                cov_start, cov_end = coverage
                  # Strip timezone info for comparison (compare dates only)
                cov_start_naive = cov_start.replace(tzinfo=None) if cov_start.tzinfo else cov_start
                cov_end_naive = cov_end.replace(tzinfo=None) if cov_end.tzinfo else cov_end
                start_naive = start.replace(tzinfo=None) if start.tzinfo else start
                end_naive = end.replace(tzinfo=None) if end.tzinfo else end
                
                if cov_start_naive > start_naive or cov_end_naive < end_naive:
                    missing.append(
                        f"{signal}/{region}/{data_type} (partial: {cov_start.date()} to {cov_end.date()})"
                    )
    return len(missing) == 0, missing


if __name__ == "__main__":
    # When run directly, show library contents
    list_library_contents()
