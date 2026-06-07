"""
Export all WattTime regions available to your research license.
Checks: co2_moer (marginal), co2_aoer (average), health_damage
Output: CSV with all regions and signal type availability
"""

import requests
import csv
from collections import defaultdict

USERNAME = "ASM21_purdue"
PASSWORD = "Mango21!"

# Authenticate
print("Authenticating...")
resp = requests.get(
    "https://api.watttime.org/login",
    auth=(USERNAME, PASSWORD)
)
resp.raise_for_status()
token = resp.json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# Get access info
print("Fetching available regions...")
resp = requests.get(
    "https://api.watttime.org/v3/my-access",
    headers=headers
)
resp.raise_for_status()
access = resp.json()

# Signal types we care about
target_signals = ["co2_moer", "co2_aoer", "health_damage"]

# Build region data: {region_code: {region_full_name, parent, signal_types: set()}}
regions_data = defaultdict(lambda: {"region_full_name": "", "parent": "", "signal_types": set()})

for signal_group in access.get("signal_types", []):
    signal_type = signal_group.get("signal_type")
    if signal_type not in target_signals:
        continue
    
    regions = signal_group.get("regions", [])
    print(f"  {signal_type}: {len(regions)} regions")
    
    for r in regions:
        code = r.get("region", "")
        regions_data[code]["region_full_name"] = r.get("region_full_name", "")
        regions_data[code]["parent"] = r.get("parent", "")
        regions_data[code]["signal_types"].add(signal_type)

# Write to CSV
output_file = "watttime_regions.csv"
with open(output_file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "region_code", 
        "region_full_name", 
        "parent",
        "co2_moer", 
        "co2_aoer", 
        "health_damage"
    ])
    
    for code in sorted(regions_data.keys()):
        data = regions_data[code]
        writer.writerow([
            code,
            data["region_full_name"],
            data["parent"],
            "Y" if "co2_moer" in data["signal_types"] else "",
            "Y" if "co2_aoer" in data["signal_types"] else "",
            "Y" if "health_damage" in data["signal_types"] else ""
        ])

print(f"\nExported {len(regions_data)} unique regions to {output_file}")

# Summary
print("\nSummary by signal type:")
for sig in target_signals:
    count = sum(1 for d in regions_data.values() if sig in d["signal_types"])
    print(f"  {sig}: {count} regions")