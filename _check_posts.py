import sqlite3
db = sqlite3.connect('db/phone_farm.db')
rows = db.execute("""SELECT id, content_type, scheduled_time, status, posted_at, error_message 
                     FROM content_schedule WHERE device_serial = '10.1.10.238_5555' 
                     ORDER BY scheduled_time""").fetchall()
for r in rows:
    print(r)
