"""Step 2: Detailed look at author elements and DM inbox."""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2

d = u2.connect('10.1.11.4:5555')

# Read the XML we already dumped
with open('test_results/current_screen.xml', 'r', encoding='utf-8') as f:
    xml = f.read()

# Find all row_feed_profile_header nodes
print("=== row_feed_profile_header ===")
for m in re.finditer(r'<node[^>]*resource-id="[^"]*row_feed_profile_header[^"]*"[^>]*', xml):
    node = m.group(0)
    print(f"  {node}")

# Find all row_feed_photo_profile_name nodes
print("\n=== row_feed_photo_profile_name ===")
for m in re.finditer(r'<node[^>]*resource-id="[^"]*row_feed_photo_profile_name[^"]*"[^>]*', xml):
    node = m.group(0)
    print(f"  {node}")

# Find ALL nodes with text attribute that are small text
print("\n=== ALL text nodes (non-empty, <40 chars) ===")
for m in re.finditer(r'<node[^>]* text="([^"]+)"[^>]*resource-id="([^"]*)"', xml):
    text, rid = m.group(1), m.group(2)
    if len(text) < 40:
        short_rid = rid.split(':id/')[-1] if ':id/' in rid else (rid or 'NO_RID')
        print(f"  [{short_rid}] '{text}'")

# Also try reverse order: resource-id before text
for m in re.finditer(r'<node[^>]*resource-id="([^"]*)"[^>]* text="([^"]+)"', xml):
    rid, text = m.group(1), m.group(2)
    if len(text) < 40:
        short_rid = rid.split(':id/')[-1] if ':id/' in rid else (rid or 'NO_RID')
        print(f"  [{short_rid}] '{text}'")

# Search for known usernames from profile pics
print("\n=== Search for 'jasper_theshepherd' in XML ===")
for m in re.finditer(r'<node[^>]*jasper_theshepherd[^>]*', xml):
    print(f"  {m.group(0)[:200]}")

print("\n=== Search for 'nekonekodreamer' in XML ===")
for m in re.finditer(r'<node[^>]*nekonekodreamer[^>]*', xml):
    print(f"  {m.group(0)[:200]}")

# Now navigate to DM inbox
print("\n\n=== NAVIGATING TO DM INBOX ===")
dm_btn = d(resourceIdMatches='.*action_bar_inbox_button')
if dm_btn.exists(timeout=3):
    print("DM button found, clicking...")
    dm_btn.click()
    time.sleep(3)
    
    xml_dm = d.dump_hierarchy()
    with open('test_results/dm_inbox.xml', 'w', encoding='utf-8') as f:
        f.write(xml_dm)
    print(f"DM inbox XML dumped: {len(xml_dm)} bytes")
    d.screenshot('test_results/dm_inbox.png')
    
    # Check story/reel indicators
    print("\n--- Story/reel indicators in DM inbox ---")
    for pat in ['reel_viewer_root', 'story_viewer', 'reel_viewer_texture_view', 
                'reel_viewer', 'reels_tray', 'reels_tray_container']:
        if pat in xml_dm:
            idx = xml_dm.index(pat)
            ctx = xml_dm[max(0,idx-80):idx+80].replace('\n',' ')
            print(f"  FOUND: {pat}")
            print(f"    ...{ctx}...")
    
    # Check DM indicators
    print("\n--- DM indicators ---")
    for pat in ['inbox_refreshable_thread_list_recyclerview', 'inbox_tab',
                'direct_thread', 'action_bar_inbox_button', 'thread_title',
                'action_bar_title', 'tab_layout']:
        if pat in xml_dm:
            print(f"  FOUND: {pat}")
        else:
            print(f"  missing: {pat}")
    
    # Check what resource-ids contain 'inbox' or 'direct' or 'thread'
    print("\n--- All resource IDs with inbox/direct/thread ---")
    for m in set(re.findall(r'resource-id="([^"]*(?:inbox|direct|thread|message)[^"]*)"', xml_dm, re.IGNORECASE)):
        print(f"  {m}")
    
    # Go back
    d.press('back')
    time.sleep(1)
else:
    print("DM button NOT found!")
    # Try alternative
    dm_btn2 = d(descriptionContains='Direct')
    if dm_btn2.exists(timeout=2):
        print("Found via desc 'Direct'")
    dm_btn3 = d(descriptionContains='Messenger')
    if dm_btn3.exists(timeout=2):
        print("Found via desc 'Messenger'")

print("\nDone")
