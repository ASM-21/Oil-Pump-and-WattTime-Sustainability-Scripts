"""
WattTime API Test Script
Prints all available data to explore what you can access.
"""

import requests
import os


def get_watttime_credentials():
    """Read WattTime credentials from environment variables."""
    username = os.getenv("WATTTIME_USERNAME")
    password = os.getenv("WATTTIME_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "Set WATTTIME_USERNAME and WATTTIME_PASSWORD before running this script. "
            "See .env.example and docs/SECURITY_AND_SHARING_CHECKLIST.md."
        )
    return username, password

from datetime import datetime, timedelta, timezone

# =============================================================================
# Config
# =============================================================================
USERNAME, PASSWORD = get_watttime_credentials()
REGION = "MISO_LAFAYETTE"  # West Lafayette / Purdue

# =============================================================================
# Auth
# =============================================================================
print("=" * 70)
print("WATTTIME API TEST")
print("=" * 70)

print("\n[1] AUTHENTICATION")
print("-" * 40)

resp = requests.get(
    "https://api.watttime.org/login",
    auth=(USERNAME, PASSWORD)
)
print(f"Status: {resp.status_code}")
token = resp.json().get("token")
print(f"Token: {token[:20]}..." if token else "FAILED")

headers = {"Authorization": f"Bearer {token}"}

# =============================================================================
# Real-time / Forecast
# =============================================================================
print("\n[2] REAL-TIME & FORECAST (co2_moer)")
print("-" * 40)

resp = requests.get(
    "https://api.watttime.org/v3/forecast",
    headers=headers,
    params={"region": REGION, "signal_type": "co2_moer"}
)
print(f"Status: {resp.status_code}")
forecast = resp.json()

meta = forecast.get("meta", {})
print(f"\nRegion: {meta.get('region')} ({meta.get('region_full_name')})")
print(f"Signal: {meta.get('signal_type')}")
print(f"Units: {meta.get('units')}")
print(f"Generated at: {meta.get('generated_at')}")
print(f"Data point interval: {meta.get('data_point_period_seconds')} seconds")

data = forecast.get("data", [])
print(f"\nForecast points: {len(data)}")
print(f"Forecast horizon: {len(data) * 5 / 60:.1f} hours")

# Current (first point)
if data:
    current = data[0]
    print(f"\n>>> CURRENT MOER: {current.get('value'):.2f} lbs CO2/MWh")
    print(f"    Time: {current.get('point_time')}")

# Show first 12 points (1 hour)
print("\nNext 1 hour forecast:")
print(f"{'Time':<25} {'MOER (lbs/MWh)':<15}")
print("-" * 40)
for point in data[:12]:
    print(f"{point.get('point_time'):<25} {point.get('value'):<15.2f}")

# Find optimal time
min_point = min(data, key=lambda x: x.get("value", float("inf")))
max_point = max(data, key=lambda x: x.get("value", float("-inf")))
values = [p.get("value") for p in data]

print(f"\nForecast Statistics:")
print(f"  Min:  {min(values):.2f} at {min_point.get('point_time')}")
print(f"  Max:  {max(values):.2f} at {max_point.get('point_time')}")
print(f"  Mean: {sum(values)/len(values):.2f}")

# =============================================================================
# Historical Data
# =============================================================================
print("\n[3] HISTORICAL DATA (last 24 hours)")
print("-" * 40)

now = datetime.now(timezone.utc)
start = now - timedelta(hours=24)

