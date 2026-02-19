import sqlite3
db = sqlite3.connect('db/phone_farm.db')
rows = db.execute("SELECT username, status, start_time, end_time FROM accounts WHERE device_serial = '10.1.10.238_5555' AND status = 'active'").fetchall()
print(f"Active accounts: {len(rows)}")
for r in rows:
    print(r)
