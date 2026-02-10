"""Step-by-step XML dump collection. Run with: python -u dump_step.py <step>"""
import uiautomator2 as u2
import subprocess
import time
import os
import sys

SERIAL = '10.1.11.4:5555'
OUTPUT_DIR = r'C:\Users\TheLiveHouse\clawd\phone-farm\xml_dumps\dm_and_comments'
os.makedirs(OUTPUT_DIR, exist_ok=True)

d = u2.connect(SERIAL)

def adb(cmd):
    r = subprocess.run(f"adb -s {SERIAL} {cmd}", shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def save(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    xml = d.dump_hierarchy()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(xml)
    print(f"Saved {filename} ({len(xml)} bytes)")
    return xml

def show_current():
    c = d.app_current()
    print(f"Current: {c['package']} / {c['activity']}")
    return c

def start_clone(pkg):
    adb(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
    time.sleep(5)
    c = show_current()
    if c['package'] != pkg:
        adb(f"shell am start -n {pkg}/com.instagram.mainactivity.InstagramMainActivity")
        time.sleep(5)
        c = show_current()
    return c['package'] == pkg

def dismiss():
    for txt in ["Not Now", "Not now", "OK", "Allow", "Skip"]:
        btn = d(text=txt)
        if btn.exists(timeout=0.3):
            btn.click()
            time.sleep(0.3)
            print(f"Dismissed: {txt}")

def go_home(pkg):
    for _ in range(4):
        d.press('back')
        time.sleep(0.3)
    time.sleep(1)
    c = d.app_current()
    if c['package'] != pkg:
        start_clone(pkg)
        time.sleep(2)
    dismiss()
    # Click home tab
    h = d(description="Home")
    if h.exists(timeout=2):
        h.click()
        time.sleep(2)
    else:
        # bottom-left
        d.click(108, 1840)
        time.sleep(2)

step = sys.argv[1] if len(sys.argv) > 1 else 'status'

if step == 'status':
    show_current()

# ===== ANDROIF STEPS =====
elif step == 'androif_start':
    ok = start_clone('com.instagram.androif')
    print(f"androif started: {ok}")
    dismiss()
    
elif step == 'androif_home':
    go_home('com.instagram.androif')
    show_current()
    
elif step == 'androif_feed':
    # Dump feed with comment button
    show_current()
    d.swipe(540, 1200, 540, 800, duration=0.3)
    time.sleep(2)
    save('androif_feed_comment_button.xml')

elif step == 'androif_dm_inbox':
    # Click DM button
    pkg = 'com.instagram.androif'
    dm = d(resourceId=f"{pkg}:id/action_bar_inbox_button")
    if dm.exists(timeout=2):
        dm.click()
        print("Clicked DM by resource ID")
    else:
        for desc in ["Direct", "Messenger", "Inbox", "Messages"]:
            el = d(description=desc)
            if el.exists(timeout=1):
                el.click()
                print(f"Clicked DM by desc={desc}")
                break
        else:
            # top-right
            d.click(1020, 120)
            print("Clicked top-right area")
    time.sleep(3)
    dismiss()
    save('androif_dm_inbox.xml')

elif step == 'androif_dm_thread':
    # Click first conversation thread
    pkg = 'com.instagram.androif'
    tl = d(resourceId=f"{pkg}:id/inbox_refreshable_thread_list_recyclerview")
    if tl.exists(timeout=2):
        print("Found thread list")
        try:
            ch = tl.child(className="android.widget.FrameLayout")
            if ch.exists(timeout=2):
                ch.click()
                print("Clicked first thread")
        except:
            d.click(540, 400)
            print("Tapped at (540,400)")
    else:
        print("No thread list found, tapping...")
        d.click(540, 400)
    time.sleep(3)
    dismiss()
    save('androif_dm_thread.xml')

elif step == 'androif_dm_back':
    d.press('back')
    time.sleep(2)
    show_current()

elif step == 'androif_dm_new':
    # Click new message button from DM inbox
    found = False
    for desc in ["New Message", "New message", "Compose", "Write", "Create"]:
        el = d(description=desc)
        if el.exists(timeout=1):
            el.click()
            print(f"Clicked new msg by desc={desc}")
            found = True
            break
    if not found:
        # Top-right of DM inbox
        d.click(1020, 120)
        print("Clicked top-right for new message")
    time.sleep(3)
    dismiss()
    save('androif_dm_new_message.xml')

elif step == 'androif_comment':
    # Click comment button from feed
    pkg = 'com.instagram.androif'
    go_home(pkg)
    time.sleep(2)
    d.swipe(540, 1200, 540, 600, duration=0.5)
    time.sleep(2)
    
    cb = d(resourceId=f"{pkg}:id/row_feed_button_comment")
    if cb.exists(timeout=3):
        cb.click()
        print("Clicked comment by resource ID")
    else:
        cd = d(description="Comment")
        if cd.exists(timeout=2):
            cd.click()
            print("Clicked comment by desc")
        else:
            print("Comment button not found! Scrolling more...")
            d.swipe(540, 1400, 540, 600, duration=0.5)
            time.sleep(2)
            cb = d(resourceId=f"{pkg}:id/row_feed_button_comment")
            if cb.exists(timeout=3):
                cb.click()
                print("Clicked comment after scroll")
            else:
                print("STILL not found. Dumping feed as-is.")
    time.sleep(3)
    dismiss()
    save('androif_comment_section.xml')

# ===== ANDROIH STEPS =====
elif step == 'androih_start':
    ok = start_clone('com.instagram.androih')
    print(f"androih started: {ok}")
    dismiss()

elif step == 'androih_home':
    go_home('com.instagram.androih')
    show_current()

elif step == 'androih_feed':
    show_current()
    d.swipe(540, 1200, 540, 800, duration=0.3)
    time.sleep(2)
    save('androih_feed_comment_button.xml')

elif step == 'androih_dm_inbox':
    pkg = 'com.instagram.androih'
    dm = d(resourceId=f"{pkg}:id/action_bar_inbox_button")
    if dm.exists(timeout=2):
        dm.click()
        print("Clicked DM by resource ID")
    else:
        for desc in ["Direct", "Messenger", "Inbox", "Messages"]:
            el = d(description=desc)
            if el.exists(timeout=1):
                el.click()
                print(f"Clicked DM by desc={desc}")
                break
        else:
            d.click(1020, 120)
            print("Clicked top-right area")
    time.sleep(3)
    dismiss()
    save('androih_dm_inbox.xml')

elif step == 'androih_dm_thread':
    pkg = 'com.instagram.androih'
    tl = d(resourceId=f"{pkg}:id/inbox_refreshable_thread_list_recyclerview")
    if tl.exists(timeout=2):
        print("Found thread list")
        try:
            ch = tl.child(className="android.widget.FrameLayout")
            if ch.exists(timeout=2):
                ch.click()
                print("Clicked first thread")
        except:
            d.click(540, 400)
            print("Tapped at (540,400)")
    else:
        print("No thread list found, tapping...")
        d.click(540, 400)
    time.sleep(3)
    dismiss()
    save('androih_dm_thread.xml')

elif step == 'androih_dm_back':
    d.press('back')
    time.sleep(2)
    show_current()

elif step == 'androih_dm_new':
    found = False
    for desc in ["New Message", "New message", "Compose", "Write", "Create"]:
        el = d(description=desc)
        if el.exists(timeout=1):
            el.click()
            print(f"Clicked new msg by desc={desc}")
            found = True
            break
    if not found:
        d.click(1020, 120)
        print("Clicked top-right for new message")
    time.sleep(3)
    dismiss()
    save('androih_dm_new_message.xml')

elif step == 'androih_comment':
    pkg = 'com.instagram.androih'
    go_home(pkg)
    time.sleep(2)
    d.swipe(540, 1200, 540, 600, duration=0.5)
    time.sleep(2)
    
    cb = d(resourceId=f"{pkg}:id/row_feed_button_comment")
    if cb.exists(timeout=3):
        cb.click()
        print("Clicked comment by resource ID")
    else:
        cd = d(description="Comment")
        if cd.exists(timeout=2):
            cd.click()
            print("Clicked comment by desc")
        else:
            print("Comment button not found! Scrolling more...")
            d.swipe(540, 1400, 540, 600, duration=0.5)
            time.sleep(2)
            cb = d(resourceId=f"{pkg}:id/row_feed_button_comment")
            if cb.exists(timeout=3):
                cb.click()
            else:
                print("STILL not found. Dumping as-is.")
    time.sleep(3)
    dismiss()
    save('androih_comment_section.xml')

elif step == 'back':
    d.press('back')
    time.sleep(1)
    show_current()

elif step == 'dump_raw':
    # Just dump whatever is on screen
    name = sys.argv[2] if len(sys.argv) > 2 else 'raw_dump.xml'
    save(name)

else:
    print(f"Unknown step: {step}")
    print("Steps: status, androif_start, androif_home, androif_feed, androif_dm_inbox,")
    print("  androif_dm_thread, androif_dm_back, androif_dm_new, androif_comment,")
    print("  androih_start, androih_home, androih_feed, androih_dm_inbox,")
    print("  androih_dm_thread, androih_dm_back, androih_dm_new, androih_comment,")
    print("  back, dump_raw <name>")
