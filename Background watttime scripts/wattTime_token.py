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

# Login
resp = requests.get(
    "https://api.watttime.org/login",
    auth=(USERNAME, PASSWORD)
)
print("Login status:", resp.status_code)
token = resp.json().get("token")

# Save token to file
with open("WattTime_token.txt", "w") as f:
    f.write(token)
print("Token saved to WattTime_token.txt")

headers = {"Authorization": f"Bearer {token}"}

# Test signal index
print("--- Signal Index ---")
resp = requests.get(
    "https://api.watttime.org/v3/signal-index",
    headers=headers,
    params={
        "region": "CAISO_NORTH",
        "signal_type": "co2_moer"
    }
)
print("Status:", resp.status_code)
print("Response:", resp.json())
