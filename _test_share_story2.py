"""Quick test: run share_to_story directly on modeljagger with mention enabled."""
import logging
import sqlite3
import time
import uiautomator2 as u2
from automation.actions.share_to_story import ShareToStoryAction
from automation.ig_controller import IGController, Screen

logging.basicConfig(level=logging.INFO, format='%(message)s')

# Get account info
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row
acct = conn.execute("SELECT * FROM accounts WHERE username='modeljagger'").fetchone()
conn.close()

account_info = dict(acct)
serial_adb = acct['device_serial'].replace('_', ':')
serial_db = acct['device_serial']
pkg = acct['instagram_package']

print(f"Device: {serial_adb}, Package: {pkg}")

device = u2.connect(serial_adb)

# Force start IG clone
import subprocess
adb_serial = serial_db.replace('_', ':')
subprocess.run(['adb', '-s', adb_serial, 'shell', 'am', 'force-stop', pkg], capture_output=True, timeout=10)
time.sleep(1)
activity = f"{pkg}/com.instagram.mainactivity.InstagramMainActivity"
subprocess.run(['adb', '-s', adb_serial, 'shell', 'am', 'start', '-n', activity], capture_output=True, timeout=10)
print(f"Launched {pkg}")
time.sleep(5)

ctrl = IGController(device, serial_db, pkg)
ctrl.dismiss_popups()
ctrl.navigate_to(Screen.HOME_FEED)
time.sleep(2)

print("IG is on home feed. Starting share_to_story test...")

action = ShareToStoryAction(device, serial_db, account_info, session_id=999, package=pkg)
print(f"Mention enabled: {action.enable_mention}")
print(f"Mention target: {action.mention_target}")

result = action.execute()
print(f"\nResult: {result}")
