"""
01_data_collection.py - WattTime Historical Data Collection

Pulls historical data from WattTime API into the library.
Supports multiple signals and intelligent caching.

Usage:
    1. Edit the CONFIG section below
    2. Run: python 01_data_collection.py
    
The script will:
    1. Check what data already exists in library
    2. Only fetch missing date ranges
    3. Append new data to existing files
    4. Update the library catalog

Performance features:
    - Parallel fetching across regions (configurable workers)
    - Monthly incremental saves (crash-safe)
    - Progress logging inside long fetches
    - Optional rate-limit sleep
"""

import requests
import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    WATTTIME_USERNAME, WATTTIME_PASSWORD, WATTTIME_BASE_URL,
    API_MAX_DAYS_PER_REQUEST, SIGNALS, REGIONS, REGION_GROUPS,
    DEFAULT_HISTORICAL_START, DEFAULT_HISTORICAL_END,
    expand_region_group
)
from utils.library_manager import (
    get_library_file_path, check_data_exists, register_data,
    calculate_missing_ranges, get_data_coverage
)

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Signal to fetch: "co2_moer", "co2_aoer", or "health_damage"
SIGNAL = "health_damage"

# Regions to fetch - use a group name OR a list of specific regions
# Group options: "US_5REG", "MOER_REGIONS", "HEALTH_REGIONS", "INDY_ONLY", "EAST_COAST"
# Or list specific regions: ["MISO_INDIANAPOLIS", "PJM_NJ"]  "CAISO_NORTH",

REGIONS_TO_FETCH = "GridMixStudy"

# Date range
START_DATE = datetime(2022, 1, 1)
END_DATE = datetime(2024, 12, 31)

# Data type: "historical" or "forecast"
DATA_TYPE = "historical"

# Parallel workers - increase for speed, decrease if hitting rate limits
# Set to 1 to run sequentially (original behavior)
MAX_WORKERS = 1

# Delay between API calls in seconds. Set to 0 to disable.
# Increase if you get 429 (rate limit) errors.
API_CALL_DELAY = 0.0

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================

# Thread-safe print lock
_print_lock = threading.Lock()

def safe_print(msg: str):
    """Thread-safe print."""
    with _print_lock:
        print(msg, flush=True)


