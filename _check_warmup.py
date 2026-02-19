import sqlite3
db = sqlite3.connect('db/phone_farm.db')
row = db.execute("SELECT username, warmup, warmup_until FROM accounts WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'").fetchone()
print(f"username={row[0]}, warmup={row[1]}, warmup_until={row[2]}")
