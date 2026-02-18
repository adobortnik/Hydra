"""Full XML dump of New Reel screen - IG elements only"""
import uiautomator2 as u2
import re, sys

d = u2.connect('10.1.10.238:5555')
xml = d.dump_hierarchy()

# Print ALL IG nodes
for node in re.finditer(r'<node\s([^/]*?)/?>', xml):
    attrs = node.group(1)
    pkg = re.search(r'package="([^"]*)"', attrs)
    pkg_v = pkg.group(1) if pkg else ''
    
    if 'instagram' not in pkg_v:
        continue
    
    rid = re.search(r'resource-id="([^"]*)"', attrs)
    cls = re.search(r'class="([^"]*)"', attrs)
    text = re.search(r'text="([^"]*)"', attrs)
    desc = re.search(r'content-desc="([^"]*)"', attrs)
    click = re.search(r'clickable="([^"]*)"', attrs)
    bounds = re.search(r'bounds="([^"]*)"', attrs)
    enabled = re.search(r'enabled="([^"]*)"', attrs)
    
    rid_v = rid.group(1).split('/')[-1] if rid else ''
    cls_v = cls.group(1).split('.')[-1] if cls else ''
    text_v = text.group(1) if text else ''
    desc_v = desc.group(1) if desc else ''
    click_v = click.group(1) if click else ''
    bounds_v = bounds.group(1) if bounds else ''
    en_v = enabled.group(1) if enabled else ''
    
    line = f"rid={rid_v:40s} cls={cls_v:15s} click={click_v:5s} en={en_v:5s} text={text_v:30s} desc={desc_v[:50]:50s} bounds={bounds_v}"
    try:
        sys.stdout.buffer.write((line + '\n').encode('utf-8', errors='replace'))
    except:
        pass
