import sqlite3
db = sqlite3.connect('db/phone_farm.db')

# Set rieff_real working hours 4:00 - 11:00
db.execute("""UPDATE accounts SET start_time = '04:00', end_time = '11:00' 
              WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'""")

# Disable all other accounts on ROBIN 1
db.execute("""UPDATE accounts SET status = 'disabled' 
              WHERE device_serial = '10.1.10.238_5555' AND username != 'rieff_real'""")

db.commit()

# Verify
rows = db.execute("""SELECT username, status, start_time, end_time 
                     FROM accounts WHERE device_serial = '10.1.10.238_5555' 
                     ORDER BY username""").fetchall()
for r in rows:
    print(r)
