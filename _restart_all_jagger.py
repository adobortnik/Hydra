import sqlite3, requests, time

conn = sqlite3.connect('db/phone_farm.db')
rows = conn.execute("SELECT DISTINCT device_serial FROM accounts WHERE tag='jagger'").fetchall()
devices = [r[0] for r in rows]
conn.close()

auth = ('admin', 'hydra2026')
BASE = 'http://localhost:5055'

print(f"Restarting {len(devices)} jagger devices...\n")

# Stop all
for s in devices:
    try:
        r = requests.post(f'{BASE}/api/bot/stop/{s}', auth=auth, timeout=5)
        print(f"  STOP  {s}: {r.json().get('status','?')}")
    except:
        print(f"  STOP  {s}: (not running)")

time.sleep(3)

# Start all
for s in devices:
    try:
        r = requests.post(f'{BASE}/api/bot/launch/{s}', auth=auth, timeout=15)
        print(f"  START {s}: {r.json().get('success','?')}")
    except Exception as e:
        print(f"  START {s}: ERROR {e}")
    time.sleep(2)

print("\nDone!")
