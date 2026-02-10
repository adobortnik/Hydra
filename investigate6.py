"""Step 5: Force scroll to absolute top, find DM button, then navigate to DM inbox."""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import uiautomator2 as u2

d = u2.connect('10.1.11.4:5555')

# Double-click home tab to go to top
home = d(resourceIdMatches='.*feed_tab')
if home.exists(timeout=3):
    home.click()
    time.sleep(0.5)
    home.click()  # Double click goes to top
    time.sleep(2)
    print("Double-clicked home tab")

# Aggressive scroll up
w, h = d.window_size()
for i in range(3):
    d.swipe(w//2, int(h*0.2), w//2, int(h*0.8), duration=0.3)
    time.sleep(0.5)
time.sleep(2)

xml = d.dump_hierarchy()
with open('test_results/feed_absolute_top.xml', 'w', encoding='utf-8') as f:
    f.write(xml)
d.screenshot('test_results/feed_absolute_top.png')
print(f"XML: {len(xml)} bytes")

# Search for action bar contents
print("\n=== action_bar_container contents (all children) ===")
# Find the action_bar_container and get its bounds
for m in re.finditer(r'<node[^>]*resource-id="[^"]*action_bar_container[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    print(f"  action_bar_container: [{x1},{y1}][{x2},{y2}]")

# All resource IDs containing 'action_bar'
print("\n=== All action_bar resource IDs ===")
for m in set(re.findall(r'resource-id="([^"]*action_bar[^"]*)"', xml)):
    print(f"  {m}")

# All resource IDs containing 'inbox' or 'direct' or 'messenger'
print("\n=== inbox/direct/messenger resource IDs ===")
for m in set(re.findall(r'resource-id="([^"]*(?:inbox|direct|messenger)[^"]*)"', xml, re.IGNORECASE)):
    print(f"  {m}")

# All elements in the y=110-220 range (where action bar should be)
print("\n=== Elements in y range 100-250 ===")
for m in re.finditer(r'<node[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*', xml):
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if 100 <= y1 <= 250 and y2 <= 350 and (x2-x1) < 300:  # Small elements in action bar area
        node = m.group(0)
        rid_m = re.search(r'resource-id="([^"]*)"', node)
        desc_m = re.search(r'content-desc="([^"]*)"', node)
        text_m = re.search(r' text="([^"]*)"', node)
        cls_m = re.search(r'class="([^"]*)"', node)
        rid = rid_m.group(1).split(':id/')[-1] if rid_m and ':id/' in rid_m.group(1) else ''
        desc = desc_m.group(1) if desc_m else ''
        text = text_m.group(1) if text_m else ''
        cls = cls_m.group(1).split('.')[-1] if cls_m else ''
        if desc or rid or text:
            print(f"  [{rid}] {cls} desc='{desc}' text='{text}' [{x1},{y1}][{x2},{y2}]")

# Also check ALL content-desc values
print("\n=== All unique content-desc values in XML ===")
descs = set(re.findall(r'content-desc="([^"]+)"', xml))
for d_val in sorted(descs):
    if len(d_val) < 60:
        print(f"  {d_val}")

print("\nDone")
