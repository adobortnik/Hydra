import uiautomator2 as u2
import re

d = u2.connect('10.1.11.4:5555')
xml = d.dump_hierarchy()

with open('test_results/live_editor_u2.xml', 'w', encoding='utf-8') as f:
    f.write(xml)

# Extract all IG elements
nodes = re.findall(r'resource-id="([^"]*)"[^>]*content-desc="([^"]*)"[^>]*bounds="(\[[^\]]+\]\[[^\]]+\])"', xml)
descs = [(rid.split('/')[-1] if '/' in rid else rid, desc, bounds) for rid, desc, bounds in nodes if desc and 'systemui' not in rid and 'samsung' not in rid]

print("=== BUTTONS WITH CONTENT-DESC ===")
for rid, desc, bounds in descs:
    print(f'  rid={rid:<45} desc="{desc:<35}" bounds={bounds}')

texts_with_bounds = re.findall(r'text="([^"]+)"[^>]*bounds="(\[[^\]]+\]\[[^\]]+\])"', xml)
print(f"\n=== TEXT VALUES ===")
for t, bounds in texts_with_bounds:
    if t.strip() and len(t) < 50:
        print(f'  text="{t}"  bounds={bounds}')

# Specifically look for editor toolbar
print(f"\n=== EDITOR TOOLBAR SEARCH ===")
for pattern in ['add_text', 'asset_button', 'cancel', 'music', 'overflow', 'story_share', 
                'post_capture', 'edit_buttons', 'camera_resize', 'camera_ar']:
    matches = re.findall(rf'resource-id="[^"]*{pattern}[^"]*"[^>]*content-desc="([^"]*)"[^>]*bounds="(\[[^\]]+\]\[[^\]]+\])"', xml)
    for desc, bounds in matches:
        print(f'  {pattern}: desc="{desc}" bounds={bounds}')

print(f'\nXML size: {len(xml)} bytes')
