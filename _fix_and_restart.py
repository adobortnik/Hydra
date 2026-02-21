import sqlite3

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Find stuck entries
rows = conn.execute("SELECT device_serial, status, pid FROM bot_status WHERE status != 'stopped'").fetchall()
print(f"Stuck bot_status entries: {len(rows)}")
for r in rows:
    print(f"  {r['device_serial']}: status={r['status']}, pid={r['pid']}")

# Fix all to stopped
if rows:
    conn.execute("UPDATE bot_status SET status='stopped', pid=NULL WHERE status != 'stopped'")
    conn.commit()
    print(f"Fixed {len(rows)} entries -> stopped")
else:
    print("All clean!")

conn.close()
