import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Pick 2 accounts that are actively running on our local devices
# Account 1: mention test
# Account 2: link test

test_accounts = {
    'jaggerlifestyle': {
        'story_mention_enabled': True,
        'story_mention_target': 'jaggerprime',
        'story_link_sticker_enabled': False,
        'story_link_sticker_url': '',
    },
    'mrjaggerclub': {
        'story_mention_enabled': False,
        'story_mention_target': '',
        'story_link_sticker_enabled': True,
        'story_link_sticker_url': 'https://instagram.com/jaggerprime',
    },
}

for username, updates in test_accounts.items():
    row = conn.execute("""
        SELECT a.id, ast.settings_json 
        FROM accounts a 
        JOIN account_settings ast ON ast.account_id = a.id 
        WHERE a.username = ?
    """, (username,)).fetchone()
    
    if not row:
        print(f"  {username}: NOT FOUND")
        continue
    
    s = json.loads(row['settings_json'])
    
    # Apply updates
    for k, v in updates.items():
        s[k] = v
    
    # Make sure share_to_story is enabled
    s['enable_shared_post'] = True
    
    conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?",
                (json.dumps(s), row['id']))
    
    # Show what we set
    features = []
    if updates.get('story_mention_enabled'):
        features.append(f"MENTION @{updates['story_mention_target']}")
    if updates.get('story_link_sticker_enabled'):
        features.append(f"LINK {updates['story_link_sticker_url']}")
    
    print(f"  {username}: {', '.join(features)}")

conn.commit()
conn.close()
print("\nDone! Settings updated. Features will apply on next share_to_story action.")
