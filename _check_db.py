import sqlite3
import os

# Check phone_farm.db
db1 = 'db/phone_farm.db'
print(f"=== {db1} ===")
conn = sqlite3.connect(db1)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

if 'account_inventory' in tables:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(account_inventory)").fetchall()]
    print("account_inventory columns:", cols)
    cnt = conn.execute("SELECT COUNT(*) FROM account_inventory").fetchone()[0]
    print("account_inventory count:", cnt)

if 'accounts' in tables:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    print("accounts columns:", cols)

if 'account_health_events' in tables:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(account_health_events)").fetchall()]
    print("account_health_events columns:", cols)

conn.close()

# Check inventory DB
db2 = 'dashboard/data/account_inventory/account_inventory.db'
if os.path.exists(db2):
    print(f"\n=== {db2} ===")
    conn2 = sqlite3.connect(db2)
    tables2 = [r[0] for r in conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables2)
    if 'account_inventory' in tables2:
        cols = [r[1] for r in conn2.execute("PRAGMA table_info(account_inventory)").fetchall()]
        print("account_inventory columns:", cols)
        cnt = conn2.execute("SELECT COUNT(*) FROM account_inventory").fetchone()[0]
        avail = conn2.execute("SELECT COUNT(*) FROM account_inventory WHERE status='available'").fetchone()[0]
        print(f"account_inventory count: {cnt}, available: {avail}")
    conn2.close()
else:
    print(f"\n{db2} does not exist")
