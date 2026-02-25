import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

import sqlite3, subprocess, time
import uiautomator2 as u2

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row
account = dict(conn.execute("SELECT * FROM accounts WHERE id = 329").fetchone())
conn.close()

pkg = account['instagram_package']
print(f"Account: {account['username']} | pkg={pkg}")

d = u2.connect('10.1.10.238:5555')
print("Connected to ROBIN 1")

# Force-stop ALL IG clones first
print("Force-stopping all IG clones...")
for suffix in 'abcdefghijklmnopqrstuvwxyz':
    clone_pkg = f'com.instagram.androi{suffix}'
    subprocess.run(['adb', '-s', '10.1.10.238:5555', 'shell', 'am', 'force-stop', clone_pkg], 
                   capture_output=True, timeout=3)
time.sleep(2)

print(f"Launching {pkg}...")
subprocess.run(['adb', '-s', '10.1.10.238:5555', 'shell', 'monkey', '-p', pkg, 
                '-c', 'android.intent.category.LAUNCHER', '1'],
               capture_output=True, timeout=5)
time.sleep(10)  # Extra wait for slow proxy
print(f"Current app: {d.app_current()}")

from automation.actions.switch_to_private import SwitchToPrivateAction

action = SwitchToPrivateAction(
    device=d,
    device_serial='10.1.10.238_5555',
    account_info=account,
    session_id='manual_test',
    pkg=pkg
)

print("\nStarting switch to private flow...")
print("Watch the phone!\n")
result = action.execute()
print(f"\nResult: {result}")
