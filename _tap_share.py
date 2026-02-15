"""Dismiss keyboard and tap Share."""
from automation.device_connection import get_connection
import time, re

conn = get_connection('10.1.11.4_5555')
if conn.status != 'connected':
    conn.connect()
    time.sleep(3)
d = conn.device

# Dismiss keyboard
d.press('back')
time.sleep(2)

# Check screen
xml = d.dump_hierarchy()
texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml) if m.group(1)]
print('Texts:', texts[:15])

# Tap Share  
share = d(text='Share')
if share.exists(timeout=3):
    share.click()
    print('SHARE TAPPED!')
    time.sleep(15)
    xml2 = d.dump_hierarchy()
    texts2 = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml2) if m.group(1)]
    print('After share:', texts2[:15])
    print('POST DONE!')
else:
    print('No Share button found')
    print('All texts:', texts[:25])
