"""Step 4: Scroll to top, find DM button, then test DM inbox XML."""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2

d = u2.connect('10.1.11.4:5555')

# Click home tab to reset to top
home = d(resourceIdMatches='.*feed_tab')
if home.exists(timeout=3):
    home.click()
    time.sleep(2)
    print("Clicked home tab")

# Scroll up
w, h = d.window_size()
d.swipe(w//2, int(h*0.3), w//2, int(h*0.7), duration=0.5)
time.sleep(1)
d.swipe(w//2, int(h*0.3), w//2, int(h*0.7), duration=0.5)
time.sleep(2)

xml = d.dump_hierarchy()
with open('test_results/feed_top.xml', 'w', encoding='utf-8') as f:
    f.write(xml)
d.screenshot('test_results/feed_top.png')
print(f"Feed top XML: {len(xml)} bytes")

# Search for ALL elements in action bar area (y < 200)  
print("\n=== ALL elements with bounds in top 200px ===")
for m in re.finditer(r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*', xml):
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if y2 <= 200:
        node = m.group(0)
        rid_m = re.search(r'resource-id="([^"]*)"', node)
        desc_m = re.search(r'content-desc="([^"]*)"', node)
        text_m = re.search(r' text="([^"]*)"', node)
        cls_m = re.search(r'class="([^"]*)"', node)
        click_m = re.search(r'clickable="([^"]*)"', node)
        rid = rid_m.group(1).split(':id/')[-1] if rid_m and ':id/' in rid_m.group(1) else (rid_m.group(1) if rid_m else '')
        desc = desc_m.group(1) if desc_m else ''
        text = text_m.group(1) if text_m else ''
        cls = cls_m.group(1).split('.')[-1] if cls_m else ''
        click = click_m.group(1) if click_m else ''
        print(f"  [{rid or cls}] desc='{desc}' text='{text}' click={click} bounds=[{x1},{y1}][{x2},{y2}]")

# Search for ImageView/Button with content-desc in top area
print("\n=== Top ImageViews/Buttons with content-desc ===")
for m in re.finditer(r'<node[^>]*class="android\.widget\.(ImageView|Button|ImageButton)"[^>]*content-desc="([^"]+)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
    cls, desc, x1, y1, x2, y2 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
    if y1 < 300:
        print(f"  {cls}: desc='{desc}' bounds=[{x1},{y1}][{x2},{y2}]")

# Also check reverse attribute order
for m in re.finditer(r'<node[^>]*content-desc="([^"]+)"[^>]*class="android\.widget\.(ImageView|Button|ImageButton)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
    desc, cls, x1, y1, x2, y2 = m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
    if y1 < 300:
        print(f"  {cls}: desc='{desc}' bounds=[{x1},{y1}][{x2},{y2}]")

# Now look for the DM button by trying different desc patterns
print("\n=== Searching for DM button by description ===")
for desc_pat in ['Direct', 'Messenger', 'Messages', 'Inbox', 'Chat', 'DM', 'Send message']:
    btn = d(descriptionContains=desc_pat)
    if btn.exists(timeout=1):
        info = btn.info
        print(f"  FOUND: desc contains '{desc_pat}' - bounds={info.get('bounds',{})}")

# Try clicking the top-right area directly
print("\n=== Elements in top-right corner (x > 800, y < 200) ===")
for m in re.finditer(r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*', xml):
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if x1 > 800 and y2 < 200:
        node = m.group(0)
        rid_m = re.search(r'resource-id="([^"]*)"', node)
        desc_m = re.search(r'content-desc="([^"]*)"', node)
        cls_m = re.search(r'class="([^"]*)"', node)
        rid = rid_m.group(1).split(':id/')[-1] if rid_m and ':id/' in rid_m.group(1) else ''
        desc = desc_m.group(1) if desc_m else ''
        cls = cls_m.group(1).split('.')[-1] if cls_m else ''
        print(f"  [{rid}] {cls} desc='{desc}' bounds=[{x1},{y1}][{x2},{y2}]")

print("\nDone")
