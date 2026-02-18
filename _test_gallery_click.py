"""Quick test: just try clicking the first gallery_grid_item_thumbnail"""
import uiautomator2 as u2
import time

d = u2.connect('10.1.10.238:5555')
print("Connected")

# Try the resource-id match
el = d(resourceIdMatches=".*gallery_grid_item_thumbnail.*")
print(f"gallery_grid_item_thumbnail exists: {el.exists(timeout=3)}")
if el.exists():
    info = el[0].info
    print(f"  First item: {info.get('contentDescription', 'no desc')}")
    print(f"  Bounds: {info.get('bounds', 'unknown')}")
    print(f"  Class: {info.get('className', 'unknown')}")
    print(f"  Clickable: {info.get('clickable', 'unknown')}")
    print("  Clicking first thumbnail...")
    el[0].click()
    time.sleep(3)
    print("  Clicked! Checking screen...")
    
    # Now check what's on screen
    d2 = d.dump_hierarchy()
    if 'Next' in d2 or 'NEXT' in d2:
        print("  SUCCESS: 'Next' button found on screen!")
    else:
        # Check for trim/editor indicators
        import re
        texts = re.findall(r'text="([^"]+)"', d2)
        descs = re.findall(r'content-desc="([^"]+)"', d2)
        non_empty = [t for t in texts if t] + [d for d in descs if d]
        print(f"  Screen elements: {non_empty[:20]}")
else:
    print("  Not found! Trying other selectors...")
    for rid in ['gallery_grid_item_image', 'media_thumbnail']:
        el2 = d(resourceIdMatches=f".*{rid}.*")
        print(f"  {rid}: exists={el2.exists(timeout=2)}")
