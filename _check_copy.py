import sqlite3, json

conn = sqlite3.connect('db/phone_farm.db')
cur = conn.cursor()

# Check share settings across accounts on JACK 1 device
cur.execute("""
    SELECT a.username, s.settings_json 
    FROM accounts a 
    JOIN account_settings s ON a.id = s.account_id 
    WHERE a.device_serial = '10.1.11.4_5555'
""")
for r in cur.fetchall():
    settings = json.loads(r[1])
    esp = settings.get('enable_shared_post')
    espts = settings.get('enable_share_post_to_story')
    print(f"  {r[0]}: enable_shared_post={esp}, enable_share_post_to_story={espts}")

conn.close()
