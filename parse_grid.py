"""Parse profile XML to find grid items"""
import re

with open('test_results/share_story_02_profile.xml', 'r', encoding='utf-8') as f:
    xml = f.read()

# Find nodes with 'Photo by' or 'Reel by' in content-desc
print("=== Grid items (Photo/Reel/photos) ===")
for m in re.finditer(r'<node([^>]*content-desc="[^"]*(?:Photo|Reel|photos)[^"]*"[^>]*)/?>', xml):
    attrs = m.group(1)
    desc = re.search(r'content-desc="([^"]*)"', attrs)
    bounds = re.search(r'bounds="([^"]*)"', attrs)
    cls = re.search(r'class="([^"]*)"', attrs)
    rid = re.search(r'resource-id="([^"]*)"', attrs)
    click = re.search(r'clickable="([^"]*)"', attrs)
    print(f"  desc={desc.group(1) if desc else ''}")
    print(f"    bounds={bounds.group(1) if bounds else ''} class={cls.group(1).split('.')[-1] if cls else ''} rid={rid.group(1) if rid else ''} clickable={click.group(1) if click else ''}")

# Find tab_icon elements (Grid/Reels/Tagged tabs on profile)
print("\n=== Profile tabs ===")
for m in re.finditer(r'<node([^>]*resource-id="[^"]*tab_icon[^"]*"[^>]*)/?>', xml):
    attrs = m.group(1)
    desc = re.search(r'content-desc="([^"]*)"', attrs)
    bounds = re.search(r'bounds="([^"]*)"', attrs)
    print(f"  tab: desc={desc.group(1) if desc else ''} bounds={bounds.group(1) if bounds else ''}")

# Find media_set_row elements 
print("\n=== media_set elements ===")
for pattern in ['media_set', 'profile_tab', 'profile_viewpager']:
    for m in re.finditer(rf'<node([^>]*resource-id="[^"]*{pattern}[^"]*"[^>]*)/?>', xml):
        attrs = m.group(1)
        bounds = re.search(r'bounds="([^"]*)"', attrs)
        cls = re.search(r'class="([^"]*)"', attrs)
        rid = re.search(r'resource-id="([^"]*)"', attrs)
        print(f"  {rid.group(1) if rid else ''} class={cls.group(1).split('.')[-1] if cls else ''} bounds={bounds.group(1) if bounds else ''}")

print("\nDONE")
