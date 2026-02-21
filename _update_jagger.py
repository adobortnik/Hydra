import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Find all jagger accounts
rows = conn.execute("""
    SELECT a.id, a.device_serial, a.username, a.tag, a.follow_enabled
    FROM accounts a
    WHERE a.tag LIKE '%jagger%'
    ORDER BY a.tag, a.device_serial
""").fetchall()

print(f"Found {len(rows)} accounts with jagger tag:\n")

jagger_ids = []
skip_ids = []
for r in rows:
    tag = r['tag'] or ''
    is_prime = 'jaggerprime' in tag.lower()
    status = "SKIP (jaggerprime)" if is_prime else "WILL UPDATE"
    print(f"  [{r['id']}] {r['username']:25s} tag={tag:15s} follow={r['follow_enabled']:6s} -> {status}")
    if is_prime:
        skip_ids.append(r['id'])
    else:
        jagger_ids.append(r['id'])

print(f"\nAccounts to update: {len(jagger_ids)}")
print(f"Accounts to skip (jaggerprime): {len(skip_ids)}")

if not jagger_ids:
    print("No accounts to update!")
    sys.exit(0)

# Update follow_enabled on accounts table
conn.execute(f"""
    UPDATE accounts SET follow_enabled = 'True'
    WHERE id IN ({','.join(str(i) for i in jagger_ids)})
""")

# Update account_settings for follow method
for aid in jagger_ids:
    row = conn.execute("SELECT settings_json FROM account_settings WHERE account_id = ?", (aid,)).fetchone()
    if row:
        settings = json.loads(row['settings_json'])
    else:
        settings = {}
    
    # Set follow method to follow_followers
    settings['follow_method'] = {
        'follow_followers': True,
        'follow_likers': False,
        'follow_specific_sources': False,
        'follow_using_word_search': False
    }
    
    conn.execute("""
        INSERT INTO account_settings (account_id, settings_json, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(account_id) DO UPDATE SET
            settings_json = excluded.settings_json,
            updated_at = excluded.updated_at
    """, (aid, json.dumps(settings)))

conn.commit()
print(f"\n✅ Updated {len(jagger_ids)} accounts:")
print(f"   - follow_enabled = True")
print(f"   - follow_method = follow_followers (follow users' followers)")

# Verify
for aid in jagger_ids:
    r = conn.execute("SELECT username, follow_enabled FROM accounts WHERE id = ?", (aid,)).fetchone()
    s = conn.execute("SELECT settings_json FROM account_settings WHERE account_id = ?", (aid,)).fetchone()
    fm = json.loads(s['settings_json']).get('follow_method', {}) if s else {}
    print(f"   [{aid}] {r['username']:25s} follow={r['follow_enabled']}  method={fm}")

conn.close()
