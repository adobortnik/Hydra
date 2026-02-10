import sqlite3

conn = sqlite3.connect(r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db')
conn.row_factory = sqlite3.Row

print("=== DEVICES ===")
devs = conn.execute('SELECT * FROM devices').fetchall()
for d in devs:
    print(f"  id={d['id']} name={d['device_name']} serial={d['device_serial']}")

print("\n=== ACCOUNTS ===")
accs = conn.execute('SELECT a.id, a.username, a.device_id, a.instagram_package, a.status FROM accounts a').fetchall()
for a in accs:
    print(f"  id={a['id']} dev={a['device_id']} user={a['username']} pkg={a['instagram_package']} status={a['status']}")

print("\n=== TABLES ===")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(f"  {t['name']}")

conn.close()
