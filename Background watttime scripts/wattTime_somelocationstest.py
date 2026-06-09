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

USERNAME, PASSWORD = get_watttime_credentials()
resp = requests.get("https://api.watttime.org/login", auth=(USERNAME, PASSWORD))
token = resp.json().get("token")
headers = {"Authorization": f"Bearer {token}"}

for name, coords in [("PJM_Philly", (39.95, -75.16)),
                      ("ERCOT_Houston", (29.76, -95.37)),
                      ("ISONE_Boston", (42.36, -71.06))]:
    r = requests.get("https://api.watttime.org/v3/region-from-loc",
                     headers=headers,
                     params={"latitude": coords[0], "longitude": coords[1], "signal_type": "co2_moer"})
    print(f"{name}: {r.json()}")
