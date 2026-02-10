import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
cur = conn.cursor()

# Find harrer_private account
cur.execute("SELECT id, username, device_serial FROM accounts WHERE username LIKE '%harrer%'")
for r in cur.fetchall():
    print(f"Account {r[0]}: {r[1]} on {r[2]}")
    
    # Check all source types for this account
    cur.execute("SELECT source_type, COUNT(*) FROM account_sources WHERE account_id=? GROUP BY source_type", (r[0],))
    sources = cur.fetchall()
    print(f"  Source types: {sources}")
    
    # Check settings for share-related keys
    cur.execute("SELECT settings_json FROM account_settings WHERE account_id=?", (r[0],))
    row = cur.fetchone()
    if row:
        s = json.loads(row[0])
        share_keys = [k for k in s.keys() if 'share' in k.lower() or 'shared' in k.lower()]
        print(f"  Share setting keys:")
        for k in share_keys:
            print(f"    {k} = {s[k]}")

# Check what source_types exist in the whole DB
print("\n--- All source types ---")
cur.execute("SELECT DISTINCT source_type FROM account_sources ORDER BY source_type")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Check the LIST_FILE_MAPPING for any share-specific source
print("\n--- Checking for share-specific source types in Onimator docs ---")
# In old Onimator, check if there was a shared_post_sources or similar
with open('ONIMATOR_DOCS.md', 'r', encoding='utf-8') as f:
    content = f.read()
    for line in content.split('\n'):
        if 'share' in line.lower() and ('source' in line.lower() or '.txt' in line.lower()):
            print(f"  {line.strip()}")

conn.close()
