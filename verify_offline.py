"""Verify fixes using saved XML files only (no device connection)."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# We need a mock device for IGController init
class MockDevice:
    def app_current(self):
        return {'package': 'com.instagram.androie'}
    def window_size(self):
        return (1080, 2400)
    def dump_hierarchy(self):
        return ""

from automation.ig_controller import IGController, Screen

ctrl = IGController(MockDevice(), '10.1.11.4_5555', 'com.instagram.androie')

passed = 0
failed = 0

# Test 1: DM Inbox XML detection
print("TEST 1: DM Inbox XML detection")
dm_xml_path = 'test_results/dm_inbox_full.xml'
if os.path.exists(dm_xml_path):
    with open(dm_xml_path, 'r', encoding='utf-8') as f:
        dm_xml = f.read()
    screen = ctrl.detect_screen(dm_xml)
    if screen == Screen.DM_INBOX:
        print(f"  PASS: detected as {screen.value}")
        passed += 1
    else:
        print(f"  FAIL: detected as {screen.value} (expected DM_INBOX)")
        failed += 1
else:
    print("  SKIP: no dm_inbox_full.xml")

# Test 2: Home feed XML detection
print("\nTEST 2: Home feed XML detection")
feed_xml_path = 'test_results/feed_absolute_top.xml'
if os.path.exists(feed_xml_path):
    with open(feed_xml_path, 'r', encoding='utf-8') as f:
        feed_xml = f.read()
    screen = ctrl.detect_screen(feed_xml)
    if screen == Screen.HOME_FEED:
        print(f"  PASS: detected as {screen.value}")
        passed += 1
    else:
        print(f"  FAIL: detected as {screen.value} (expected HOME_FEED)")
        failed += 1

# Test 3: Post author detection from saved feed XML
print("\nTEST 3: Post author detection")
feed2_path = 'test_results/current_screen.xml'
if os.path.exists(feed2_path):
    with open(feed2_path, 'r', encoding='utf-8') as f:
        feed_xml2 = f.read()
    
    # Replicate _get_post_author_from_xml logic
    # Method 1: row_feed_profile_header content-desc
    header = ctrl._find_in_xml(feed_xml2, resource_id='row_feed_profile_header')
    if header:
        desc = header.get('content_desc', '')
        print(f"  Header content_desc: '{desc}'")
        if desc:
            username = desc.split(' ')[0].strip()
            if username and username not in ('Sponsored', 'Suggested', 'Photo'):
                print(f"  PASS: Method 1 found author: '{username}'")
                passed += 1
            else:
                print(f"  FAIL: Method 1 got excluded word: '{username}'")
                failed += 1
        else:
            print("  Method 1: empty content_desc")
    else:
        print("  Method 1: row_feed_profile_header not found")
    
    # Method 3 new: Profile picture of username
    profile_pics = ctrl._find_all_in_xml(
        feed_xml2, desc_pattern=r"Profile picture of .+")
    if profile_pics:
        for pic in profile_pics:
            desc = pic.get('content_desc', '')
            if desc.startswith('Profile picture of '):
                username = desc[len('Profile picture of '):].strip()
                print(f"  PASS: Method 3 found author: '{username}'")
                passed += 1
                break
    else:
        print("  Method 3: no 'Profile picture of' matches")

    # Method 5: posted a pattern
    posted_match = re.search(
        r'content-desc="(\w[\w._]+)\s+posted\s+a\s+', feed_xml2)
    if posted_match:
        print(f"  PASS: Method 5 found: '{posted_match.group(1)}'")
        passed += 1
    else:
        print("  Method 5: no 'posted a' match")

print(f"\n{'='*40}")
print(f"RESULTS: {passed} passed, {failed} failed")
print(f"{'='*40}")
