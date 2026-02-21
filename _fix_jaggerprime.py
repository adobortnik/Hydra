import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

r = conn.execute("SELECT id, follow_enabled FROM accounts WHERE username = 'jaggerprime'").fetchone()
if r:
    aid = r['id']
    print(f"jaggerprime: id={aid}, currently follow={r['follow_enabled']}")
    
    # Disable follow for jaggerprime
    conn.execute("UPDATE accounts SET follow_enabled = 'False' WHERE id = ?", (aid,))
    
    # Reset follow method
    s = conn.execute("SELECT settings_json FROM account_settings WHERE account_id = ?", (aid,)).fetchone()
    if s:
        settings = json.loads(s['settings_json'])
        settings['follow_method'] = {
            'follow_followers': False,
            'follow_likers': False,
            'follow_specific_sources': False,
            'follow_using_word_search': False
        }
        conn.execute("UPDATE account_settings SET settings_json = ? WHERE account_id = ?", 
                     (json.dumps(settings), aid))
    
    conn.commit()
    print("✅ jaggerprime excluded — follow disabled")
else:
    print("jaggerprime not found in DB")

conn.close()
