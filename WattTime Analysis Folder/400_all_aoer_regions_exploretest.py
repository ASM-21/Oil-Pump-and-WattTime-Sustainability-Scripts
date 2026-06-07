"""
Quick test: verify co2_aoer access for all 6 regions.
Attempts a tiny 1-day historical pull for each.
"""

import requests
from datetime import datetime

# ── Config ──────────────────────────────────────────────
USERNAME = "ASM21_purdue"
PASSWORD = "Mango21!"
BASE_URL = "https://api.watttime.org"

REGIONS = ["MISO", "BPA", "CAISO", "SPP", "ERCOT", "ISONE"]
SIGNAL = "co2_aoer"
TEST_START = "2024-01-01T00:00:00Z"
TEST_END = "2024-01-02T00:00:00Z"
# ────────────────────────────────────────────────────────

# Auth
token = requests.get(f"{BASE_URL}/login", auth=(USERNAME, PASSWORD)).json()["token"]
headers = {"Authorization": f"Bearer {token}"}

# 1) Check my-access for AOER
print("=" * 60)
print("CHECKING /v3/my-access for co2_aoer")
print("=" * 60)
access = requests.get(f"{BASE_URL}/v3/my-access", headers=headers, params={"signal_type": SIGNAL})
if access.status_code == 200:
    data = access.json()
    for st in data.get("signal_types", []):
        if st["signal_type"] == SIGNAL:
            available = [r["region"] for r in st.get("regions", [])]
            print(f"Account has AOER access to {len(available)} regions:")
            for r in available:
                tag = " ← YOURS" if r in REGIONS else ""
                print(f"  {r}{tag}")
            missing = set(REGIONS) - set(available)
            if missing:
                print(f"\n⚠ NOT in your access: {missing}")
            else:
                print(f"\n✓ All 6 target regions found in access list")
else:
    print(f"my-access returned {access.status_code}: {access.text[:200]}")

# 2) Test a 1-day pull for each region
print(f"\n{'=' * 60}")
print(f"TESTING 1-DAY HISTORICAL PULL ({TEST_START[:10]})")
print("=" * 60)
for region in REGIONS:
    resp = requests.get(
        f"{BASE_URL}/v3/historical",
        headers=headers,
        params={
            "region": region,
            "signal_type": SIGNAL,
            "start": TEST_START,
            "end": TEST_END,
        },
    )
    if resp.status_code == 200:
        records = resp.json().get("data", [])
        meta = resp.json().get("meta", {})
        units = meta.get("units", "?")
        period = meta.get("data_point_period_seconds", "?")
        print(f"  ✓ {region:8s} → {len(records):4d} records  ({period}s intervals, {units})")
    else:
        print(f"  ✗ {region:8s} → HTTP {resp.status_code}: {resp.text[:120]}")