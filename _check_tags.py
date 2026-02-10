import sqlite3

# Check phone_farm.db
conn = sqlite3.connect('db/phone_farm.db')
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# Tag-related tables
tag_tables = [t for t in tables if 'tag' in t.lower()]
print("Tag-related tables:", tag_tables)

# Check accounts columns
cur.execute("PRAGMA table_info(accounts)")
cols = [r[1] for r in cur.fetchall()]
print("Account columns:", cols)

# Check if tags column exists
if 'tags' in cols:
    cur.execute("SELECT username, tags FROM accounts WHERE tags IS NOT NULL AND tags != '' LIMIT 10")
    rows = cur.fetchall()
    print(f"Accounts with tags: {len(rows)}")
    for r in rows:
        print(f"  {r[0]}: {r[1]}")
else:
    print("No 'tags' column in accounts table")

# Check account_settings for tags
if 'account_settings' in tables:
    cur.execute("PRAGMA table_info(account_settings)")
    sc = [r[1] for r in cur.fetchall()]
    print("account_settings columns:", sc)
    if 'settings_json' in sc:
        cur.execute("SELECT account_id, settings_json FROM account_settings LIMIT 3")
        for r in cur.fetchall():
            if 'tag' in str(r[1]).lower():
                print(f"  Account {r[0]} has tag in settings: {r[1][:200]}")

conn.close()

# Also check old devices.db
print("\n--- Checking devices.db ---")
try:
    conn2 = sqlite3.connect('devices.db')
    cur2 = conn2.cursor()
    cur2.execute("SELECT name FROM sqlite_master WHERE type='table'")
    t2 = [r[0] for r in cur2.fetchall()]
    print("Tables:", t2)
    tag_t = [t for t in t2 if 'tag' in t.lower()]
    print("Tag tables:", tag_t)
    for tt in tag_t:
        cur2.execute(f"SELECT * FROM {tt} LIMIT 5")
        print(f"  {tt} samples:", cur2.fetchall())
    conn2.close()
except Exception as e:
    print(f"devices.db error: {e}")

# Check Onimator folders for tags
import os, json
onimator_base = r"C:\Users\TheLiveHouse\Onimator"
if os.path.exists(onimator_base):
    print("\n--- Checking Onimator ---")
    accounts_dir = os.path.join(onimator_base, "accounts")
    if os.path.exists(accounts_dir):
        for acct in os.listdir(accounts_dir)[:3]:
            acct_path = os.path.join(accounts_dir, acct)
            for f in os.listdir(acct_path):
                if 'tag' in f.lower() or f == 'config.json':
                    fp = os.path.join(acct_path, f)
                    print(f"  {acct}/{f}: {open(fp).read()[:200]}")
