import sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open('dashboard/templates/job_orders_v2.html', 'rb') as f:
    raw = f.read()

for m in re.finditer(b'type-icon">(.*?)</span>', raw):
    icon_bytes = m.group(1)
    print(f"Icon hex: {icon_bytes.hex()}")

# Find TYPE_ICONS
idx = raw.find(b'TYPE_ICONS')
if idx > 0:
    line_end = raw.find(b'\n', idx)
    line = raw[idx:line_end]
    print(f"\nTYPE_ICONS hex: {line.hex()}")
    
    # Find each emoji in the line
    for m2 in re.finditer(b"'([^']*?)'", line):
        val = m2.group(1)
        if any(b > 127 for b in val):
            print(f"  Emoji hex: {val.hex()} = {val.decode('utf-8', errors='replace')}")
