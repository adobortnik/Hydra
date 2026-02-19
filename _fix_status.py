import sqlite3
db = sqlite3.connect('db/phone_farm.db')
db.execute("UPDATE content_schedule SET status = 'pending' WHERE status = 'scheduled'")
db.commit()
rows = db.execute("SELECT id, content_type, scheduled_time, status, username FROM content_schedule WHERE device_serial = '10.1.10.238_5555' ORDER BY scheduled_time").fetchall()
for r in rows:
    print(r)
