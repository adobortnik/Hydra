"""Set DM targets and message for jaggerplays."""
import requests

BASE = "http://localhost:5055"
AUTH = ("admin", "hydra2026")
SERIAL = "10.1.10.184_5555"
ACCOUNT = "jaggerplays"

# Set DM specific users list (contains @camillo_bro)
print("=== Setting DM specific users ===")
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}/lists/dm_specific_users", auth=AUTH, json={
    "items": ["camillo_bro"]
})
print(f"DM targets: {r.status_code} {r.json()}")

# Set DM message as text config (comments_list / pm_list)
# Check what text configs exist
print("\n=== Setting DM message template ===")
r = requests.post(f"{BASE}/api/bot-settings/{SERIAL}/{ACCOUNT}/prompts/dm_specific_users_prompt", auth=AUTH, json={
    "content": "Hey bro, looking good"
})
print(f"DM prompt: {r.status_code} {r.json()}")

# Also set the pm_list (account_text_configs)
# The DM module reads from account_text_configs.pm_list
import sqlite3
import os
DB = os.path.join(os.path.dirname(__file__), 'db', 'phone_farm.db')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Get account ID
acc = conn.execute("SELECT id FROM accounts WHERE username='jaggerplays'").fetchone()
if acc:
    aid = acc['id']
    # Check if pm_list exists
    existing = conn.execute("SELECT id FROM account_text_configs WHERE account_id=? AND config_type='pm_list'", (aid,)).fetchone()
    if existing:
        conn.execute("UPDATE account_text_configs SET content='Hey bro, looking good' WHERE account_id=? AND config_type='pm_list'", (aid,))
    else:
        conn.execute("INSERT INTO account_text_configs (account_id, config_type, content) VALUES (?, 'pm_list', 'Hey bro, looking good')", (aid,))
    conn.commit()
    print(f"PM list set for account_id={aid}")

    # Also set comments_list
    existing_c = conn.execute("SELECT id FROM account_text_configs WHERE account_id=? AND config_type='comments_list'", (aid,)).fetchone()
    if existing_c:
        conn.execute("UPDATE account_text_configs SET content='Amazing content! Keep it up' WHERE account_id=? AND config_type='comments_list'", (aid,))
    else:
        conn.execute("INSERT INTO account_text_configs (account_id, config_type, content) VALUES (?, 'comments_list', 'Amazing content! Keep it up')", (aid,))
    conn.commit()
    print(f"Comments list set for account_id={aid}")

conn.close()

# Now create a job order for REPORT
print("\n=== Creating Report Job Order ===")
# Check job orders v2 routes
import requests
r = requests.get(f"{BASE}/api/job-orders", auth=AUTH)
print(f"Job orders endpoint: {r.status_code}")

# Try v2
r = requests.get(f"{BASE}/api/jobs", auth=AUTH)
print(f"Jobs endpoint: {r.status_code}")

print("\nAll settings configured!")
