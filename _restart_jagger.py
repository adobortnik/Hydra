import sqlite3, requests, time

conn = sqlite3.connect('db/phone_farm.db')
rows = conn.execute("SELECT DISTINCT device_serial FROM accounts WHERE tag='jagger'").fetchall()
devices = [r[0] for r in rows]
conn.close()

print(f"Jagger devices: {len(devices)}")

# Stop all first
for serial in devices:
    try:
        r = requests.post(f'http://localhost:5055/api/bot/stop/{serial}', timeout=5)
        d = r.json()
        print(f"  STOP {serial}: {d.get('status', d.get('message','ok'))}")
    except Exception as e:
        print(f"  STOP {serial}: {e}")

print("\nWaiting 3s...")
time.sleep(3)

# Start all with 2s delay
for i, serial in enumerate(devices):
    try:
        r = requests.post(f'http://localhost:5055/api/bot/launch/{serial}', timeout=10)
        d = r.json()
        print(f"  START {serial}: {d.get('success', False)}")
    except Exception as e:
        print(f"  START {serial}: {e}")
    if i < len(devices) - 1:
        time.sleep(2)

print("\nDone!")
