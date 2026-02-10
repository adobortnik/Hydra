"""Quick investigation script for DM and Comment issues."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2
from automation.ig_controller import IGController, Screen

d = u2.connect('10.1.11.4:5555')
ctrl = IGController(d, '10.1.11.4_5555', 'com.instagram.androie')

print("Current app:", d.app_current())
ctrl.ensure_app()
ctrl.dismiss_popups()

# Phase 1: Navigate to home feed and dump XML for post author investigation
print("\n=== HOME FEED XML ===")
ctrl.navigate_to(Screen.HOME_FEED)
time.sleep(2)

# Scroll down a bit to see a post
w, h = d.window_size()
d.swipe(w // 2, int(h * 0.7), w // 2, int(h * 0.3), duration=0.5)
time.sleep(2)

xml_feed = ctrl.dump_xml("investigate_feed")
ctrl.screenshot("investigate_feed")

# Search for post author-related elements
import re
print("\n--- Looking for author-related resource IDs ---")
author_patterns = [
    'row_feed_profile',
    'row_feed_photo_profile',
    'row_feed_comment_textview',
    'row_feed_textview_likes',
    'row_feed_profile_header',
    'profile_name',
    'header_title',
    'username',
]
for pat in author_patterns:
    matches = re.findall(r'resource-id="[^"]*' + pat + r'[^"]*"', xml_feed)
    if matches:
        for m in set(matches):
            print(f"  FOUND: {m}")

# Also search for profile picture content-desc patterns
pic_matches = re.findall(r"content-desc=\"[^\"]*profile picture[^\"]*\"", xml_feed)
for m in set(pic_matches):
    print(f"  PROFILE PIC DESC: {m}")

# Search for any text elements that might be usernames (short text near top)
print("\n--- Text elements that could be usernames ---")
text_matches = re.findall(r'<node[^>]*resource-id="([^"]*)"[^>]*text="([^"]*)"[^>]*bounds="(\[[\d,]+\]\[[\d,]+\])"', xml_feed)
for rid, text, bounds in text_matches:
    if text and len(text) < 40 and not text.startswith('http'):
        print(f"  rid={rid} text={text} bounds={bounds}")

# Phase 2: Navigate to DM inbox and dump XML
print("\n\n=== DM INBOX XML ===")
ctrl.navigate_to(Screen.HOME_FEED)
time.sleep(1)

dm_btn = ctrl.find_element(resource_id='action_bar_inbox_button', timeout=3)
if not dm_btn:
    dm_btn = ctrl.find_element(desc='Direct', timeout=2)
if not dm_btn:
    dm_btn = ctrl.find_element(desc='Messenger', timeout=2)

if dm_btn:
    dm_btn.click()
    time.sleep(3)
    ctrl.dismiss_popups()
    
    xml_dm = ctrl.dump_xml("investigate_dm_inbox")
    ctrl.screenshot("investigate_dm_inbox")
    
    screen = ctrl.detect_screen(xml_dm)
    print(f"Detected screen: {screen.value}")
    
    # Check for DM-specific indicators
    print("\n--- DM Inbox indicators ---")
    dm_ids = [
        'action_bar_inbox_button',
        'inbox_tab',
        'thread_list',
        'direct_thread_list',
        'inbox_refreshable_thread_list_recyclerview',
        'direct_thread',
        'action_bar_title',
    ]
    for rid in dm_ids:
        if rid in xml_dm:
            print(f"  FOUND: {rid}")
        else:
            print(f"  not found: {rid}")
    
    # Check for story/reel indicators that cause false STORY_VIEW
    print("\n--- Story/Reel indicators in DM inbox ---")
    story_ids = [
        'reel_viewer_root',
        'story_viewer',
        'reel_viewer_texture_view',
        'reel_viewer',
        'reels_tray',
        'reels_tray_container',
    ]
    for rid in story_ids:
        if rid in xml_dm:
            # Find the full context
            idx = xml_dm.index(rid)
            start = max(0, idx - 100)
            end = min(len(xml_dm), idx + 100)
            context = xml_dm[start:end].replace('\n', ' ')
            print(f"  FOUND: {rid}")
            print(f"    context: ...{context}...")
        else:
            print(f"  not found: {rid}")
    
    # Check for notes area
    print("\n--- Notes area indicators ---")
    notes_ids = ['notes', 'note_', 'reel_tray', 'reshare']
    for rid in notes_ids:
        count = xml_dm.lower().count(rid)
        if count > 0:
            print(f"  '{rid}' appears {count} times")
    
    ctrl.press_back()
    time.sleep(1)
else:
    print("DM button not found!")

print("\nDone! Check test_results/ for screenshots and XML dumps.")
