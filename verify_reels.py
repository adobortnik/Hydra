"""Verify reels navigation actually goes to the Reels tab."""
import uiautomator2 as u2
from automation.ig_controller import IGController, Screen
import time, re

d = u2.connect('10.1.11.4:5555')
ctrl = IGController(d, '10.1.11.4_5555', 'com.instagram.androie')

# First go home
ctrl.navigate_to(Screen.HOME_FEED)
time.sleep(1)
print(f"Starting screen: {ctrl.detect_screen().value}")

# Navigate to REELS
print("Navigating to REELS...")
result = ctrl.navigate_to(Screen.REELS)
print(f"navigate_to result: {result}")
time.sleep(2)

screen = ctrl.detect_screen()
print(f"After nav to REELS: {screen.value}")

# Screenshot
d.screenshot().save("test_results/reels_verify.png")
print("Screenshot saved: reels_verify.png")

# Dump XML
xml = ctrl.dump_xml("reels_verify")

# Check for clips elements
for pattern in ["clips_viewer", "clips_tab", "reel_viewer", "clips_like"]:
    count = xml.lower().count(pattern.lower())
    print(f"  {pattern}: {count} matches")

# Check selected tab
for tab in ["feed_tab", "search_tab", "profile_tab", "clips_tab"]:
    match = re.search(
        r'resource-id="[^"]*' + tab + r'"[^>]*selected="(\w+)"', xml)
    if match:
        print(f"  TAB {tab}: selected={match.group(1)}")

# Swipe
print("\nSwiping to next reel...")
ctrl.swipe_to_next_reel()
time.sleep(2)
screen2 = ctrl.detect_screen()
print(f"After swipe: {screen2.value}")
d.screenshot().save("test_results/reels_after_swipe.png")

ctrl.navigate_to(Screen.HOME_FEED)
print("Done")
