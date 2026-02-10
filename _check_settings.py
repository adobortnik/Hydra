import sqlite3
import json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Check account_settings for id=603
s = conn.execute('SELECT * FROM account_settings WHERE account_id=603').fetchone()
if s:
    print('Row exists in account_settings for id=603')
    sj = s['settings_json']
    if sj:
        d = json.loads(sj)
        print(f"  startTime: {d.get('startTime', 'NOT SET')}")
        print(f"  endTime: {d.get('endTime', 'NOT SET')}")
        print(f"  Keys: {list(d.keys())}")
    else:
        print('  settings_json is NULL/empty')
else:
    print('NO ROW in account_settings for account_id=603')

# Check accounts table structure
cols = [c[1] for c in conn.execute('PRAGMA table_info(accounts)').fetchall()]
print(f"\naccounts table columns: {cols}")

# Check if startTime/endTime are in accounts table directly
a = conn.execute('SELECT * FROM accounts WHERE id=603').fetchone()
if a:
    ad = dict(a)
    print(f"\naccounts row for id=603:")
    for k in ['username', 'status', 'startTime', 'endTime', 'start_time', 'end_time']:
        if k in ad:
            print(f"  {k}: {ad[k]}")

conn.close()
