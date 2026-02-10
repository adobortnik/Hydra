import uiautomator2 as u2
import time
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

d = u2.connect('10.1.11.4:5555')

# Check current state
print("App:", d.app_current()['package'])

# Scan for ALL clickable/tappable elements near bottom of screen (where post/send would be)
xml = d.dump_hierarchy()

# Find any send-like resource IDs
for match in re.finditer(r'resource-id="([^"]*)"', xml):
    rid = match.group(1)
    if any(k in rid.lower() for k in ['send', 'post', 'submit', 'comment_composer']):
        print(f"Resource: {rid}")

# Find any send-like descriptions
for match in re.finditer(r'content-desc="([^"]*)"', xml):
    desc = match.group(1)
    if any(k in desc.lower() for k in ['send', 'post', 'submit']):
        print(f"Desc: {desc}")

# Check all clickable elements
for elem in d(clickable=True):
    info = elem.info
    t = info.get('text', '') or ''
    desc = info.get('contentDescription', '') or ''
    cls = info.get('className', '')
    bounds = info.get('bounds', {})
    # Only show bottom half elements or relevant ones
    bottom = bounds.get('bottom', 0)
    if bottom > 1500 or 'send' in t.lower() or 'post' in t.lower() or 'send' in desc.lower() or 'post' in desc.lower():
        print(f"Clickable: cls={cls} text='{t}' desc='{desc}' bounds={bounds}")

# Also specifically look for the keyboard send/return button
print("\n--- Looking for IME action button ---")
# The send button on keyboard is usually an ImeAction
# Or there might be an ImageView/Button near the input field
for elem in d(className='android.widget.ImageView', clickable=True):
    info = elem.info
    desc = info.get('contentDescription', '') or ''
    bounds = info.get('bounds', {})
    bottom = bounds.get('bottom', 0)
    right = bounds.get('right', 0)
    if bottom > 1600:
        print(f"ImageView: desc='{desc}' bounds={bounds}")
