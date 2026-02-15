import sqlite3, datetime
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row
hour = datetime.datetime.now().hour
print(f'Current hour: {hour}')
rows = conn.execute('''
    SELECT id, username, instagram_package, start_time, end_time, status
    FROM accounts WHERE device_serial='10.1.11.4_5555' AND status='active'
''').fetchall()
for r in rows:
    s, e = str(r['start_time']), str(r['end_time'])
    starts = [int(x) for x in s.split(',') if x.strip()]
    ends = [int(x) for x in e.split(',') if x.strip()]
    windows = list(zip(starts, ends))
    active = any(ws <= hour < we for ws, we in windows) or (starts == [0] and ends == [0])
    mark = ' <<< ACTIVE NOW' if active else ''
    pkg = r['instagram_package'] or 'default'
    uname = r['username']
    print(f'  {uname:<30} pkg={pkg:<30} window={s}-{e}{mark}')
conn.close()
