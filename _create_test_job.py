"""
Create a test follow job order for ROBIN 1 accounts.
Small target (5 follows) to verify the pipeline works.
"""
import sqlite3, sys, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB = 'db/phone_farm.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Create the job order
now = datetime.datetime.utcnow().isoformat()
cursor = conn.execute("""
    INSERT INTO job_orders (job_name, job_type, target, target_count,
                            limit_per_hour, limit_per_day,
                            priority, status, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
""", (
    'TEST: Follow robin.rieff fans',   # job_name
    'follow',                           # job_type
    'robin.rieff',                      # target account to follow from
    10,                                 # target_count (small test)
    50,                                 # limit_per_hour
    200,                                # limit_per_day
    1,                                  # priority (high)
    now, now
))
job_id = cursor.lastrowid
print(f"Created job order #{job_id}")

# Assign 3 ROBIN 1 accounts (not all 12 - just a test)
robin_accounts = conn.execute("""
    SELECT id, username, device_serial
    FROM accounts
    WHERE device_serial = '10.1.10.238_5555'
    ORDER BY username
    LIMIT 3
""").fetchall()

assigned = 0
for acc in robin_accounts:
    try:
        conn.execute("""
            INSERT INTO job_assignments (job_id, account_id, device_serial, username, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (job_id, acc['id'], acc['device_serial'], acc['username'], now))
        assigned += 1
        print(f"  Assigned: {acc['username']} (id={acc['id']})")
    except Exception as e:
        print(f"  Failed to assign {acc['username']}: {e}")

conn.commit()
print(f"\nJob #{job_id} created with {assigned} assignments")
print("Bot engine should pick this up on next cycle when started")

# Verify
job = conn.execute("SELECT * FROM job_orders WHERE id = ?", (job_id,)).fetchone()
print(f"\nJob details: {dict(job)}")

assignments = conn.execute("SELECT * FROM job_assignments WHERE job_id = ?", (job_id,)).fetchall()
for a in assignments:
    print(f"  Assignment: {a['username']} status={a['status']}")

conn.close()
