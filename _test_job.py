"""
Test Job Orders integration with bot engine.
Creates a small 'follow' job targeting ROBIN 1 accounts.
"""
import sqlite3, json, sys, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB = 'db/phone_farm.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# 1. Get ROBIN 1 accounts
robin1 = conn.execute("""
    SELECT a.id, a.username, a.device_serial, a.tag, a.status
    FROM accounts a
    WHERE a.device_serial = '10.1.10.238_5555'
    ORDER BY a.username
""").fetchall()

print(f"ROBIN 1 accounts: {len(robin1)}")
for a in robin1:
    print(f"  [{a['id']}] {a['username']} tag={a['tag']} status={a['status']}")

# 2. Check existing active jobs
jobs = conn.execute("SELECT * FROM job_orders WHERE status = 'active'").fetchall()
print(f"\nExisting active jobs: {len(jobs)}")
for j in jobs:
    print(f"  #{j['id']} {j['job_name']} ({j['job_type']}) target=@{j['target']} {j['completed_count']}/{j['target_count']}")

# 3. Check existing assignments for ROBIN 1 accounts
robin_ids = [a['id'] for a in robin1]
assignments = conn.execute(f"""
    SELECT ja.*, jo.job_name, jo.job_type, jo.status as job_status
    FROM job_assignments ja
    JOIN job_orders jo ON ja.job_id = jo.id
    WHERE ja.account_id IN ({','.join('?' * len(robin_ids))})
""", robin_ids).fetchall()
print(f"\nExisting assignments for ROBIN 1: {len(assignments)}")
for a in assignments:
    print(f"  {a['username']} -> job#{a['job_id']} {a['job_name']} ({a['job_type']}) status={a['status']} done={a['completed_count']}")

# 4. Check bot running status (log files)
import os, time
log_dir = os.path.join('logs')
robin_serial = '10.1.10.238_5555'
log_file = os.path.join(log_dir, f'{robin_serial}.log')
if os.path.exists(log_file):
    mtime = os.path.getmtime(log_file)
    age_min = (time.time() - mtime) / 60
    print(f"\nBot log age: {age_min:.1f} minutes ago")
    if age_min < 10:
        print("Bot is ACTIVE")
    else:
        print("Bot is NOT active (log too old)")
else:
    print(f"\nNo log file found at {log_file}")

# 5. Check job_history for any recent entries
history = conn.execute("""
    SELECT jh.*, a.username 
    FROM job_history jh
    LEFT JOIN accounts a ON a.id = jh.account_id
    ORDER BY jh.created_at DESC LIMIT 10
""").fetchall()
print(f"\nRecent job history: {len(history)} entries")
for h in history:
    print(f"  job#{h['job_id']} {h['username']} {h['action_type']} {h['status']} {h['created_at']}")

conn.close()
