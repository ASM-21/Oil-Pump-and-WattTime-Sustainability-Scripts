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
token = resp.json()["token"]
print("Token:", token[:20] + "...")

resp = requests.get(
    "https://api.watttime.org/v3/forecast",
    headers={"Authorization": f"Bearer {token}"},
    params={"region": "CAISO_NORTH", "signal_type": "co2_moer"}
)
print("Status:", resp.status_code)
print("Response:", resp.text[:500])
