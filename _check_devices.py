"""Quick check: which devices are connected and which accounts are on them."""
from automation.actions.helpers import get_db

conn = get_db()

# Connected devices
print("=== CONNECTED DEVICES ===")
rows = conn.execute("SELECT device_serial, device_name, status FROM devices WHERE status='connected'").fetchall()
for r in rows:
    print(dict(r))

if not rows:
    print("No connected devices in DB. Checking ADB...")
    import subprocess
    result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
    print(result.stdout)

# Accounts on JACK 1 (10.1.11.4_5555)
print("\n=== JACK 1 ACCOUNTS (active) ===")
accts = conn.execute(
    "SELECT id, username, instagram_package, status, start_time, end_time FROM accounts WHERE device_serial='10.1.11.4_5555' AND status='active'"
).fetchall()
for a in accts:
    print(dict(a))

conn.close()
