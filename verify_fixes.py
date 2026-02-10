"""Verify the DM inbox detection fix and post author detection fix."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2
from automation.ig_controller import IGController, Screen

d = u2.connect('10.1.11.4:5555')
ctrl = IGController(d, '10.1.11.4_5555', 'com.instagram.androie')

passed = 0
failed = 0

# ============================================================
# Test 1: DM Inbox detection using saved XML
# ============================================================
print("=" * 60)
print("TEST 1: DM Inbox detection (using saved XML)")
print("=" * 60)

dm_xml_path = 'test_results/dm_inbox_full.xml'
if os.path.exists(dm_xml_path):
    with open(dm_xml_path, 'r', encoding='utf-8') as f:
        dm_xml = f.read()
    screen = ctrl.detect_screen(dm_xml)
    if screen == Screen.DM_INBOX:
        print(f"  PASS: DM inbox correctly detected as {screen.value}")
        passed += 1
    else:
        print(f"  FAIL: DM inbox detected as {screen.value} (expected DM_INBOX)")
        failed += 1
else:
    print("  SKIP: No saved DM inbox XML found")

# Test that feed XML still detects correctly
feed_xml_path = 'test_results/feed_absolute_top.xml'
if os.path.exists(feed_xml_path):
    with open(feed_xml_path, 'r', encoding='utf-8') as f:
        feed_xml = f.read()
    screen = ctrl.detect_screen(feed_xml)
    if screen == Screen.HOME_FEED:
        print(f"  PASS: Home feed correctly detected as {screen.value}")
        passed += 1
    else:
        print(f"  FAIL: Home feed detected as {screen.value} (expected HOME_FEED)")
        failed += 1

# ============================================================
# Test 2: Live DM inbox navigation and detection
# ============================================================
print("\n" + "=" * 60)
print("TEST 2: Live DM inbox navigation")
print("=" * 60)

ctrl.ensure_app()
ctrl.dismiss_popups()

# Go home first, scroll to top
home = d(resourceIdMatches='.*feed_tab')
if home.exists(timeout=3):
    home.click()
    time.sleep(0.5)
    home.click()
    time.sleep(2)

# Scroll up to reveal action bar
w, h = d.window_size()
for i in range(3):
    d.swipe(w//2, int(h*0.2), w//2, int(h*0.8), duration=0.3)
    time.sleep(0.3)
time.sleep(1)

# Click DM button
dm_btn = d(resourceIdMatches='.*action_bar_inbox_button')
if dm_btn.exists(timeout=3):
    dm_btn.click()
    time.sleep(3)
    ctrl.dismiss_popups()
    
    screen = ctrl.detect_screen()
    ctrl.screenshot("verify_dm_inbox")
    if screen == Screen.DM_INBOX:
        print(f"  PASS: Live DM inbox detected as {screen.value}")
        passed += 1
    else:
        print(f"  FAIL: Live DM inbox detected as {screen.value} (expected DM_INBOX)")
        failed += 1
    
    d.press('back')
    time.sleep(1)
else:
    print("  FAIL: DM button not found")
    failed += 1

# ============================================================
# Test 3: Post author detection
# ============================================================
print("\n" + "=" * 60)
print("TEST 3: Post author detection")
print("=" * 60)

# Make sure we import the comment module
from automation.actions.comment import CommentAction

# Use saved feed XML
if os.path.exists('test_results/current_screen.xml'):
    with open('test_results/current_screen.xml', 'r', encoding='utf-8') as f:
        feed_xml = f.read()
    
    # Create a minimal CommentAction-like object to test _get_post_author_from_xml
    class MockComment:
        def __init__(self, ctrl):
            self.ctrl = ctrl
    
    mock = MockComment(ctrl)
    # Bind the method
    mock._get_post_author_from_xml = CommentAction._get_post_author_from_xml.__get__(mock)
    
    author = mock._get_post_author_from_xml(feed_xml)
    if author:
        print(f"  PASS: Post author detected: '{author}'")
        passed += 1
    else:
        print(f"  FAIL: Post author NOT detected")
        failed += 1

# Also test live
print("\n  Testing live feed...")
ctrl.navigate_to(Screen.HOME_FEED)
time.sleep(2)
d.swipe(w//2, int(h*0.7), w//2, int(h*0.3), duration=0.5)
time.sleep(2)
xml = ctrl.dump_xml("verify_feed_author")
author_live = mock._get_post_author_from_xml(xml)
if author_live:
    print(f"  PASS: Live post author: '{author_live}'")
    passed += 1
else:
    print(f"  FAIL: Live post author NOT detected")
    failed += 1

# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed")
print("=" * 60)
