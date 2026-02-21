import sqlite3, os, glob

base = r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4"

# Check device-level accounts.db
for f in glob.glob(os.path.join(base, "*/accounts.db")):
    db = sqlite3.connect(f)
    try:
        cols = [c[1] for c in db.execute("PRAGMA table_info(accounts)").fetchall()]
        print(f"=== {f} ===")
        print(f"Columns: {cols}")
        if 'tag' in cols or 'tags' in cols or 'group_tag' in cols:
            rows = db.execute("SELECT * FROM accounts").fetchall()
            for r in rows[:3]:
                print(r)
    except Exception as e:
        print(f"Error: {e}")
    db.close()

# Also check the-livehouse-dashboard
for f in glob.glob(os.path.join(base, "the-livehouse-dashboard/**/*.db"), recursive=True):
    db = sqlite3.connect(f)
    try:
        tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if any('account' in t.lower() for t in tables):
            print(f"\n=== {f} ===")
            print(f"Tables: {tables}")
            for t in tables:
                if 'account' in t.lower():
                    cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})").fetchall()]
                    print(f"  {t}: {cols}")
                    if 'tag' in cols:
                        rows = db.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
                        for r in rows: print(f"    {r}")
    except: pass
    db.close()

# Check uiAutomator bot_data
for f in glob.glob(os.path.join(base, "uiAutomator/bot_data/*.db")):
    db = sqlite3.connect(f)
    try:
        tables = [t[0] for t in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"\n=== {f} ===")
        print(f"Tables: {tables}")
        for t in tables:
            cols = [c[1] for c in db.execute(f"PRAGMA table_info({t})").fetchall()]
            if 'tag' in cols:
                print(f"  FOUND TAG in {t}: {cols}")
                rows = db.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
                for r in rows: print(f"    {r}")
    except: pass
    db.close()
