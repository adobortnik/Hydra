"""Collect all XML dumps in one go. Bot is stopped."""
import uiautomator2 as u2
import subprocess
import time
import os
import sys

SERIAL = '10.1.11.4:5555'
OUT = r'C:\Users\TheLiveHouse\clawd\phone-farm\xml_dumps\dm_and_comments'
os.makedirs(OUT, exist_ok=True)

print("Connecting...")
d = u2.connect(SERIAL)
print("Connected:", d.app_current()['package'])

def adb(cmd):
    return subprocess.run(f"adb -s {SERIAL} {cmd}", shell=True, capture_output=True, text=True, timeout=15).stdout.strip()

def save(name):
    xml = d.dump_hierarchy()
    p = os.path.join(OUT, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(xml)
    print(f"  SAVED: {name} ({len(xml):,} bytes)")

def launch(pkg):
    print(f"Launching {pkg}...")
    adb(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
    time.sleep(5)
    c = d.app_current()
    print(f"  Current: {c['package']}")
    if c['package'] != pkg:
        adb(f"shell am start -n {pkg}/com.instagram.mainactivity.InstagramMainActivity")
        time.sleep(5)
        c = d.app_current()
        print(f"  After retry: {c['package']}")
    return c['package'] == pkg

def dismiss():
    for txt in ["Not Now", "Not now", "OK", "Allow", "Skip", "SKIP"]:
        try:
            b = d(text=txt)
            if b.exists(timeout=0.3):
                b.click()
                time.sleep(0.3)
                print(f"  Dismissed: {txt}")
        except:
            pass

def go_home(pkg):
    for _ in range(4):
        d.press('back')
        time.sleep(0.3)
    time.sleep(1)
    if d.app_current()['package'] != pkg:
        launch(pkg)
    dismiss()
    h = d(description="Home")
    if h.exists(timeout=2):
        h.click()
    else:
        d.click(108, 1840)
    time.sleep(2)
    dismiss()

def do_clone(pkg, prefix):
    print(f"\n{'='*50}")
    print(f"CLONE: {prefix} ({pkg})")
    print(f"{'='*50}")
    
    if not launch(pkg):
        print(f"FAILED to launch {pkg}!")
        return
    dismiss()
    time.sleep(2)
    
    # 1. Home feed
    print("\n[1] Home Feed")
    go_home(pkg)
    d.swipe(540, 1200, 540, 800, duration=0.3)
    time.sleep(2)
    save(f"{prefix}_feed_comment_button.xml")
    
    # 2. DM Inbox
    print("\n[2] DM Inbox")
    dm = d(resourceId=f"{pkg}:id/action_bar_inbox_button")
    if dm.exists(timeout=2):
        dm.click()
        print("  Clicked DM by resource ID")
    else:
        clicked = False
        for desc in ["Direct", "Messenger", "Inbox", "Messages"]:
            el = d(description=desc)
            if el.exists(timeout=1):
                el.click()
                print(f"  Clicked DM by desc={desc}")
                clicked = True
                break
        if not clicked:
            d.click(1020, 120)
            print("  Clicked top-right")
    time.sleep(3)
    dismiss()
    save(f"{prefix}_dm_inbox.xml")
    
    # 3. DM Thread
    print("\n[3] DM Thread")
    tl = d(resourceId=f"{pkg}:id/inbox_refreshable_thread_list_recyclerview")
    if tl.exists(timeout=2):
        print("  Found thread list recycler")
        try:
            ch = tl.child(className="android.widget.FrameLayout")
            if ch.exists(timeout=2):
                ch.click()
                print("  Clicked first thread child")
            else:
                d.click(540, 400)
                print("  Tapped 540,400")
        except:
            d.click(540, 400)
            print("  Exception, tapped 540,400")
    else:
        d.click(540, 400)
        print("  No thread list, tapped 540,400")
    time.sleep(3)
    dismiss()
    save(f"{prefix}_dm_thread.xml")
    d.press('back')
    time.sleep(2)
    
    # 4. New Message
    print("\n[4] New Message")
    found = False
    for desc in ["New Message", "New message", "Compose", "Write", "Create"]:
        el = d(description=desc)
        if el.exists(timeout=1):
            el.click()
            print(f"  Clicked by desc={desc}")
            found = True
            break
    if not found:
        d.click(1020, 120)
        print("  Clicked top-right")
    time.sleep(3)
    dismiss()
    save(f"{prefix}_dm_new_message.xml")
    d.press('back')
    time.sleep(2)
    
    # 5. Comment Section
    print("\n[5] Comment Section")
    go_home(pkg)
    time.sleep(2)
    d.swipe(540, 1200, 540, 600, duration=0.5)
    time.sleep(2)
    
    cb = d(resourceId=f"{pkg}:id/row_feed_button_comment")
    if cb.exists(timeout=3):
        cb.click()
        print("  Clicked comment by resource ID")
    else:
        cd = d(description="Comment")
        if cd.exists(timeout=2):
            cd.click()
            print("  Clicked comment by desc")
        else:
            print("  Not found, scrolling...")
            d.swipe(540, 1400, 540, 600, duration=0.5)
            time.sleep(2)
            cb2 = d(resourceId=f"{pkg}:id/row_feed_button_comment")
            if cb2.exists(timeout=3):
                cb2.click()
                print("  Clicked after scroll")
            else:
                cd2 = d(description="Comment")
                if cd2.exists(timeout=2):
                    cd2.click()
                    print("  Clicked comment desc after scroll")
                else:
                    print("  STILL not found - dumping feed")
    time.sleep(3)
    dismiss()
    save(f"{prefix}_comment_section.xml")
    d.press('back')
    time.sleep(1)
    d.press('back')
    time.sleep(1)
    
    print(f"\nDone with {prefix}!")

# Run for both clones
do_clone('com.instagram.androif', 'androif')
do_clone('com.instagram.androih', 'androih')

# List results
print(f"\n{'='*50}")
print("ALL DONE! Files:")
for f in sorted(os.listdir(OUT)):
    if f.endswith('.xml'):
        sz = os.path.getsize(os.path.join(OUT, f))
        print(f"  {f} ({sz:,} bytes)")
