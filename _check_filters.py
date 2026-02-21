import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT a.id, a.username, s.settings_json 
    FROM accounts a 
    JOIN account_settings s ON a.id = s.account_id 
    WHERE a.device_serial LIKE '%184%'
""").fetchall()

print(f"Accounts on .184 device: {len(rows)}\n")
for r in rows:
    settings = json.loads(r['settings_json'])
    filters = settings.get('filters', {})
    enable = settings.get('enable_filters', False)
    min_f = filters.get('min_followers', '0')
    max_f = filters.get('max_followers', '999999')
    min_posts = filters.get('min_posts', '0')
    print(f"  {r['username']:25s} enable_filters={enable}  min_followers={min_f}  max_followers={max_f}  min_posts={min_posts}")

conn.close()
