#!/usr/bin/env python3
"""Analyze accounts.db structure"""
import sqlite3
import json
from pathlib import Path

# Analyze accounts.db
print("=" * 70)
print("ANALYZING accounts.db")
print("=" * 70)

accounts_db = Path("..") / "10.1.10.36_5555" / "accounts.db"
conn = sqlite3.connect(accounts_db)
cursor = conn.cursor()

# Get schema
print("\nColumns in accounts table:")
cursor.execute('PRAGMA table_info(accounts)')
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

# Get sample data
print("\nSample data (first 3 rows):")
cursor.execute('SELECT * FROM accounts LIMIT 3')
rows = cursor.fetchall()
for row in rows:
    print(f"  {row}")

conn.close()

print("\n" + "=" * 70)
print("ANALYZING settings.db")
print("=" * 70)

# Analyze settings.db
settings_db = Path("..") / "10.1.10.36_5555" / "anna.blnaa" / "settings.db"
conn = sqlite3.connect(settings_db)
cursor = conn.cursor()

cursor.execute('SELECT settings FROM accountsettings WHERE id=1')
row = cursor.fetchone()
if row and row[0]:
    settings = json.loads(row[0])

    # Look for username/account name
    print("\nSearching for username/account identifiers...")
    for key in sorted(settings.keys()):
        value = settings[key]
        if any(keyword in key.lower() for keyword in ['account', 'username', 'user_name', 'name']):
            print(f"  {key}: {value}")

conn.close()

print("\n" + "=" * 70)
print("FOLDER STRUCTURE")
print("=" * 70)

device_dir = Path("..") / "10.1.10.36_5555"
print(f"\nDevice folder: {device_dir}")
print(f"Account folders (first 5):")
account_folders = [f for f in device_dir.iterdir() if f.is_dir() and f.name not in ['.stm', 'Camera', 'crash_log', 'jobs']]
for folder in list(account_folders)[:5]:
    print(f"  - {folder.name}")

print(f"\n✓ Folder name = Username")
print(f"✓ When username changes: anna.blnaa → anna.newname")
print(f"✓ We need to RENAME the folder!")
