import json, random, sys
sys.stdout.reconfigure(encoding='utf-8')

d = json.load(open('data/sk_cz_bios.json', 'r', encoding='utf-8'))

print("=== FEMALE BIO SAMPLES ===")
for s in random.sample(d['female_bios'], 8):
    print(f"  {s}")

print("\n=== MALE BIO SAMPLES ===")
for s in random.sample(d['male_bios'], 5):
    print(f"  {s}")

print("\n=== NEUTRAL SAMPLES ===")
for s in random.sample(d['neutral_bios'], 5):
    print(f"  {s}")

print("\n=== MINIMAL SAMPLES ===")
for s in random.sample(d['minimal_bios'], 5):
    print(f"  {s}")

# Check manifest
m = json.load(open('data/profile_assignment_manifest.json', 'r', encoding='utf-8'))
meta = m.get('meta', m.get('campaign', {}))
accts = m.get('accounts', m.get('assignments', []))
print(f"\n=== MANIFEST: {len(accts)} accounts ===")
# Show 5 sample assignments
for a in random.sample(accts, min(5, len(accts))):
    print(f"  @{a.get('new_username','?')} | bio: {a.get('new_bio','?')[:50]}... | pic: {a.get('pic_category', a.get('profile_pic_category','?'))}")
