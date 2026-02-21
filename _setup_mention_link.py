import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Get all active jagger accounts with share_to_story enabled
rows = conn.execute("""
    SELECT a.id, a.username, a.device_serial, s.settings_json
    FROM accounts a
    LEFT JOIN account_settings s ON s.account_id = a.id
    WHERE a.username LIKE '%jagger%' AND a.status = 'active'
    ORDER BY a.username
""").fetchall()

print(f"Found {len(rows)} active jagger accounts\n")

# Split: first half = mention, second half = link sticker
half = len(rows) // 2
mention_accounts = rows[:half]
link_accounts = rows[half:]

print("=== MENTION (first half) ===")
for r in mention_accounts:
    settings = json.loads(r['settings_json'] or '{}')
    settings['enable_shared_post'] = True
    settings['story_mention_enabled'] = True
    settings['story_mention_target'] = 'jaggerprime'
    settings['story_link_sticker_enabled'] = False
    settings['story_link_sticker_url'] = ''
    conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                 (json.dumps(settings), r['id']))
    print(f"  {r['username']:25s} -> mention @jaggerprime")

print(f"\n=== LINK STICKER (second half) ===")
for r in link_accounts:
    settings = json.loads(r['settings_json'] or '{}')
    settings['enable_shared_post'] = True
    settings['story_mention_enabled'] = False
    settings['story_mention_target'] = ''
    settings['story_link_sticker_enabled'] = True
    settings['story_link_sticker_url'] = 'https://instagram.com/jaggerprime'
    conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                 (json.dumps(settings), r['id']))
    print(f"  {r['username']:25s} -> link https://instagram.com/jaggerprime")

conn.commit()
conn.close()
print(f"\nDone! {len(mention_accounts)} mention + {len(link_accounts)} link")
