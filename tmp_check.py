import sys
sys.stdout.reconfigure(encoding='utf-8')
import json

with open('data/sk_cz_names.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

print(f"Female first names: {len(d['female_first_names'])}")
print(f"Male first names: {len(d['male_first_names'])}")
print(f"Female surnames: {len(d['female_surnames'])}")
print(f"Male surnames: {len(d['male_surnames'])}")
print()
print(f"Sample female: {d['female_first_names'][:15]}")
print(f"Sample male: {d['male_first_names'][:15]}")
print(f"Sample female surnames: {d['female_surnames'][:15]}")
print(f"Sample male surnames: {d['male_surnames'][:15]}")
print()
print(f"Keys: {list(d.keys())}")
