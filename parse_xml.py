import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
xml = open(sys.argv[1], 'r', encoding='utf-8').read()
texts = [m for m in re.findall(r'text="([^"]+)"', xml) if m.strip()]
print("TEXTS:", texts[:30])
descs = [m for m in re.findall(r'content-desc="([^"]{1,80})"', xml) if m.strip() and 'notification' not in m.lower()]
print("DESCS:", descs[:20])
rids = [m.split('/')[-1] for m in re.findall(r'resource-id="([^"]+)"', xml) if 'instagram' in m]
print("IG-RIDS:", list(set(rids))[:30])
