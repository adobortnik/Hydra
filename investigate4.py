"""Step 3: Find DM button and look at profile name children."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Read the feed XML
with open('test_results/current_screen.xml', 'r', encoding='utf-8') as f:
    xml = f.read()

# 1. Search for DM/inbox/messenger related elements
print("=== DM/Inbox/Messenger button search ===")
for pat in ['inbox', 'direct', 'messenger', 'Messenger', 'Direct', 'dm_button', 'mail', 'chat']:
    matches = re.findall(r'<node[^>]*' + pat + r'[^>]*', xml, re.IGNORECASE)
    for m in matches:
        print(f"  [{pat}] {m[:200]}")

# 2. Search for top action bar elements
print("\n=== Action bar elements ===")
for pat in ['action_bar', 'title_bar', 'toolbar', 'header']:
    matches = re.findall(r'resource-id="([^"]*' + pat + r'[^"]*)"', xml, re.IGNORECASE)
    for m in set(matches):
        print(f"  {m}")

# 3. Look at content-desc with 'message' or 'inbox' or 'direct'
print("\n=== Content-desc with message/inbox/direct ===")
descs = re.findall(r'content-desc="([^"]*(?:message|inbox|direct|chat|mail)[^"]*)"', xml, re.IGNORECASE)
for d in set(descs):
    print(f"  {d}")

# 4. All clickable elements in top area (bounds y < 300)
print("\n=== Clickable elements in top 300px ===")
for m in re.finditer(r'<node[^>]*clickable="true"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*', xml):
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if y1 < 300:
        node = m.group(0)
        rid_m = re.search(r'resource-id="([^"]*)"', node)
        desc_m = re.search(r'content-desc="([^"]*)"', node)
        text_m = re.search(r' text="([^"]*)"', node)
        rid = rid_m.group(1) if rid_m else ''
        desc = desc_m.group(1) if desc_m else ''
        text = text_m.group(1) if text_m else ''
        short_rid = rid.split(':id/')[-1] if ':id/' in rid else rid
        print(f"  [{short_rid}] desc='{desc}' text='{text}' bounds=[{x1},{y1}][{x2},{y2}]")

# 5. Detailed view of row_feed_profile_header context (50 chars each side of username)
print("\n=== Around first row_feed_profile_header ===")
idx = xml.find('row_feed_profile_header')
if idx >= 0:
    # Find the enclosing node
    node_start = xml.rfind('<node', 0, idx)
    # Find the NEXT few nodes after it
    chunk = xml[node_start:node_start+2000]
    # Print each node
    for line in chunk.split('<node'):
        if line.strip():
            print(f"  <node{line[:250]}")

print("\nDone")
