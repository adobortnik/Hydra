"""Quick test: run share_to_story directly on modeljagger with mention enabled."""
import sqlite3
import uiautomator2 as u2
from automation.actions.share_to_story import ShareToStoryAction

# Get account info
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row
acct = conn.execute("SELECT * FROM accounts WHERE username='modeljagger'").fetchone()
conn.close()

account_info = dict(acct)
serial = acct['device_serial'].replace('_', ':')
pkg = acct['instagram_package']

print(f"Device: {serial}, Package: {pkg}")
print(f"Running share_to_story for @modeljagger with mention test...")

device = u2.connect(serial)
action = ShareToStoryAction(device, acct['device_serial'], account_info, session_id=999, package=pkg)

print(f"Mention enabled: {action.enable_mention}")
print(f"Mention target: {action.mention_target}")
print(f"Link enabled: {action.enable_link_sticker}")
print(f"Link URL: {action.link_sticker_url}")

result = action.execute()
print(f"\nResult: {result}")
