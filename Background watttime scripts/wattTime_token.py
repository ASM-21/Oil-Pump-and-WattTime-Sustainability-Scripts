import requests

USERNAME = "ASM21_purdue"
PASSWORD = "Mango21!"

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