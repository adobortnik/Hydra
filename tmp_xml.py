"""Get into sticker picker and dump XML to find MENTION element."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

import uiautomator2 as u2
import subprocess, time, re
import xml.etree.ElementTree as ET

DEVICE = '10.1.10.192:5555'
PKG = 'com.instagram.androio'

d = u2.connect(DEVICE)
d.app_stop(PKG)
time.sleep(2)
subprocess.run(['adb', '-s', DEVICE, 'shell', 'monkey', '-p', PKG,
                '-c', 'android.intent.category.LAUNCHER', '1'], capture_output=True)
time.sleep(5)

from automation.ig_controller import IGController
ctrl = IGController(d, '10.1.10.192_5555', PKG)

# Search and go to profile
ctrl.search_user('jaggerprime')
time.sleep(1)

# Reels tab
d(description="Reels").click()
time.sleep(2)

# Click first reel  
xml_str = d.dump_hierarchy()
root = ET.fromstring(xml_str)
for elem in root.iter():
    desc = elem.get('content-desc', '')
    bounds = elem.get('bounds', '')
    if bounds and 'Reel by' in desc:
        m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
        if m:
            d.click((int(m.group(1))+int(m.group(3)))//2, (int(m.group(2))+int(m.group(4)))//2)
            break
time.sleep(4)

# Share -> Add to story
d(description="Share").click()
time.sleep(3)
d(text="Add to story").click()
time.sleep(10)

# Handle permissions
for p in ['While using the app', 'Allow']:
    btn = d(text=p)
    if btn.exists(timeout=1):
        btn.click()
        time.sleep(2)
time.sleep(3)

# Open sticker picker
stk = d(descriptionContains="Sticker")
if not stk.exists(timeout=2):
    stk = d(descriptionContains="sticker")
if stk.exists(timeout=3):
    stk.click()
    time.sleep(3)
    
    # DUMP XML
    xml_str = d.dump_hierarchy()
    with open('test_results/sticker_picker_dump.xml', 'w', encoding='utf-8') as f:
        f.write(xml_str)
    
    root = ET.fromstring(xml_str)
    print("=== ALL elements with text or desc (non-empty, in sticker area) ===")
    for elem in root.iter():
        text = elem.get('text', '')
        desc = elem.get('content-desc', '')
        bounds = elem.get('bounds', '')
        clazz = elem.get('class', '')
        
        if (text or desc) and bounds:
            m = re.match(r'\[(\d+),(\d+)\]', bounds)
            if m:
                y = int(m.group(2))
                if y > 300:  # Below status bar
                    if text:
                        print(f'  TEXT="{text}" class={clazz} bounds={bounds}')
                    if desc and desc != text:
                        print(f'  DESC="{desc}" class={clazz} bounds={bounds}')
    
    print("\n=== Searching for mention/@ ===")
    mention_found = False
    for elem in root.iter():
        text = (elem.get('text', '') or '').lower()
        desc = (elem.get('content-desc', '') or '').lower()
        all_text = text + desc
        if 'mention' in all_text or '@' in all_text:
            bounds = elem.get('bounds', '')
            clazz = elem.get('class', '')
            print(f'  FOUND: text="{elem.get("text","")}" desc="{elem.get("content-desc","")}" class={clazz} bounds={bounds}')
            mention_found = True
    if not mention_found:
        print("  NOT FOUND in XML!")
else:
    print("Sticker button not found")

# Back out
for _ in range(5):
    d.press('back')
    time.sleep(0.5)
    disc = d(text='Discard')
    if disc.exists(timeout=0.5):
        disc.click()
        time.sleep(0.5)
