import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

for username in ['modeljagger', 'mrjaggerclub', 'jaggerlifestyle']:
    row = conn.execute("""
        SELECT a.id, a.device_serial, ast.settings_json
        FROM accounts a JOIN account_settings ast ON ast.account_id = a.id
        WHERE a.username = ?
    """, (username,)).fetchone()
    if not row:
        print(f"{username}: NOT FOUND")
        continue
    s = json.loads(row['settings_json'])
    print(f"{username} ({row['device_serial']}):")
    print(f"  mention={s.get('story_mention_enabled')}, target={s.get('story_mention_target')}")
    print(f"  link={s.get('story_link_sticker_enabled')}, url={s.get('story_link_sticker_url')}")
    print(f"  share_limit={s.get('shared_post_limit_perday')}")

conn.close()
