import sqlite3, datetime
db = sqlite3.connect('db/phone_farm.db')

# Schedule reel in 5 minutes
now = datetime.datetime.now()
reel_time = (now + datetime.timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
media_path = r'C:\Users\TheLiveHouse\clawd\phone-farm\media_library\original\0d9d902d_WhatsApp_Video_2025-02-22_at_16.59.28.mp4'

db.execute("""INSERT INTO content_schedule 
    (account_id, device_serial, username, content_type, media_path, caption, hashtags, scheduled_time, status, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
    (325, '10.1.10.238_5555', 'rieff_real', 'reel', media_path,
     'Testing reel flow', '#test #reel',
     reel_time, 'pending'))
db.commit()

row = db.execute("SELECT id, content_type, scheduled_time, status FROM content_schedule WHERE status='pending' ORDER BY id DESC LIMIT 1").fetchone()
print(f"Scheduled: id={row[0]} type={row[1]} time={row[2]} status={row[3]}")
