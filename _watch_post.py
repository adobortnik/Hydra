"""Watch screen every 3 seconds and log what's happening."""
import uiautomator2 as u2
import re
import time

d = u2.connect('10.1.11.4:5555')
print("Watching screen... (Ctrl+C to stop)")

for i in range(60):
    try:
        xml = d.dump_hierarchy()
        texts = [m.group(1) for m in re.finditer(r'text="([^"]+)"', xml)]
        descs = [m.group(1) for m in re.finditer(r'content-desc="([^"]+)"', xml)]
        
        # Filter interesting ones
        interesting_texts = [t for t in texts if t not in ['', ' '] and not re.match(r'^\d+:\d+$', t) and t not in ['100%']]
        interesting_descs = [d2 for d2 in descs if any(kw in d2.lower() for kw in ['share', 'post', 'next', 'caption', 'ok', 'done', 'back', 'new'])]
        
        # Check for key screens
        has_share = 'Share' in xml or 'share' in xml
        has_next = 'Next' in xml
        has_caption = 'caption' in xml.lower() or 'Write a' in xml
        has_filter = 'Filter' in xml or 'Edit' in xml
        
        markers = []
        if has_share: markers.append('SHARE')
        if has_next: markers.append('NEXT')
        if has_caption: markers.append('CAPTION')
        if has_filter: markers.append('FILTER/EDIT')
        
        print(f"\n[{i*3}s] Markers: {markers}")
        print(f"  Texts: {interesting_texts[:10]}")
        if interesting_descs:
            print(f"  Descs: {interesting_descs[:5]}")
    except Exception as e:
        print(f"[{i*3}s] Error: {e}")
    
    time.sleep(3)
