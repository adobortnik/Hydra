"""
Run actual CommentAction on ROBIN 1 / rieff_real with source christian.jagg.
Same flow as bot engine would run.
"""
import sys, logging
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

# Log to console so we can see what's happening
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)-7s %(message)s',
                    stream=sys.stdout)

import uiautomator2 as u2
import subprocess, time

DEVICE = '10.1.10.238:5555'
SERIAL = '10.1.10.238_5555'
PKG = 'com.instagram.androie'
USERNAME = 'rieff_real'

d = u2.connect(DEVICE)

# Fresh start
d.app_stop(PKG)
time.sleep(2)
subprocess.run(['adb', '-s', DEVICE, 'shell', 'monkey', '-p', PKG,
                '-c', 'android.intent.category.LAUNCHER', '1'], capture_output=True)
time.sleep(5)
print("IG launched")

from automation.ig_controller import IGController
from automation.actions.comment import CommentAction
import sqlite3

# Get account id
db = sqlite3.connect('db/phone_farm.db')
row = db.execute("SELECT id FROM accounts WHERE username=? AND device_serial=?",
                 (USERNAME, SERIAL)).fetchone()
account_id = row[0]
print(f"Account: {USERNAME} (id={account_id})")

# Get settings
import json
srow = db.execute("SELECT settings_json FROM account_settings WHERE account_id=?",
                  (account_id,)).fetchone()
settings = json.loads(srow[0]) if srow and srow[0] else {}

# Override for test
settings['comment_limit_perday'] = 2
settings['comment_text'] = '[AI]'

account_info = {
    'id': account_id,
    'username': USERNAME,
    'package': PKG,
}

action = CommentAction(
    device=d,
    device_serial=SERIAL,
    account_info=account_info,
    session_id=None,
    package=PKG,
)

print("Running CommentAction.execute()...")
result = action.execute()
print(f"\nResult: {result}")
