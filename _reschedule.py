import sqlite3, datetime
db = sqlite3.connect('db/phone_farm.db')

# Extend window to cover now (4-14h)
db.execute("""UPDATE accounts SET start_time = '4', end_time = '14' 
              WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'""")

# Reschedule: post in 5 min, reel in 20 min
now = datetime.datetime.now()
post_time = (now + datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
reel_time = (now + datetime.timedelta(minutes=20)).strftime('%Y-%m-%d %H:%M:%S')

db.execute("UPDATE content_schedule SET scheduled_time = ? WHERE id = 65", (post_time,))
db.execute("UPDATE content_schedule SET scheduled_time = ? WHERE id = 66", (reel_time,))
db.commit()

rows = db.execute("SELECT id, content_type, scheduled_time, status FROM content_schedule WHERE device_serial = '10.1.10.238_5555'").fetchall()
for r in rows:
    print(r)

row = db.execute("SELECT username, start_time, end_time FROM accounts WHERE username = 'rieff_real' AND device_serial = '10.1.10.238_5555'").fetchone()
print(f"\nrieff_real: window={row[1]}h-{row[2]}h")
