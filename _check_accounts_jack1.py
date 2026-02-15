import sqlite3
conn = sqlite3.connect('C:/Users/TheLiveHouse/clawd/phone-farm/db/phone_farm.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("""SELECT id, username, device_serial, start_time, end_time, status, instagram_package
    FROM accounts WHERE device_serial = '10.1.11.4_5555' AND status = 'active' 
    ORDER BY CAST(COALESCE(start_time,'0') AS INTEGER)""").fetchall()
print(f"{'ID':>4} | {'Username':25s} | Start | End   | Package")
print("-" * 80)
import datetime
now = datetime.datetime.now()
print(f"Current time: {now.strftime('%H:%M')} (hour={now.hour})")
print("-" * 80)
for r in rows:
    st = str(r["start_time"] or "0")
    et = str(r["end_time"] or "0")
    pkg = r["instagram_package"] or "?"
    print(f'{r["id"]:4d} | {r["username"]:25s} | {st:>5s} | {et:>5s} | {pkg}')
conn.close()