class WattTimeClient:
    """WattTime API client with token management (thread-safe)."""
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.base_url = WATTTIME_BASE_URL
        self.token = None
        self.token_time = None
        self._token_lock = threading.Lock()
    
    def _get_token(self) -> str:
        """Get or refresh authentication token (thread-safe)."""
        with self._token_lock:
            if self.token and self.token_time:
                age = (datetime.now() - self.token_time).total_seconds() / 60
                if age < 25:
                    return self.token
            
            resp = requests.get(
                f"{self.base_url}/login",
                auth=(self.username, self.password)
            )
            resp.raise_for_status()
            self.token = resp.json()["token"]
            self.token_time = datetime.now()
            return self.token
    
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}
    
    def get_historical(
        self, 
        region: str, 
        start: datetime, 
        end: datetime,
        signal_type: str = "co2_moer"
    ) -> pd.DataFrame:
        """
        Fetch historical data for a region and time range.
        Handles the 32-day limit by chunking automatically.
        """
        all_data = []
        current_start = start
        total_days = (end - start).days
        
        while current_start < end:
            chunk_end = min(current_start + timedelta(days=API_MAX_DAYS_PER_REQUEST - 1), end)
            
            params = {
                "region": region,
                "signal_type": signal_type,
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": chunk_end.strftime("%Y-%m-%dT23:59:00Z"),
            }
            
            resp = requests.get(
                f"{self.base_url}/v3/historical",
                headers=self._headers(),
                params=params
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and data["data"]:
                    all_data.extend(data["data"])
            elif resp.status_code == 429:
                safe_print(f"        ⚠ Rate limited, waiting 10s...")
                time.sleep(10)
                continue  # retry this chunk
            elif resp.status_code == 403:
                safe_print(f"        ✗ Access denied for {signal_type}")
                break
            else:
                safe_print(f"        ⚠ API returned {resp.status_code} for {current_start.date()} to {chunk_end.date()}")
            
            current_start = chunk_end + timedelta(days=1)
            if API_CALL_DELAY > 0:
                time.sleep(API_CALL_DELAY)
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(all_data)
        df["point_time"] = pd.to_datetime(df["point_time"])
        df["region"] = region
        df["signal"] = signal_type
        
        return df
    
    def get_forecast_historical(
        self,
        region: str,
        start: datetime,
        end: datetime,
        signal_type: str = "co2_moer"
    ) -> pd.DataFrame:
        """
        Fetch historical forecasts for a region and time range.
        Returns forecasts organized by when they were generated.
        Limited to 24 hours of generated_at times per request.
        """
        all_data = []
        current_start = start
        total_days = (end - start).days
        
        while current_start < end:
            chunk_end = min(current_start + timedelta(hours=23, minutes=59), end)
            
            params = {
                "region": region,
                "signal_type": signal_type,
                "start": current_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end": chunk_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            
            resp = requests.get(
                f"{self.base_url}/v3/forecast/historical",
                headers=self._headers(),
                params=params
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and data["data"]:
                    for forecast_set in data["data"]:
                        generated_at = forecast_set.get("generated_at")
                        for point in forecast_set.get("forecast", []):
                            point["generated_at"] = generated_at
                            point["region"] = region
                            point["signal"] = signal_type
                            all_data.append(point)
            elif resp.status_code == 429:
                safe_print(f"        ⚠ Rate limited, waiting 10s...")
                time.sleep(10)
                continue  # retry this chunk
            elif resp.status_code == 403:
                safe_print(f"        ✗ Access denied for forecast {signal_type}")
                break
            else:
                safe_print(f"        ⚠ Forecast API returned {resp.status_code} for {current_start}")
            
            # Move to next chunk - fixed to not skip hours
            current_start = chunk_end + timedelta(seconds=1)
            if API_CALL_DELAY > 0:
                time.sleep(API_CALL_DELAY)
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(all_data)
        df["point_time"] = pd.to_datetime(df["point_time"])
        df["generated_at"] = pd.to_datetime(df["generated_at"])
        
        return df


def _split_into_months(start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
    """Split a date range into monthly chunks for incremental saves."""
    months = []
    current = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current < end:
        month_end = (current + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        chunk_start = max(current, start)
        chunk_end = min(month_end, end)
        # Ensure chunk_end includes the full last day
        chunk_end = chunk_end.replace(hour=23, minute=59, second=59)
        months.append((chunk_start, chunk_end))
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def _append_and_save(file_path: Path, new_df: pd.DataFrame, dedup_cols: list, sort_cols: list):
    """Load existing parquet (if any), append new data, deduplicate, and save."""
    if file_path.exists():
        existing_df = pd.read_parquet(file_path)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df
    
    combined = combined.drop_duplicates(subset=dedup_cols).sort_values(sort_cols)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(file_path, index=False)
    return combined


def fetch_and_save_historical(
    client: WattTimeClient,
    signal: str,
    region: str,
    start: datetime,
    end: datetime
) -> bool:
    """
    Fetch historical data and save/append to library.
    Saves incrementally by month. Returns True if successful.
    """
    file_path = get_library_file_path(signal, region, "historical")
    region_start_time = time.time()
    
    # Check what ranges are missing
    missing_ranges = calculate_missing_ranges(signal, region, "historical", start, end)
    
    if not missing_ranges:
        coverage = get_data_coverage(signal, region, "historical")
        safe_print(f"    ✓ Already complete: {coverage[0].date()} to {coverage[1].date()}")
        return True
    
    # Calculate work to do
    total_days_missing = sum((end - start).days for start, end in missing_ranges)
    safe_print(f"    → {total_days_missing} days to fetch across {len(missing_ranges)} gap(s)")
    
    total_saved = 0
    months_processed = 0
    
    for gap_idx, (range_start, range_end) in enumerate(missing_ranges, 1):
        monthly_chunks = _split_into_months(range_start, range_end)
        
        for month_idx, (month_start, month_end) in enumerate(monthly_chunks, 1):
            month_label = month_start.strftime('%Y-%m')
            chunk_start_time = time.time()
            
            safe_print(f"    [{region}] Gap {gap_idx}/{len(missing_ranges)}, Month {month_idx}/{len(monthly_chunks)}: {month_label}...")
            
            df = client.get_historical(region, month_start, month_end, signal)
            
            if len(df) > 0:
                combined = _append_and_save(
                    file_path, df,
                    dedup_cols=["point_time", "region"],
                    sort_cols=["point_time"]
                )
                
                chunk_elapsed = time.time() - chunk_start_time
                total_saved = len(combined)
                months_processed += 1
                
                safe_print(
                    f"        ✓ {month_label}: {len(df):,} new records "
                    f"({chunk_elapsed:.1f}s, {len(df)/chunk_elapsed:.0f} rec/s) "
                    f"→ {total_saved:,} total"
                )
            else:
                safe_print(f"        ✗ {month_label}: No data returned")
    
    if total_saved == 0:
        safe_print(f"    ✗ No data fetched")
        return file_path.exists()
    
    # Final catalog update
    final_df = pd.read_parquet(file_path)
    register_data(
        signal=signal,
        region=region,
        data_type="historical",
        start=final_df["point_time"].min().to_pydatetime(),
        end=final_df["point_time"].max().to_pydatetime(),
        n_records=len(final_df),
        file_path=file_path
    )
    
    region_elapsed = time.time() - region_start_time
    safe_print(
        f"    ✓ Region complete: {total_saved:,} records, "
        f"{months_processed} months, {region_elapsed/60:.1f}min"
    )
    return True


def fetch_and_save_forecast(
    client: WattTimeClient,
    signal: str,
    region: str,
    start: datetime,
    end: datetime
) -> bool:
    """
    Fetch forecast data and save/append to library.
    Saves incrementally by month. Returns True if successful.
    """
    file_path = get_library_file_path(signal, region, "forecast")
    region_start_time = time.time()
    
    # Check what ranges are missing
    missing_ranges = calculate_missing_ranges(signal, region, "forecast", start, end)
    
    if not missing_ranges:
        coverage = get_data_coverage(signal, region, "forecast")
        safe_print(f"    ✓ Already complete: {coverage[0].date()} to {coverage[1].date()}")
        return True
    
    # Calculate work to do
    total_days_missing = sum((end - start).days for start, end in missing_ranges)
    safe_print(f"    → {total_days_missing} days to fetch across {len(missing_ranges)} gap(s)")
    
    total_saved = 0
    months_processed = 0
    
    for gap_idx, (range_start, range_end) in enumerate(missing_ranges, 1):
        monthly_chunks = _split_into_months(range_start, range_end)
        
        for month_idx, (month_start, month_end) in enumerate(monthly_chunks, 1):
            month_label = month_start.strftime('%Y-%m')
            chunk_start_time = time.time()
            
            safe_print(f"    [{region}] Gap {gap_idx}/{len(missing_ranges)}, Month {month_idx}/{len(monthly_chunks)}: {month_label}...")
            
            df = client.get_forecast_historical(region, month_start, month_end, signal)
            
            if len(df) > 0:
                combined = _append_and_save(
                    file_path, df,
                    dedup_cols=["point_time", "generated_at", "region"],
                    sort_cols=["generated_at", "point_time"]
                )
                
                chunk_elapsed = time.time() - chunk_start_time
                total_saved = len(combined)
                months_processed += 1
                
                safe_print(
                    f"        ✓ {month_label}: {len(df):,} new records "
                    f"({chunk_elapsed:.1f}s, {len(df)/chunk_elapsed:.0f} rec/s) "
                    f"→ {total_saved:,} total"
                )
            else:
                safe_print(f"        ✗ {month_label}: No data returned")
    
    if total_saved == 0:
        safe_print(f"    ✗ No forecast data fetched")
        return file_path.exists()
    
    # Final catalog update
    final_df = pd.read_parquet(file_path)
    register_data(
        signal=signal,
        region=region,
        data_type="forecast",
        start=final_df["point_time"].min().to_pydatetime(),
        end=final_df["point_time"].max().to_pydatetime(),
        n_records=len(final_df),
        file_path=file_path
    )
    
    region_elapsed = time.time() - region_start_time
    safe_print(
        f"    ✓ Region complete: {total_saved:,} records, "
        f"{months_processed} months, {region_elapsed/60:.1f}min"
    )
    return True


def _process_region(
    client: WattTimeClient,
    signal: str,
    region: str,
    start: datetime,
    end: datetime,
    data_type: str,
    index: int,
    total: int
) -> Tuple[str, bool]:
    """Process a single region. Used by both sequential and parallel modes."""
    region_name = REGIONS.get(region, {}).get("name", region)
    safe_print(f"\n[{index}/{total}] {region_name} ({region})")
    
    try:
        if data_type == "forecast":
            success = fetch_and_save_forecast(client, signal, region, start, end)
        else:
            success = fetch_and_save_historical(client, signal, region, start, end)
        return region, success
    except Exception as e:
        safe_print(f"    ✗ ERROR: {e}")
        return region, False


def main():
    # Resolve regions from config
    regions = expand_region_group(REGIONS_TO_FETCH)
    
    print("=" * 60)
    print("WATTTIME DATA COLLECTION")
    print("=" * 60)
    print(f"Signal: {SIGNAL} ({SIGNALS[SIGNAL]['name']})")
    print(f"Data type: {DATA_TYPE}")
    print(f"Regions: {len(regions)} regions")
    print(f"Date range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Workers: {MAX_WORKERS} {'(parallel)' if MAX_WORKERS > 1 else '(sequential)'}")
    print(f"API delay: {API_CALL_DELAY}s")
    print("=" * 60)
    
    # Validate signal
    if SIGNAL not in SIGNALS:
        print(f"\nERROR: Unknown signal '{SIGNAL}'")
        print(f"Valid options: {list(SIGNALS.keys())}")
        sys.exit(1)
    
    # Validate data type
    if DATA_TYPE not in ["historical", "forecast"]:
        print(f"\nERROR: Invalid data type '{DATA_TYPE}'")
        print("Valid options: 'historical', 'forecast'")
        sys.exit(1)
    
    # Initialize client
    print("\nAuthenticating...")
    try:
        client = WattTimeClient(WATTTIME_USERNAME, WATTTIME_PASSWORD)
        client._get_token()
        print("  ✓ Authentication successful!")
    except Exception as e:
        print(f"  ✗ Authentication failed: {e}")
        sys.exit(1)
    
    # PRE-FLIGHT CHECK: Analyze data coverage
    print(f"\n{'─' * 60}")
    print("ANALYZING DATA COVERAGE")
    print("─" * 60)
    
    regions_complete = []
    regions_partial = []
    regions_empty = []
    
    for region in regions:
        missing = calculate_missing_ranges(SIGNAL, region, DATA_TYPE, START_DATE, END_DATE)
        region_name = REGIONS.get(region, {}).get("name", region)
        
        if not missing:
            regions_complete.append(region)
            try:
                coverage = get_data_coverage(SIGNAL, region, DATA_TYPE)
                print(f"  ✓ {region_name}: Complete ({coverage[0].date()} to {coverage[1].date()})")
            except:
                print(f"  ✓ {region_name}: Complete")
        else:
            total_days = sum((end - start).days for start, end in missing)
            try:
                coverage = get_data_coverage(SIGNAL, region, DATA_TYPE)
                regions_partial.append((region, total_days))
                print(f"  → {region_name}: {total_days} days missing (have {coverage[0].date()} to {coverage[1].date()})")
            except:
                regions_empty.append((region, total_days))
                print(f"  ○ {region_name}: No data ({total_days} days needed)")
    
    total_days_to_fetch = sum(d for _, d in regions_partial) + sum(d for _, d in regions_empty)
    
    print(f"\nSummary:")
    print(f"  Complete: {len(regions_complete)}")
    print(f"  Partial: {len(regions_partial)}")
    print(f"  Empty: {len(regions_empty)}")
    print(f"  Total days to fetch: {total_days_to_fetch:,}")
    
    if len(regions_complete) == len(regions):
        print("\n✓ All regions already complete! Nothing to do.")
        sys.exit(0)
    
    # Filter to only regions that need work
    regions_to_process = [r for r, _ in regions_partial] + [r for r, _ in regions_empty]
    
    # Fetch data for regions that need it
    print(f"\n{'─' * 60}")
    print(f"FETCHING {DATA_TYPE.upper()} DATA")
    print(f"Processing {len(regions_to_process)} of {len(regions)} regions")
    print("─" * 60)
    
    start_time = time.time()
    success_count = 0
    
    if MAX_WORKERS > 1:
        # Parallel execution
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for i, region in enumerate(regions_to_process, 1):
                future = executor.submit(
                    _process_region,
                    client, SIGNAL, region, START_DATE, END_DATE,
                    DATA_TYPE, i, len(regions_to_process)
                )
                futures[future] = region
            
            for future in as_completed(futures):
                region, success = future.result()
                if success:
                    success_count += 1
    else:
        # Sequential execution
        for i, region in enumerate(regions_to_process, 1):
            _, success = _process_region(
                client, SIGNAL, region, START_DATE, END_DATE,
                DATA_TYPE, i, len(regions_to_process)
            )
            if success:
                success_count += 1
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("COLLECTION COMPLETE")
    print("=" * 60)
    print(f"Regions processed: {success_count}/{len(regions_to_process)}")
    print(f"Regions skipped (complete): {len(regions_complete)}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print(f"Average: {elapsed/len(regions_to_process):.1f}s per region")
    print("\nRun 'python utils/library_manager.py' to see library contents")
    print("=" * 60)


if __name__ == "__main__":
    main()