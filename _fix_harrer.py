import sqlite3
conn = sqlite3.connect('C:/Users/TheLiveHouse/clawd/phone-farm/db/phone_farm.db')
conn.execute("UPDATE accounts SET start_time = '2,12', end_time = '4,14' WHERE id = 450")
conn.commit()
r = conn.execute('SELECT id, username, start_time, end_time FROM accounts WHERE id = 450').fetchone()
print(f'Updated: id={r[0]} user={r[1]} start={r[2]} end={r[3]}')
conn.close()