resp = requests.get(
    "https://api.watttime.org/v3/historical",
    headers=headers,
    params={
        "region": REGION,
        "signal_type": "co2_moer",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
)
print(f"Status: {resp.status_code}")
historical = resp.json()

hist_data = historical.get("data", [])
print(f"Historical points: {len(hist_data)}")

if hist_data:
    hist_values = [p.get("value") for p in hist_data if p.get("value")]
    hist_min = min(hist_data, key=lambda x: x.get("value", float("inf")))
    hist_max = max(hist_data, key=lambda x: x.get("value", float("-inf")))

    print(f"\nLast 24h Statistics:")
    print(f"  Min:  {min(hist_values):.2f} at {hist_min.get('point_time')}")
    print(f"  Max:  {max(hist_values):.2f} at {hist_max.get('point_time')}")
    print(f"  Mean: {sum(hist_values)/len(hist_values):.2f}")

    # Show hourly samples
    print("\nHourly samples (last 24h):")
    print(f"{'Time':<25} {'MOER (lbs/MWh)':<15}")
    print("-" * 40)
    for i, point in enumerate(hist_data):
        if i % 12 == 0:  # Every hour (12 x 5min = 60min)
            print(f"{point.get('point_time'):<25} {point.get('value'):<15.2f}")

# =============================================================================
# Region Lookup (from coordinates)
# =============================================================================
print("\n[4] REGION LOOKUP (Purdue coordinates)")
print("-" * 40)

# Purdue University coordinates
lat, lon = 40.4237, -86.9212

resp = requests.get(
    "https://api.watttime.org/v3/region-from-loc",
    headers=headers,
    params={
        "latitude": lat,
        "longitude": lon,
        "signal_type": "co2_moer"
    }
)
print(f"Status: {resp.status_code}")
region_info = resp.json()
print(f"Coordinates: {lat}, {lon}")
print(f"Region: {region_info.get('region')}")
print(f"Full name: {region_info.get('region_full_name')}")

# =============================================================================
# Carbon Calculation Example
# =============================================================================
print("\n[5] CARBON CALCULATION EXAMPLE")
print("-" * 40)

# Example: CNC machining operation
operation_kwh = 2.5  # kWh consumed
current_moer = data[0].get("value") if data else 0
optimal_moer = min(values) if values else 0

# Convert lbs CO2/MWh to kg CO2/kWh
# 1 lb = 0.453592 kg, 1 MWh = 1000 kWh
current_kg_per_kwh = current_moer * 0.453592 / 1000
optimal_kg_per_kwh = optimal_moer * 0.453592 / 1000

print(f"Example CNC operation: {operation_kwh} kWh")
print(f"\nIf manufactured NOW ({current_moer:.1f} lbs/MWh):")
print(f"  Carbon footprint: {operation_kwh * current_kg_per_kwh:.4f} kg CO2")

print(f"\nIf manufactured at OPTIMAL time ({optimal_moer:.1f} lbs/MWh):")
print(f"  Carbon footprint: {operation_kwh * optimal_kg_per_kwh:.4f} kg CO2")

savings_kg = operation_kwh * (current_kg_per_kwh - optimal_kg_per_kwh)
savings_pct = (1 - optimal_moer / current_moer) * 100 if current_moer > 0 else 0
print(f"\nPotential savings: {savings_kg:.4f} kg CO2 ({savings_pct:.1f}%)")

# =============================================================================
# Signal Index (relative percentile)
# =============================================================================
print("\n[6] SIGNAL INDEX (relative percentile)")
print("-" * 40)

resp = requests.get(
    "https://api.watttime.org/v3/signal-index",
    headers=headers,
    params={"region": REGION, "signal_type": "co2_moer"}
)
print(f"Status: {resp.status_code}")
signal = resp.json()

sig_data = signal.get("data", [{}])[0]
print(f"Percentile: {sig_data.get('value')}%")
print(f"  (0% = cleanest the grid gets, 100% = dirtiest)")
print(f"Time: {sig_data.get('point_time')}")

# =============================================================================
# Health Damage Signal (if available)
# =============================================================================
print("\n[7] HEALTH DAMAGE SIGNAL")
print("-" * 40)

resp = requests.get(
    "https://api.watttime.org/v3/forecast",
    headers=headers,
    params={"region": REGION, "signal_type": "health_damage"}
)
print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    health = resp.json()
    health_meta = health.get("meta", {})
    health_data = health.get("data", [])

    print(f"Signal: {health_meta.get('signal_type')}")
    print(f"Units: {health_meta.get('units')}")

    if health_data:
        print(f"Current: {health_data[0].get('value')}")
else:
    print("Health damage signal not available for this region")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"""
Region: {REGION} ({meta.get('region_full_name')})

Current Grid Status:
  MOER: {current.get('value'):.2f} lbs CO2/MWh
  Percentile: {sig_data.get('value')}% (lower = cleaner)

Forecast ({len(data) * 5 / 60:.0f}h horizon):
  Best time to manufacture: {min_point.get('point_time')}
  Best MOER: {min(values):.2f} lbs CO2/MWh

  Worst time: {max_point.get('point_time')}
  Worst MOER: {max(values):.2f} lbs CO2/MWh

For your research:
  - Use /v3/historical with your operation timestamps to get exact MOER
  - Multiply: energy (kWh) × MOER × 0.000453592 = kg CO2
  - Compare to Ecoinvent static factors
""")
