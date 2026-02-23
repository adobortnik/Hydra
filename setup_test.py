"""Configure jaggerplays for comment, DM, and report testing via API."""
import requests
import json

BASE = "http://localhost:5055"
AUTH = ("admin", "hydra2026")
SERIAL = "10.1.10.184_5555"
ACCOUNT = "jaggerplays"

# 1. Enable commenting
print("=== Enabling Comment ===")
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}", auth=AUTH, json={
    "settings": {
        "comment_text": "Amazing content! Keep it up"
    },
    "toggles": {
        "comment_enabled": "True"
    }
})
print(f"Comment: {r.status_code} {r.json()}")

# 2. Enable DM to specific user (@camillo_bro)
print("\n=== Enabling DM to @camillo_bro ===")
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}", auth=AUTH, json={
    "settings": {
        "directmessage_method": {
            "directmessage_specificuser": True,
            "directmessage_new_followers": False,
            "directmessage_reply": False,
            "enable_dm_crm": False
        },
        "directmessage_daily_limit": "25",
        "directmessage_min": "1",
        "directmessage_max": "1"
    },
    "toggles": {
        "dm_enabled": "True"
    }
})
print(f"DM settings: {r.status_code} {r.json()}")

# Set DM target list to @camillo_bro
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}/lists/dm_targets", auth=AUTH, json={
    "items": ["camillo_bro"]
})
print(f"DM targets: {r.status_code} {r.json()}")

# Set DM message template  
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}/prompts/pm_list", auth=AUTH, json={
    "content": "Hey bro, looking good"
})
print(f"DM message: {r.status_code} {r.json()}")

# 3. Check job orders for report
print("\n=== Job Orders (Report) ===")
# Check what endpoints exist for job orders
r = requests.get(f"{BASE}/api/job-orders-v2", auth=AUTH)
print(f"Job orders list: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"  Orders: {len(data.get('orders', data.get('jobs', [])))} existing")

print("\nDone! Settings updated. Bot will pick them up on next cycle.")
print("Comment: enabled with text 'Amazing content! Keep it up'")
print("DM: enabled to @camillo_bro with message 'Hey bro, looking good'")
