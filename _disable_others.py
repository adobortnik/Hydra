import sqlite3
db = sqlite3.connect('db/phone_farm.db')
db.execute("UPDATE accounts SET status = 'disabled' WHERE device_serial = '10.1.10.238_5555' AND username != 'rieff_real'")
db.commit()
rows = db.execute("SELECT username, status FROM accounts WHERE device_serial = '10.1.10.238_5555' AND status = 'active'").fetchall()
print(f"Active: {len(rows)}")
for r in rows:
    print(r)
