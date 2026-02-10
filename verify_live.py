"""Live verification of DM inbox detection and post author detection."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2
from automation.ig_controller import IGController, Screen

d = u2.connect('10.1.11.4:5555')
ctrl = IGController(d, '10.1.11.4_5555', 'com.instagram.androie')
print("Connected")

ctrl.ensure_app()

passed = 0
failed = 0

# Go to home feed
print("\n--- Navigate to home feed ---")
home = d(resourceIdMatches='.*feed_tab')
if home.exists(timeout=3):
    home.click()
    time.sleep(0.5)
    home.click()
    time.sleep(2)
    w, h = d.window_size()
    for i in range(3):
        d.swipe(w//2, int(h*0.2), w//2, int(h*0.8), duration=0.3)
        time.sleep(0.3)
    time.sleep(1)

screen = ctrl.detect_screen()
print(f"Home feed detection: {screen.value}")
if screen == Screen.HOME_FEED:
    passed += 1
    print("  PASS")
else:
    failed += 1
    print("  FAIL")

# Navigate to DM inbox
print("\n--- Navigate to DM inbox ---")
dm_btn = d(resourceIdMatches='.*action_bar_inbox_button')
if dm_btn.exists(timeout=3):
    dm_btn.click()
    time.sleep(3)
    
    screen = ctrl.detect_screen()
    ctrl.screenshot("verify_live_dm")
    print(f"DM inbox detection: {screen.value}")
    if screen == Screen.DM_INBOX:
        passed += 1
        print("  PASS")
    else:
        failed += 1
        print("  FAIL")
    
    d.press('back')
    time.sleep(1)
else:
    print("  DM button not found, scrolling up more")
    failed += 1

# Post author detection on live feed
print("\n--- Post author detection (live) ---")
# Go to home
home = d(resourceIdMatches='.*feed_tab')
if home.exists(timeout=3):
    home.click()
    time.sleep(2)
    # Scroll to see a post
    w, h = d.window_size()
    d.swipe(w//2, int(h*0.7), w//2, int(h*0.3), duration=0.5)
    time.sleep(2)

xml = ctrl.dump_xml("verify_live_feed")

# Import comment action's method
from automation.actions.comment import CommentAction
class MockComment:
    def __init__(self, ctrl):
        self.ctrl = ctrl
mock = MockComment(ctrl)
mock._get_post_author_from_xml = CommentAction._get_post_author_from_xml.__get__(mock)

author = mock._get_post_author_from_xml(xml)
if author:
    print(f"  Author found: '{author}'")
    passed += 1
    print("  PASS")
else:
    print("  Author NOT found")
    failed += 1
    print("  FAIL")

print(f"\n{'='*40}")
print(f"RESULTS: {passed} passed, {failed} failed")
print(f"{'='*40}")
