import uiautomator2 as u2, sys
d = u2.connect('10.1.10.238:5555')
xml = d.dump_hierarchy()
for line in xml.split('>'):
    line = line.strip()
    has_text = 'text="' in line and 'text=""' not in line
    has_desc = 'content-desc="' in line and 'content-desc=""' not in line
    if has_text or has_desc:
        # extract just the key attributes
        import re
        t = re.search(r'text="([^"]*)"', line)
        cd = re.search(r'content-desc="([^"]*)"', line)
        rid = re.search(r'resource-id="([^"]*)"', line)
        cls = re.search(r'class="([^"]*)"', line)
        bounds = re.search(r'bounds="([^"]*)"', line)
        parts = []
        if t and t.group(1): parts.append(f'text="{t.group(1)}"')
        if cd and cd.group(1): parts.append(f'desc="{cd.group(1)}"')
        if rid and rid.group(1): parts.append(f'rid="{rid.group(1)}"')
        if cls: parts.append(f'cls="{cls.group(1).split(".")[-1]}"')
        if bounds: parts.append(f'bounds={bounds.group(1)}')
        try:
            sys.stdout.buffer.write((' | '.join(parts) + '\n').encode('utf-8', errors='replace'))
        except:
            pass
