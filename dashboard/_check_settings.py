import sqlite3
DB = r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=== account_settings ===")
c.execute("PRAGMA table_info(account_settings)")
print("Columns:", [r[1] for r in c.fetchall()])
c.execute("SELECT COUNT(*) FROM account_settings")
print("Rows:", c.fetchone()[0])
c.execute("SELECT * FROM account_settings LIMIT 1")
cols = [d[0] for d in c.description]
row = c.fetchone()
if row:
    print("Sample:", dict(zip(cols, row)))

print("\n=== accounts (settings cols) ===")
c.execute("PRAGMA table_info(accounts)")
all_cols = [r[1] for r in c.fetchall()]
print("All cols:", all_cols)

print("\n=== account_sources ===")
c.execute("PRAGMA table_info(account_sources)")
print("Columns:", [r[1] for r in c.fetchall()])
c.execute("SELECT COUNT(*) FROM account_sources")
print("Rows:", c.fetchone()[0])

print("\n=== account_text_configs ===")
c.execute("PRAGMA table_info(account_text_configs)")
print("Columns:", [r[1] for r in c.fetchall()])
c.execute("SELECT COUNT(*) FROM account_text_configs")
print("Rows:", c.fetchone()[0])

conn.close()
