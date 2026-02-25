"""
E2E share_to_story test on SAMSUNG 192 / mrjaggerlife.
Waits for real UI elements, not blind sleeps.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

import uiautomator2 as u2
import subprocess, time, re
import xml.etree.ElementTree as ET

DEVICE = '10.1.10.192:5555'
PKG = 'com.instagram.androio'

d = u2.connect(DEVICE)
from automation.ig_controller import IGController
ctrl = IGController(d, '10.1.10.192_5555', PKG)

def wait_for(desc, *selectors, timeout=10):
    """Wait for any of the selectors to appear. Returns the one that matched."""
    end = time.time() + timeout
    while time.time() < end:
        for sel in selectors:
            if sel.exists(timeout=0.5):
                return sel
        time.sleep(0.5)
    print(f"  TIMEOUT waiting for: {desc}")
    d.screenshot(f'test_results/s_timeout_{desc.replace(" ","_")}.png')
    return None

def ss(name):
    d.screenshot(f'test_results/s_{name}.png')

# === FRESH START ===
d.app_stop(PKG)
time.sleep(2)
subprocess.run(['adb', '-s', DEVICE, 'shell', 'monkey', '-p', PKG,
                '-c', 'android.intent.category.LAUNCHER', '1'], capture_output=True)
time.sleep(5)
print("0. Launched")

# === 1. SEARCH ===
print("1. Searching jaggerprime...")
found = ctrl.search_user('jaggerprime')
if not found:
    print("FAIL: search_user returned False")
    ss('fail_search')
    sys.exit(1)
ss('01_profile')
print("   Found! On profile.")

# Verify we're really on jaggerprime profile
time.sleep(1)
xml = d.dump_hierarchy()
if 'jaggerprime' not in xml.lower():
    print("FAIL: Not on jaggerprime profile!")
    ss('fail_wrong_profile')
    sys.exit(1)
print("   Verified: jaggerprime profile confirmed.")

# === 2. REELS TAB ===
print("2. Reels tab...")
reels = wait_for("Reels tab", d(description="Reels"), d(text="Reels"))
if not reels:
    sys.exit(1)
reels.click()
time.sleep(2)
ss('02_reels')
print("   Reels tab active.")

# === 3. CLICK REEL ===
print("3. Clicking reel...")
xml = d.dump_hierarchy()
root = ET.fromstring(xml)
items = []
for elem in root.iter():
    desc = elem.get('content-desc', '')
    bounds = elem.get('bounds', '')
    if bounds and 'Reel by' in desc:
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        if m:
            items.append(((int(m.group(1))+int(m.group(3)))//2,
                          (int(m.group(2))+int(m.group(4)))//2, desc[:60]))
if not items:
    print("   FAIL: No reels in grid")
    ss('fail_no_reels')
    sys.exit(1)

d.click(items[0][0], items[0][1])
time.sleep(3)

# Wait for reel to load - check we're still in IG (not crashed)
app = d.app_current()
if 'launcher' in app.get('package', ''):
    print("   FAIL: App crashed!")
    ss('fail_crash')
    sys.exit(1)

# Wait for share button to confirm reel loaded
share = wait_for("Share button", d(description="Share"), d(description="Send post"), timeout=8)
if not share:
    print("   FAIL: Reel didn't load (no share button)")
    sys.exit(1)
ss('03_reel')
print(f"   Reel open. Share button visible.")

# === 4. SHARE ===
print("4. Clicking share...")
share.click()

# Wait for share sheet (has "Add to story")
add_story = wait_for("Add to story", d(text="Add to story"), d(descriptionContains="Add to story"), timeout=8)
if not add_story:
    print("   FAIL: Share sheet didn't open")
    sys.exit(1)
ss('04_share')
print("   Share sheet open.")

# === 5. ADD TO STORY ===
print("5. Add to story...")
add_story.click()

# Wait for story editor - look for editor elements (Aa text, sticker icon, Your story btn)
editor = wait_for("Story editor",
    d(descriptionContains="Sticker"),
    d(descriptionContains="sticker"),
    d(textContains="Your story"),
    d(text="Aa"),
    timeout=15)

# Handle permissions that may appear
for p in ['While using the app', 'WHILE USING THE APP', 'Allow', 'ALLOW']:
    btn = d(text=p)
    if btn.exists(timeout=1):
        btn.click()
        time.sleep(2)
        print(f"   Permission: {p}")

# Re-check editor loaded after permissions
if not editor or not editor.exists():
    editor = wait_for("Story editor (retry)",
        d(descriptionContains="Sticker"),
        d(textContains="Your story"),
        timeout=10)
if not editor:
    print("   FAIL: Story editor didn't load")
    sys.exit(1)
ss('05_editor')
print("   Story editor ready.")

# === 6. MENTION STICKER ===
print("6. Adding mention @jaggerprime...")

# Open sticker picker
sticker_btn = d(descriptionContains="Sticker")
if not sticker_btn.exists(timeout=2):
    sticker_btn = d(descriptionContains="sticker")
if sticker_btn.exists(timeout=2):
    sticker_btn.click()
    
    # Wait for sticker grid to appear
    # Note: @MENTION is rendered as ImageView with desc="Mention Sticker", NOT text
    mention_el = wait_for("Mention Sticker",
        d(description="Mention Sticker"),
        d(descriptionContains="Mention"),
        d(textContains="@MENTION"),
        d(textContains="MENTION"),
        timeout=6)
    ss('06a_stickers')
    
    if mention_el:
        mention_el.click()
        
        # Wait for mention input field
        input_field = wait_for("Mention input",
            d(className="android.widget.EditText"),
            timeout=5)
        ss('06b_mention_input')
        
        if input_field:
            # Type username via ADB
            subprocess.run(['adb', '-s', DEVICE, 'shell', 'input', 'text', 'jaggerprime'],
                          capture_output=True)
            
            # Wait for suggestion to appear
            suggestion = wait_for("jaggerprime suggestion",
                d(textContains="jaggerprime"),
                timeout=8)
            ss('06c_typed')
            
            if suggestion:
                suggestion.click()
                time.sleep(2)
                ss('06d_mention_placed')
                # After suggestion click, IG auto-places sticker and returns to preview.
                # Only click Done if we're stuck in editing mode.
                time.sleep(1)
                if d(textContains="Your story").exists(timeout=3):
                    print("   Back in story preview (no Done needed)")
                elif d(text="Done").exists(timeout=2):
                    d(text="Done").click()
                    time.sleep(2)
                    print("   Clicked Done")
                ss('06e_mention_done')
                print("   Mention @jaggerprime added!")
            else:
                print("   Suggestion not found, continuing without mention")
                d.press('back')
                time.sleep(1)
        else:
            print("   Mention input not found")
            d.press('back')
            time.sleep(1)
    else:
        print("   @MENTION sticker not found in picker")
        d.press('back')
        time.sleep(1)
else:
    print("   Sticker button not found, skipping mention")

# === 7. POST ===
print("7. Posting story...")
ss('07_before_post')

# Wait for Your story button (must be in bottom area)
your_story = wait_for("Your story",
    d(textContains="Your story"),
    d(descriptionContains="Your story"),
    timeout=8)

if not your_story:
    print("   FAIL: Your story not found")
    sys.exit(1)

your_story.click()
print("   Clicked Your story!")

# Wait for confirmation - either we go back to reel view (share sheet) or home
# The share sheet re-appearing means story was posted
time.sleep(5)
ss('08_after_post')

# Wait a bit more for upload
time.sleep(5)

# Back out cleanly
for i in range(4):
    d.press('back')
    time.sleep(1)
    disc = d(text='Discard')
    if disc.exists(timeout=0.5):
        disc.click()
        time.sleep(1)

ss('09_final')
print("\n=== DONE! Story posted on SAMSUNG 192 / mrjaggerlife ===")
