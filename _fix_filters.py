import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Fix all jagger accounts - set min_followers to 0
rows = conn.execute("""
    SELECT a.id, a.username, s.settings_json 
    FROM accounts a 
    JOIN account_settings s ON a.id = s.account_id 
    WHERE a.tag = 'jagger'
""").fetchall()

count = 0
for r in rows:
    settings = json.loads(r['settings_json'])
    filters = settings.get('filters', {})
    old_min = filters.get('min_followers', '0')
    
    if filters and str(old_min) != '0':
        filters['min_followers'] = '0'
        settings['filters'] = filters
        conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                    (json.dumps(settings), r['id']))
        count += 1
        print(f"  {r['username']:25s} min_followers: {old_min} -> 0")

conn.commit()
print(f"\nUpdated {count} accounts: min_followers set to 0")
conn.close()
