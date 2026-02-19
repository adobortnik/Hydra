import sqlite3, datetime

db = sqlite3.connect('db/phone_farm.db')
db.row_factory = sqlite3.Row

# Simulate what bot engine does
username = 'rieff_real'
device_serial = '10.1.10.238_5555'
now = datetime.datetime.now().isoformat()

print(f"Checking: username={username}, device={device_serial}, now={now}")

rows = db.execute("""
    SELECT * FROM content_schedule
    WHERE username = ? AND device_serial = ?
    AND status = 'pending' AND scheduled_time <= ?
    ORDER BY scheduled_time ASC
    LIMIT 1
""", (username, device_serial, now)).fetchall()

print(f"Found: {len(rows)} rows")
for r in rows:
    print(dict(r))

# Also check all entries for this device
print("\nAll entries for this device:")
all_rows = db.execute("SELECT id, username, content_type, scheduled_time, status FROM content_schedule WHERE device_serial = ?", (device_serial,)).fetchall()
for r in all_rows:
    print(dict(r))
