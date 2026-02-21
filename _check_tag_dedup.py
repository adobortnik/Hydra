import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT a.id, a.username, a.device_serial, ast.settings_json
    FROM accounts a
    JOIN account_settings ast ON ast.account_id = a.id
    WHERE a.tag = 'jagger'
    ORDER BY a.username
""").fetchall()

print(f"Jagger accounts: {len(rows)}\n")

enabled = 0
disabled = 0
no_tags = 0

for r in rows:
    s = json.loads(r['settings_json'])
    tags = s.get('tags', '')
    enable_tags = s.get('enable_tags', False)
    enable_dedup = s.get('enable_dont_follow_sametag_accounts', False)
    
    status = "ON " if (enable_tags and enable_dedup and tags) else "OFF"
    if not tags:
        no_tags += 1
    if enable_tags and enable_dedup and tags:
        enabled += 1
    else:
        disabled += 1
    
    print(f"  {status} {r['username']:25s} tags='{tags}' enable_tags={enable_tags} dedup={enable_dedup}")

print(f"\nEnabled: {enabled}")
print(f"Disabled: {disabled}")
print(f"   No tags set: {no_tags}")

# Check action_history for duplicates
print("\n=== Checking for duplicate follows across jagger accounts ===")
dupes = conn.execute("""
    SELECT target_username, COUNT(DISTINCT username) as follower_count,
           GROUP_CONCAT(DISTINCT username) as followers
    FROM action_history
    WHERE action_type = 'follow' AND success = 1
      AND username IN (SELECT username FROM accounts WHERE tag = 'jagger')
      AND target_username IS NOT NULL
    GROUP BY target_username
    HAVING COUNT(DISTINCT username) > 1
    ORDER BY follower_count DESC
    LIMIT 20
""").fetchall()

print(f"Targets followed by multiple jagger accounts: {len(dupes)}")
for r in dupes:
    print(f"  @{r['target_username']:25s} followed by {r['follower_count']} accounts: {r['followers']}")

conn.close()
