import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Job status
job = conn.execute("SELECT * FROM job_orders WHERE id = 3").fetchone()
print(f"Job #3: status={job['status']} completed={job['completed_count']}/{job['target_count']}")

# Assignments
for a in conn.execute("SELECT * FROM job_assignments WHERE job_id = 3").fetchall():
    print(f"  {a['username']}: status={a['status']} done={a['completed_count']}")

# History
history = conn.execute("SELECT * FROM job_history WHERE job_id = 3 ORDER BY created_at DESC LIMIT 10").fetchall()
print(f"\nHistory entries: {len(history)}")
for h in history:
    print(f"  {h['created_at']} {h['action_type']} {h['status']} {h['error_message'] or ''}")

# Check which account is currently active (time window)
import datetime
hour = datetime.datetime.now().hour
print(f"\nCurrent hour: {hour}")
accs = conn.execute("""
    SELECT a.id, a.username, a.start_time, a.end_time 
    FROM accounts a WHERE a.device_serial = '10.1.10.238_5555'
    ORDER BY a.start_time
""").fetchall()
for a in accs:
    st = int(a['start_time'] or 0)
    et = int(a['end_time'] or 24)
    active = "<<< ACTIVE" if st <= hour < et else ""
    assigned = " [JOB ASSIGNED]" if a['id'] in (325, 327, 329) else ""
    print(f"  {a['username']} ({st}h-{et}h) {active}{assigned}")

conn.close()
