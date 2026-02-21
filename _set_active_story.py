import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')

updates = {
    'jaggerframe': {
        'story_mention_enabled': True,
        'story_mention_target': 'jaggerprime',
        'story_link_sticker_enabled': False,
        'shared_post_limit_perday': 5,
    },
    'playwithjagger': {
        'story_mention_enabled': False,
        'story_link_sticker_enabled': True,
        'story_link_sticker_url': 'https://instagram.com/jaggerprime',
        'shared_post_limit_perday': 5,
    },
}

for username, changes in updates.items():
    row = conn.execute("""
        SELECT a.id, ast.settings_json FROM accounts a
        JOIN account_settings ast ON ast.account_id = a.id
        WHERE a.username = ?
    """, (username,)).fetchone()
    s = json.loads(row[1])
    s['enable_shared_post'] = True
    for k, v in changes.items():
        s[k] = v
    conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                (json.dumps(s), row[0]))
    feat = "MENTION" if changes.get('story_mention_enabled') else "LINK"
    print(f"  {username}: {feat}")

conn.commit()
conn.close()
print("Done!")
