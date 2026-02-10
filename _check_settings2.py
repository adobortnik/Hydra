import sqlite3
import json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

s = conn.execute('SELECT settings_json FROM account_settings WHERE account_id=603').fetchone()
if s and s['settings_json']:
    d = json.loads(s['settings_json'])
    print(f"settings_json.start_time: {d.get('start_time', 'NOT SET')}")
    print(f"settings_json.end_time: {d.get('end_time', 'NOT SET')}")
    print(f"settings_json.startTime: {d.get('startTime', 'NOT SET')}")
    print(f"settings_json.endTime: {d.get('endTime', 'NOT SET')}")

a = conn.execute('SELECT start_time, end_time FROM accounts WHERE id=603').fetchone()
print(f"\naccounts.start_time: {a['start_time']}")
print(f"accounts.end_time: {a['end_time']}")

conn.close()
