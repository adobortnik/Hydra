import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
conn.execute("INSERT OR IGNORE INTO account_sources (account_id, source_type, value) VALUES (449, 'sources', 'imsummerxiris')")
conn.execute("INSERT OR IGNORE INTO account_sources (account_id, source_type, value) VALUES (449, 'sources', 'sophieraiin.fanpage')")
conn.commit()
rows = conn.execute("SELECT * FROM account_sources WHERE account_id=449").fetchall()
print(f"Sources for 449: {len(rows)}")
for r in rows:
    print(r)
