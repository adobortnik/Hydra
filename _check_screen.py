"""Dump current screen elements."""
import uiautomator2 as u2
import re

d = u2.connect('10.1.11.4:5555')
xml = d.dump_hierarchy()

texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml)]
descs = [m.group(1) for m in re.finditer(r'content-desc="([^"]+)"', xml)]

print('=== All texts ===')
for t in texts[:30]:
    print(f'  {t}')
print('\n=== All descs ===')
for d2 in descs[:30]:
    print(f'  {d2}')

# Find anything that looks like Share/Post/OK/Done near top-right
print('\n=== Potential Share/Post buttons ===')
for pattern in [r'text="(Share|Post|OK|Done|Publish|Next)"', r'content-desc="[^"]*(?:Share|Post|OK|Done|Publish|Next)[^"]*"']:
    for m in re.finditer(pattern, xml, re.IGNORECASE):
        # Find bounds
        start = max(0, m.start() - 300)
        chunk = xml[start:m.end() + 200]
        bounds = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', chunk)
        if bounds:
            print(f'  {m.group(0)} @ bounds=[{bounds.group(1)},{bounds.group(2)}][{bounds.group(3)},{bounds.group(4)}]')
        else:
            print(f'  {m.group(0)} (no bounds found nearby)')
