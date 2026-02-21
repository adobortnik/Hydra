"""
Compare current DB schema with what db/models.py defines.
Find any columns/tables that might be missing on older DBs.
"""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

db = sqlite3.connect('db/phone_farm.db')

# Get all tables and their columns
tables = {}
for t in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
    name = t[0]
    cols = [c[1] for c in db.execute(f"PRAGMA table_info({name})").fetchall()]
    tables[name] = cols

print(f"=== {len(tables)} tables in phone_farm.db ===\n")
for name, cols in sorted(tables.items()):
    print(f"{name}: {', '.join(cols)}")

# Check which tables have device_serial (for sync reference)
print(f"\n=== Tables with device_serial ===")
for name, cols in sorted(tables.items()):
    if 'device_serial' in cols:
        print(f"  {name}")

# Check for columns that were likely added later (ALTER TABLE additions)
# These are usually at the END of the column list (SQLite appends them)
print(f"\n=== Likely late additions (last columns per table) ===")
for name, cols in sorted(tables.items()):
    if len(cols) > 3:
        print(f"  {name}: ...{', '.join(cols[-3:])}")

db.close()
