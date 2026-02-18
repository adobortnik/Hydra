import uiautomator2 as u2
d = u2.connect('10.1.10.238:5555')
xml = d.dump_hierarchy()
for line in xml.split('>'):
    line = line.strip()
    if 'text="' in line and 'text=""' not in line:
        print(line[:200])
    if 'content-desc="' in line and 'content-desc=""' not in line:
        print(line[:200])
