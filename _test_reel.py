"""Quick test: push video + attempt reel post on ROBIN 1"""
import sys, os, logging
sys.path.insert(0, r'C:\Users\TheLiveHouse\clawd\phone-farm')
sys.path.insert(0, r'C:\Users\TheLiveHouse\clawd\phone-farm\dashboard')
sys.path.insert(0, r'C:\Users\TheLiveHouse\clawd\phone-farm\automation')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

import uiautomator2 as u2
from automation.actions.post_content import PostContentAction

DEVICE_SERIAL = '10.1.10.238_5555'
ADB_SERIAL = '10.1.10.238:5555'
USERNAME = 'rieff_real'
PACKAGE = 'com.instagram.androie'
VIDEO_PATH = r'C:\Users\TheLiveHouse\.clawdbot\media\inbound\4ecb2ed2-e4f9-45db-8285-66cbf6983e3f.mp4'

print(f"Connecting to {ADB_SERIAL}...")
device = u2.connect(ADB_SERIAL)
print(f"Connected: {device.info.get('productName', 'unknown')}")

# Lock rotation
try:
    device.freeze_rotation()
    device.set_orientation('natural')
except:
    pass

schedule_item = {
    'id': 0,
    'content_type': 'reel',
    'media_path': VIDEO_PATH,
    'caption': 'Test reel upload #test',
    'hashtags': '',
    'location': '',
    'music_search_query': '',
    'music_name': '',
    'mention_username': '',
    'link_url': '',
}

account_info = {
    'id': 325,
    'username': USERNAME,
    'package': PACKAGE,
}

print(f"\nCreating PostContentAction for reel on {USERNAME} ({PACKAGE})...")
action = PostContentAction(
    device=device,
    device_serial=DEVICE_SERIAL,
    account_info=account_info,
    session_id='test_reel_manual',
    schedule_item=schedule_item,
    package=PACKAGE,
)

print("Executing reel posting flow...\n")
result = action.execute()

print(f"\n{'='*60}")
print(f"RESULT: {result}")
print(f"{'='*60}")
