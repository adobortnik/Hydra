"""
Dump the current screen's XML to analyze story editor UI elements.
Run this WHILE the story editor is visible on the device.
"""
import uiautomator2 as u2
import re
import sys
import os

serial = sys.argv[1] if len(sys.argv) > 1 else '10.1.11.4:5555'
adb_serial = serial.replace('_', ':')

print(f"Connecting to {adb_serial}...")
d = u2.connect(adb_serial)
print(f"Connected. Screen: {d.window_size()}")

xml = d.dump_hierarchy()

# Save full XML
dump_dir = os.path.join(os.path.dirname(__file__), 'automation', 'superproxy_dumps')
os.makedirs(dump_dir, exist_ok=True)
dump_path = os.path.join(dump_dir, 'story_editor_dump.xml')
with open(dump_path, 'w', encoding='utf-8') as f:
    f.write(xml)
print(f"\nFull XML saved to: {dump_path}")

# Find all clickable elements
print("\n=== CLICKABLE ELEMENTS ===")
clickable = re.findall(
    r'<node[^>]*?'
    r'text="([^"]*)"[^>]*?'
    r'resource-id="([^"]*)"[^>]*?'
    r'content-desc="([^"]*)"[^>]*?'
    r'clickable="true"[^>]*?'
    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    xml
)
for text, rid, desc, x1, y1, x2, y2 in clickable:
    label = text or desc or rid or '(no label)'
    print(f"  [{x1},{y1}][{x2},{y2}]  text='{text}'  desc='{desc}'  rid='{rid}'")

# Also find clickable with different attr order
print("\n=== ALL ELEMENTS WITH TEXT/DESC (from SuperProxy/IG package) ===")
nodes = re.findall(
    r'<node[^>]*?package="com\.instagram[^"]*"[^>]*?'
    r'text="([^"]*)"[^>]*?'
    r'content-desc="([^"]*)"[^>]*?'
    r'clickable="([^"]*)"[^>]*?'
    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    xml
)
for text, desc, click, x1, y1, x2, y2 in nodes:
    if text or desc:
        marker = '🟢' if click == 'true' else '⚪'
        print(f"  {marker} [{x1},{y1}][{x2},{y2}]  text='{text}'  desc='{desc}'  clickable={click}")

# Look for bottom area elements (story buttons are usually at bottom)
print("\n=== BOTTOM AREA ELEMENTS (y > 1400) ===")
all_nodes = re.findall(
    r'<node[^>]*?'
    r'text="([^"]*)"[^>]*?'
    r'resource-id="([^"]*)"[^>]*?'
    r'class="([^"]*)"[^>]*?'
    r'content-desc="([^"]*)"[^>]*?'
    r'clickable="([^"]*)"[^>]*?'
    r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    xml
)
for text, rid, cls, desc, click, x1, y1, x2, y2 in all_nodes:
    if int(y1) > 1400:
        marker = '🟢' if click == 'true' else '⚪'
        print(f"  {marker} [{x1},{y1}][{x2},{y2}]  text='{text}'  desc='{desc}'  class='{cls}'  rid='{rid}'")

print("\nDone!")
