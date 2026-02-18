"""Test: tap gallery thumbnail by coordinates"""
import uiautomator2 as u2
import time, sys

d = u2.connect('10.1.10.238:5555')
print("Connected")

# First thumbnail bounds: [6,600][358,1225]
# Center: (182, 912)
cx, cy = 182, 912
print(f"Tapping center of first thumbnail at ({cx}, {cy})...")
d.click(cx, cy)
time.sleep(3)

xml = d.dump_hierarchy()
if 'Next' in xml or 'NEXT' in xml:
    print("SUCCESS: Next button found!")
elif 'Add' in xml:
    print("SUCCESS: Add button found!")
else:
    import re
    # Look for any IG-specific elements
    texts = [m for m in re.findall(r'text="([^"]+)"', xml) if m and 'systemui' not in m.lower()]
    descs = [m for m in re.findall(r'content-desc="([^"]+)"', xml) if m and 'notification' not in m.lower() and 'systemui' not in m.lower()]
    pkg = re.findall(r'package="([^"]+)"', xml)
    pkgs = list(set(pkg))
    print(f"Packages: {pkgs}")
    print(f"Texts: {texts[:15]}")
    print(f"Descs: {descs[:15]}")

# Try a second approach - long click
print("\nNow trying LONG click on thumbnail...")
d.long_click(cx, cy, duration=0.5)
time.sleep(3)

xml2 = d.dump_hierarchy()
texts2 = [m for m in re.findall(r'text="([^"]+)"', xml2) if m]
print(f"After long click texts: {texts2[:15]}")
