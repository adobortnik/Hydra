with open('dashboard/templates/job_orders_v2.html', 'rb') as f:
    raw = f.read()

# Find all 'type-icon' spans
import re
for m in re.finditer(b'type-icon">(.*?)</span>', raw):
    icon_bytes = m.group(1)
    print(f"Icon bytes: {icon_bytes.hex()}")
    print(f"Icon text: {icon_bytes.decode('utf-8', errors='replace')}")
    print()

# Also find the JS TYPE_ICONS line
idx = raw.find(b'TYPE_ICONS')
if idx > 0:
    line = raw[idx:idx+200]
    print(f"TYPE_ICONS line bytes: {line[:100].hex()}")
    print(f"TYPE_ICONS line text: {line.decode('utf-8', errors='replace')}")
