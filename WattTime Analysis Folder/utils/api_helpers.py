"""
API Helpers - Region Lookup and Signal Availability

Utilities for querying WattTime API to:
- Look up region codes from coordinates
- Check signal availability for regions
- Verify region boundaries haven't changed
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    WATTTIME_USERNAME, WATTTIME_PASSWORD, WATTTIME_BASE_URL,
    REGIONS, SIGNALS, LIBRARY_DIR
)


class WattTimeAPI:
    """Simple WattTime API client for utility operations."""
    
    def __init__(self):
        self.base_url = WATTTIME_BASE_URL
        self.token = None
        self.token_time = None
    
    def _get_token(self) -> str:
        """Get or refresh authentication token."""
        if self.token and self.token_time:
            age = (datetime.now() - self.token_time).total_seconds() / 60
            if age < 25:
                return self.token
        
        resp = requests.get(
            f"{self.base_url}/login",
            auth=(WATTTIME_USERNAME, WATTTIME_PASSWORD)
        )
        resp.raise_for_status()
        self.token = resp.json()["token"]
        self.token_time = datetime.now()
        return self.token
    
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}
    
    def get_region_from_coords(self, lat: float, lon: float, signal: str = "co2_moer") -> dict:
        """
        Look up region code from coordinates.
        
        Returns dict with region info or error.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "signal_type": signal,
        }
        
        resp = requests.get(
            f"{self.base_url}/v3/region-from-loc",
            headers=self._headers(),
            params=params
        )
        
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": resp.status_code, "message": resp.text}
    
    def check_signal_availability(self, region: str, signal: str) -> dict:
        """
        Check if a signal is available for a region.
        
        Returns dict with availability info.
        """
        # Try to get a small sample of data
        params = {
            "region": region,
            "signal_type": signal,
            "start": "2024-01-01T00:00:00Z",
            "end": "2024-01-01T01:00:00Z",
        }
        
        resp = requests.get(
            f"{self.base_url}/v3/historical",
            headers=self._headers(),
            params=params
        )
        
        if resp.status_code == 200:
            data = resp.json()
            has_data = "data" in data and len(data.get("data", [])) > 0
            return {
                "available": has_data,
                "region": region,
                "signal": signal,
                "sample_size": len(data.get("data", [])) if has_data else 0,
            }
        elif resp.status_code == 403:
            return {
                "available": False,
                "region": region,
                "signal": signal,
                "error": "Access denied - signal may not be available for this region or subscription",
            }
        else:
            return {
                "available": False,
                "region": region,
                "signal": signal,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
            }
    
    def list_available_signals(self, region: str) -> List[dict]:
        """Check which signals are available for a region."""
        results = []
        
        for signal in SIGNALS.keys():
            result = self.check_signal_availability(region, signal)
            results.append(result)
        
        return results


def verify_region_codes() -> None:
    """
    Verify that configured region codes still match coordinates.
    Useful when WattTime updates their region boundaries.
    """
    print("=" * 60)
    print("REGION CODE VERIFICATION")
    print("=" * 60)
    
    api = WattTimeAPI()
    
    for region_code, metadata in REGIONS.items():
        coords = metadata.get("coordinates", (0, 0))
        name = metadata.get("name", region_code)
        
        print(f"\n{name} ({region_code}):")
        print(f"  Configured coords: {coords[0]:.4f}, {coords[1]:.4f}")
        
        # Check for MOER (most common)
        result = api.get_region_from_coords(coords[0], coords[1], "co2_moer")
        
        if "error" in result:
            print(f"  ERROR: {result.get('message', 'Unknown error')}")
            continue
        
        api_region = result.get("region")
        
        if api_region == region_code:
            print(f"  ✓ Region matches: {api_region}")
        else:
            print(f"  ⚠ MISMATCH! API returns: {api_region}")
            print(f"    Config has: {region_code}")
            print(f"    You may need to update config.py")


def check_all_signal_availability() -> None:
    """Check signal availability for all configured regions."""
    print("=" * 60)
    print("SIGNAL AVAILABILITY CHECK")
    print("=" * 60)
    
    api = WattTimeAPI()
    
    # Build availability matrix
    results = {}
    
    for region_code in REGIONS.keys():
        region_name = REGIONS[region_code].get("name", region_code)
        print(f"\nChecking {region_name}...")
        
        results[region_code] = {}
        
        for signal in SIGNALS.keys():
            result = api.check_signal_availability(region_code, signal)
            results[region_code][signal] = result["available"]
            
            status = "✓" if result["available"] else "✗"
            print(f"  {signal}: {status}")
    
    # Print summary matrix
    print("\n" + "=" * 60)
    print("AVAILABILITY MATRIX")
    print("=" * 60)
    
    # Header
    signals = list(SIGNALS.keys())
    header = "Region".ljust(25) + "".join(s[:12].center(14) for s in signals)
    print(header)
    print("-" * len(header))
    
    for region_code, signal_avail in results.items():
        region_name = REGIONS[region_code].get("name", region_code)[:24]
        row = region_name.ljust(25)
        for signal in signals:
            status = "✓" if signal_avail.get(signal) else "✗"
            row += status.center(14)
        print(row)
    
    # Save results
    output_path = LIBRARY_DIR / "signal_availability.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output = {
        "checked_at": datetime.now().isoformat(),
        "availability": results,
    }
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved to: {output_path}")


def lookup_region(lat: float, lon: float) -> None:
    """Look up region code for arbitrary coordinates."""
    print(f"Looking up region for ({lat}, {lon})...")
    
    api = WattTimeAPI()
    
    for signal in SIGNALS.keys():
        result = api.get_region_from_coords(lat, lon, signal)
        
        if "error" in result:
            print(f"  {signal}: Error - {result.get('message', 'Unknown')[:50]}")
        else:
            region = result.get("region", "Unknown")
            region_name = result.get("region_full_name", "")
            print(f"  {signal}: {region} ({region_name})")


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="WattTime API helpers")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Verify regions command
    subparsers.add_parser("verify", help="Verify configured region codes")
    
    # Check availability command
    subparsers.add_parser("availability", help="Check signal availability for all regions")
    
    # Lookup command
    lookup_parser = subparsers.add_parser("lookup", help="Look up region for coordinates")
    lookup_parser.add_argument("lat", type=float, help="Latitude")
    lookup_parser.add_argument("lon", type=float, help="Longitude")
    
    args = parser.parse_args()
    
    if args.command == "verify":
        verify_region_codes()
    elif args.command == "availability":
        check_all_signal_availability()
    elif args.command == "lookup":
        lookup_region(args.lat, args.lon)
    else:
        parser.print_help()
