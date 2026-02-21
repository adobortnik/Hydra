import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
row = conn.execute("""
    SELECT settings_json FROM account_settings 
    WHERE account_id = (SELECT id FROM accounts WHERE username='jaggerlifestyle')
""").fetchone()

s = json.loads(row[0])
filters = s.get('filters', {})

print("=== Full filters config ===")
for k, v in sorted(filters.items()):
    print(f"  {k}: {v}")

print("\n=== Filter-related top-level keys ===")
for k, v in sorted(s.items()):
    if 'filter' in k.lower() or 'enable' in k.lower():
        print(f"  {k}: {v}")

conn.close()
