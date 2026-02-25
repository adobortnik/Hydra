"""
E2E share_to_story on SAMSUNG (192) / mrjaggerlife using actual ShareToStoryAction.
This uses the same code path as the bot engine.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from automation.actions.share_to_story import ShareToStoryAction
from automation.actions.helpers import get_account_settings
import uiautomator2 as u2
import subprocess, time, sqlite3

DEVICE_SERIAL = '10.1.10.192_5555'
ADB_SERIAL = '10.1.10.192:5555'
PKG = 'com.instagram.androio'
ACCOUNT_ID = 119
USERNAME = 'mrjaggerlife'

# Connect
d = u2.connect(ADB_SERIAL)
print(f"Connected: {d.info['productName']}")

# Launch app
d.app_stop(PKG)
time.sleep(2)
subprocess.run(['adb', '-s', ADB_SERIAL, 'shell', 'monkey', '-p', PKG,
                '-c', 'android.intent.category.LAUNCHER', '1'], capture_output=True)
time.sleep(5)
print(f"Launched {PKG} for {USERNAME}")

# Create account_info dict like bot_engine does
account_info = {
    'id': ACCOUNT_ID,
    'username': USERNAME,
    'package': PKG,
    'device_serial': DEVICE_SERIAL,
}

# Create a dummy session_id
conn = sqlite3.connect('db/phone_farm.db')
cursor = conn.execute(
    "INSERT INTO account_sessions (account_id, device_serial, start_time) VALUES (?, ?, datetime('now'))",
    (ACCOUNT_ID, DEVICE_SERIAL))
session_id = cursor.lastrowid
conn.commit()
conn.close()
print(f"Session: {session_id}")

# Create ShareToStoryAction instance - same as bot engine
action = ShareToStoryAction(d, DEVICE_SERIAL, account_info, session_id)

print(f"\nSettings:")
print(f"  post_type: {action.post_type}")
print(f"  enable_mention: {action.enable_mention}")
print(f"  mention_target: {action.mention_target}")
print(f"  enable_link_sticker: {action.enable_link_sticker}")
print(f"  link_sticker_url: {action.link_sticker_url}")
print(f"  daily_limit: {action.daily_limit}")

# Execute the actual share_to_story action
print(f"\n--- Running share_to_story ---")
result = action.execute()
print(f"\n--- Result ---")
print(result)
