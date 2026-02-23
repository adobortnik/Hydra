"""Create a report job order for testing."""
import requests
import sqlite3
import os

BASE = "http://localhost:5055"
AUTH = ("admin", "hydra2026")
DB = os.path.join(os.path.dirname(__file__), 'db', 'phone_farm.db')

# Get some jagger account IDs from device 184
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
accounts = conn.execute("""
    SELECT id, username FROM accounts 
    WHERE device_serial='10.1.10.184_5555' AND tag='jagger' AND status='active'
    LIMIT 3
""").fetchall()
conn.close()

account_ids = [a['id'] for a in accounts]
print(f"Accounts to assign: {[(a['id'], a['username']) for a in accounts]}")

# Pick a random user to report - search for someone NOT in our DB
# Use a random common username that's definitely not ours
target_user = "test_spam_page_2026"  # random target

# Create report job
print(f"\nCreating report job for @{target_user}...")
r = requests.post(f"{BASE}/api/jobs-v2", auth=AUTH, json={
    "job_name": "Test Report",
    "job_type": "report",
    "target": target_user,
    "target_count": 2,
    "report_reason": "spam",
    "limit_per_hour": 10,
    "limit_per_day": 50,
    "accounts": account_ids
})
print(f"Report job: {r.status_code} {r.json()}")

if r.status_code == 201:
    print(f"\nReport job created! ID: {r.json().get('id')}")
    print(f"Assigned {r.json().get('assigned')} accounts")
    print(f"Target: @{target_user} | Reason: spam | Count: 2")
