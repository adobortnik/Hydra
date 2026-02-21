import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')

row = conn.execute("""
    SELECT a.id, ast.settings_json 
    FROM accounts a 
    JOIN account_settings ast ON ast.account_id = a.id 
    WHERE a.username = 'modeljagger'
""").fetchone()

s = json.loads(row[1])
s['story_mention_enabled'] = True
s['story_mention_target'] = 'jaggerprime'
s['enable_shared_post'] = True
s['shared_post_limit_perday'] = 5

conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
            (json.dumps(s), row[0]))
conn.commit()
conn.close()
print("modeljagger: mention @jaggerprime enabled")
