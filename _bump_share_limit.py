import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')

for username in ['jaggerlifestyle', 'mrjaggerclub']:
    row = conn.execute("""
        SELECT a.id, ast.settings_json 
        FROM accounts a 
        JOIN account_settings ast ON ast.account_id = a.id 
        WHERE a.username = ?
    """, (username,)).fetchone()
    
    s = json.loads(row[1])
    old_limit = s.get('shared_post_limit_perday', 1)
    s['shared_post_limit_perday'] = 5  # bump from default to allow more today
    
    conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                (json.dumps(s), row[0]))
    print(f"  {username}: share limit {old_limit} -> 5")

conn.commit()
conn.close()
print("Done!")
