import sqlite3
db = sqlite3.connect('db/phone_farm.db')

# All tables
tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("All tables:", tables)

# Check for tag-related tables
for t in tables:
    if 'tag' in t.lower():
        cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n{t}: {cols}")
        rows = db.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
        for r in rows:
            print(f"  {r}")

# Check accounts table for tag column
print("\n=== accounts table ===")
cols = [c[1] for c in db.execute("PRAGMA table_info(accounts)").fetchall()]
print("Columns:", cols)

# Check if there's a tag column in accounts
if 'tag' in cols or 'tags' in cols:
    print("HAS TAG COLUMN!")
else:
    print("NO tag column in accounts")

db.close()
