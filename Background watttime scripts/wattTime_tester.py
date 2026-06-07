import requests

resp = requests.get("https://api.watttime.org/login", auth=("ASM21_purdue", "Mango21!"))
token = resp.json()["token"]
print("Token:", token[:20] + "...")

resp = requests.get(
    "https://api.watttime.org/v3/forecast",
    headers={"Authorization": f"Bearer {token}"},
    params={"region": "CAISO_NORTH", "signal_type": "co2_moer"}
)
print("Status:", resp.status_code)
print("Response:", resp.text[:500])