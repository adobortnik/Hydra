import sqlite3
db = sqlite3.connect('db/phone_farm.db')

# Fix rieff_real: use plain hour numbers, not HH:MM format
db.execute("""UPDATE accounts SET start_time = '4', end_time = '11' 
              WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'""")
db.commit()

row = db.execute("SELECT username, start_time, end_time, status FROM accounts WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'").fetchone()
print(f"username={row[0]}, start={row[1]}, end={row[2]}, status={row[3]}")
