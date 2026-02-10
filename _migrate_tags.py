import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
cur = conn.cursor()

# Get all unique tags from settings_json
cur.execute('SELECT account_id, settings_json FROM account_settings')
account_tags_map = {}  # tag_name -> [account_ids]

for row in cur.fetchall():
    try:
        s = json.loads(row[1])
        tag = s.get('tags', '').strip()
        if tag:
            if tag not in account_tags_map:
                account_tags_map[tag] = []
            account_tags_map[tag].append(row[0])
    except:
        pass

print(f"Found {len(account_tags_map)} unique tags:")
for tag, accts in sorted(account_tags_map.items()):
    print(f"  '{tag}' -> {len(accts)} accounts")

# Clear existing (only had 1 dummy entry)
cur.execute("DELETE FROM account_tags")
cur.execute("DELETE FROM tags")

# Insert tags
for tag_name in sorted(account_tags_map.keys()):
    cur.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))

# Get tag IDs back
cur.execute("SELECT id, name FROM tags")
tag_id_map = {r[1]: r[0] for r in cur.fetchall()}

# Insert account_tags
count = 0
for tag_name, account_ids in account_tags_map.items():
    tag_id = tag_id_map[tag_name]
    for acct_id in account_ids:
        cur.execute("INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)", (acct_id, tag_id))
        count += 1

conn.commit()
print(f"\nMigrated: {len(tag_id_map)} tags, {count} account-tag links")

# Verify
cur.execute("SELECT t.name, COUNT(at.account_id) FROM tags t LEFT JOIN account_tags at ON t.id = at.tag_id GROUP BY t.id ORDER BY t.name")
print("\nVerification:")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]} accounts")

conn.close()
