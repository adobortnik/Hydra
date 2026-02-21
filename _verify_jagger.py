import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row
r = conn.execute("SELECT username, follow_enabled FROM accounts WHERE username = 'jaggerprime'").fetchone()
print(f"jaggerprime: follow_enabled={r['follow_enabled']}")

# Count
total = conn.execute("SELECT COUNT(*) FROM accounts WHERE tag = 'jagger' AND follow_enabled = 'True'").fetchone()[0]
print(f"Total jagger accounts with follow ON: {total}")
conn.close()
