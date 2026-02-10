"""Step 1: Just dump XML from current screen."""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2

d = u2.connect('10.1.11.4:5555')
print("App:", d.app_current())

# Dump current screen XML
os.makedirs('test_results', exist_ok=True)
xml = d.dump_hierarchy()
with open('test_results/current_screen.xml', 'w', encoding='utf-8') as f:
    f.write(xml)
print(f"XML dumped: {len(xml)} bytes")

# Look for key resource IDs
print("\n--- Feed author-related ---")
for pat in ['row_feed_profile', 'profile_name', 'profile_header', 'username', 'row_feed_text']:
    matches = re.findall(r'resource-id="([^"]*' + pat + r'[^"]*)"', xml)
    for m in set(matches):
        print(f"  {m}")

print("\n--- DM indicators ---")
for pat in ['inbox', 'thread', 'direct', 'messenger']:
    matches = re.findall(r'resource-id="([^"]*' + pat + r'[^"]*)"', xml)
    for m in set(matches):
        print(f"  {m}")

print("\n--- Story/reel ---")
for pat in ['reel_viewer', 'story_viewer', 'reels_tray']:
    if pat in xml:
        print(f"  FOUND: {pat}")

# Find all clickable text elements
print("\n--- Short text elements with resource IDs ---")
nodes = re.findall(r'<node[^>]*resource-id="([^"]*)"[^>]*text="([^"]*)"[^>]*', xml)
for rid, text in nodes:
    if text and len(text) < 30 and rid:
        short_rid = rid.split(':id/')[-1] if ':id/' in rid else rid
        print(f"  [{short_rid}] '{text}'")

# Profile picture descs 
print("\n--- Profile pic descs ---")
pics = re.findall(r"content-desc=\"([^\"]*(?:profile|photo|picture)[^\"]*?)\"", xml, re.IGNORECASE)
for p in set(pics):
    print(f"  {p}")

print("\nDone")
