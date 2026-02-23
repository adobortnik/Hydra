"""Setup multiple accounts for testing different features.
- jaggerplays: comment + DM specific user (@camillo_bro)  
- jaggerdominates: DM new followers
- jaggerplayboy: comment with keyword search
"""
import requests
import sqlite3
import os

BASE = "http://localhost:5055"
AUTH = ("admin", "hydra2026")
SERIAL = "10.1.10.184_5555"

# 1. jaggerplays - already set up (comment + DM specific)
print("=== jaggerplays (comment + DM specific) ===")
r = requests.get(f"{BASE}/api/bot-settings/{SERIAL}/jaggerplays", auth=AUTH)
s = r.json().get('settings', {})
print(f"  enable_comment = {s.get('enable_comment')}")
print(f"  enable_directmessage = {s.get('enable_directmessage')}")
print(f"  dm method = {s.get('directmessage_method')}")
print(f"  comment_text = {s.get('comment_text')}")

# 2. jaggerdominates - DM new followers
print("\n=== jaggerdominates (DM new followers) ===")
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/jaggerdominates", auth=AUTH, json={
    "enable_directmessage": True,
    "directmessage_method": {
        "directmessage_specificuser": False,
        "directmessage_new_followers": True,
        "directmessage_reply": False,
        "enable_dm_crm": False
    },
    "directmessage_min": "1",
    "directmessage_max": "2",
    "directmessage_daily_limit": "10"
})
print(f"  Update: {r.status_code}")
s2 = r.json().get('settings', {})
print(f"  enable_directmessage = {s2.get('enable_directmessage')}")
print(f"  dm method = {s2.get('directmessage_method')}")

# Set DM message for new followers
DB = os.path.join(os.path.dirname(__file__), 'db', 'phone_farm.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
acc = conn.execute("SELECT id FROM accounts WHERE username='jaggerdominates'").fetchone()
if acc:
    aid = acc['id']
    existing = conn.execute("SELECT id FROM account_text_configs WHERE account_id=? AND config_type='pm_list'", (aid,)).fetchone()
    msg = "Hey! Love your content, keep it up!"
    if existing:
        conn.execute("UPDATE account_text_configs SET content=? WHERE account_id=? AND config_type='pm_list'", (msg, aid))
    else:
        conn.execute("INSERT INTO account_text_configs (account_id, config_type, content) VALUES (?, 'pm_list', ?)", (aid, msg))
    conn.commit()
    print(f"  PM list set: '{msg}'")
conn.close()

print("\n=== Summary ===")
print("jaggerplays:     comment ON + DM to @camillo_bro")
print("jaggerdominates: DM new followers ON")
print("\nBot will pick these up on next cycle (~30-40 min)")
print("Monitor with: Get-Content logs/10.1.10.184_5555_2026-02-22.log -Tail 50 -Wait")
