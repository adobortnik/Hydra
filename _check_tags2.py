import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
cur = conn.cursor()

# Check tags table
print("=== tags table ===")
cur.execute("PRAGMA table_info(tags)")
print("Columns:", [r[1] for r in cur.fetchall()])
cur.execute("SELECT COUNT(*) FROM tags")
print("Count:", cur.fetchone()[0])
cur.execute("SELECT * FROM tags LIMIT 10")
for r in cur.fetchall():
    print(f"  {r}")

# Check account_tags table
print("\n=== account_tags table ===")
cur.execute("PRAGMA table_info(account_tags)")
print("Columns:", [r[1] for r in cur.fetchall()])
cur.execute("SELECT COUNT(*) FROM account_tags")
print("Count:", cur.fetchone()[0])
cur.execute("SELECT * FROM account_tags LIMIT 10")
for r in cur.fetchall():
    print(f"  {r}")

# Check settings_json for tag references
print("\n=== Tags in settings_json ===")
cur.execute("SELECT account_id, settings_json FROM account_settings LIMIT 5")
for row in cur.fetchall():
    settings = json.loads(row[1])
    tag_keys = [k for k in settings.keys() if 'tag' in k.lower()]
    if tag_keys:
        print(f"  Account {row[0]} tag keys: {tag_keys}")
        for k in tag_keys:
            print(f"    {k} = {settings[k]}")

# Check what bulk_operations page is looking for
print("\n=== Checking bulk_operations route ===")
import re
with open('dashboard/simple_app.py', 'r', encoding='utf-8') as f:
    content = f.read()
    # Find bulk_operations related code
    for m in re.finditer(r'(bulk.?op|/bulk_op|tag.*api|/api/tag)', content, re.IGNORECASE):
        start = max(0, m.start()-100)
        end = min(len(content), m.end()+200)
        print(f"  ...{content[start:end]}...")
        print("---")

conn.close()
