import re
with open('test_results/live_story_editor.xml', 'r', encoding='utf-16') as f:
    xml = f.read()

# Extract all IG elements with content-desc or text
nodes = re.findall(r'resource-id="([^"]*)"[^>]*content-desc="([^"]*)"', xml)
texts = re.findall(r'text="([^"]+)"', xml)
descs = [(rid, desc) for rid, desc in nodes if desc and 'systemui' not in rid and 'samsung' not in rid]

print("=== CONTENT-DESC (IG elements) ===")
for rid, desc in descs:
    print(f'  rid={rid.split("/")[-1] if "/" in rid else rid}  desc="{desc}"')

print(f"\n=== ALL TEXT VALUES ===")
for t in texts:
    if t.strip():
        print(f'  "{t}"')

# Find key elements
print("\n=== KEY BUTTONS ===")
for pattern in ['add_text', 'asset_button', 'cancel', 'music', 'overflow', 'story_share', 'post_capture', 'edit_buttons']:
    matches = re.findall(rf'resource-id="[^"]*{pattern}[^"]*"[^>]*bounds="(\[[^\]]+\]\[[^\]]+\])"', xml)
    if matches:
        print(f'  {pattern}: bounds={matches[0]}')
    
    desc_matches = re.findall(rf'resource-id="[^"]*{pattern}[^"]*"[^>]*content-desc="([^"]*)"', xml)
    if desc_matches:
        print(f'  {pattern}: desc="{desc_matches[0]}"')
