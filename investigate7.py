"""Step 6: Navigate to DM inbox and check for false story detection."""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2
from automation.ig_controller import IGController, Screen

d = u2.connect('10.1.11.4:5555')
ctrl = IGController(d, '10.1.11.4_5555', 'com.instagram.androie')

# Click the DM button
dm_btn = d(resourceIdMatches='.*action_bar_inbox_button')
if dm_btn.exists(timeout=3):
    print("Found DM button, clicking...")
    dm_btn.click()
    time.sleep(3)
else:
    print("DM button not found, trying home tab first")
    home = d(resourceIdMatches='.*feed_tab')
    if home.exists(timeout=3):
        home.click()
        time.sleep(0.5)
        home.click()
        time.sleep(3)
        # Scroll up
        w, h = d.window_size()
        for i in range(3):
            d.swipe(w//2, int(h*0.2), w//2, int(h*0.8), duration=0.3)
            time.sleep(0.3)
        time.sleep(2)
        dm_btn = d(resourceIdMatches='.*action_bar_inbox_button')
        if dm_btn.exists(timeout=3):
            dm_btn.click()
            time.sleep(3)
            print("Found and clicked DM button after scroll")
        else:
            print("STILL no DM button!")
            sys.exit(1)

xml = d.dump_hierarchy()
with open('test_results/dm_inbox_full.xml', 'w', encoding='utf-8') as f:
    f.write(xml)
d.screenshot('test_results/dm_inbox_screen.png')
print(f"DM inbox XML: {len(xml)} bytes")

# Test detect_screen on this XML
screen = ctrl.detect_screen(xml)
print(f"\ndetect_screen() says: {screen.value}")

# Check story indicators
print("\n=== Story/reel indicators ===")
for pat in ['reel_viewer_root', 'story_viewer', 'reel_viewer_texture_view', 'reel_viewer', 'reels_tray']:
    count = xml.count(pat)
    if count > 0:
        print(f"  FOUND: '{pat}' ({count} occurrences)")
        # Show first occurrence context
        idx = xml.index(pat)
        ctx = xml[max(0,idx-120):idx+120].replace('\n',' ')
        print(f"    ...{ctx}...")
    else:
        print(f"  not found: {pat}")

# Check DM indicators
print("\n=== DM indicators ===")
for pat in ['inbox_refreshable_thread_list_recyclerview', 'inbox_tab', 'direct_thread',
            'action_bar_inbox_button', 'thread_title', 'tab_layout',
            'action_bar_title', 'action_bar_textview_title']:
    if pat in xml:
        print(f"  FOUND: {pat}")
    else:
        print(f"  missing: {pat}")

# Check all resource IDs
print("\n=== All unique resource IDs ===")
rids = set(re.findall(r'resource-id="(com\.instagram\.androie:id/[^"]+)"', xml))
for r in sorted(rids):
    short = r.split(':id/')[-1]
    print(f"  {short}")

# Go back
d.press('back')
time.sleep(1)

print("\nDone")
