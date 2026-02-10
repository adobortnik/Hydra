"""Find the old/correct package mappings from all available data sources."""
import sqlite3
import json
import os
import glob

BASE = r'C:\Users\TheLiveHouse\clawd\phone-farm\dashboard'

# 1) Check account_inventory.db
print("=== account_inventory.db ===")
try:
    conn = sqlite3.connect(os.path.join(BASE, 'data', 'account_inventory', 'account_inventory.db'))
    conn.row_factory = sqlite3.Row
    tables = [r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")
        rows = conn.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
        for r in rows:
            print(f"    {dict(r)}")
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 2) Check login_automation.db
print("\n=== login_automation.db ===")
try:
    conn = sqlite3.connect(os.path.join(BASE, 'uiAutomator', 'login_automation.db'))
    conn.row_factory = sqlite3.Row
    tables = [r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")
        if 'app' in ' '.join(cols).lower() or 'package' in ' '.join(cols).lower():
            rows = conn.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
            for r in rows:
                print(f"    {dict(r)}")
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 3) Check profile_automation.db
print("\n=== profile_automation.db ===")
try:
    conn = sqlite3.connect(os.path.join(BASE, 'uiAutomator', 'profile_automation.db'))
    conn.row_factory = sqlite3.Row
    tables = [r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")
        if 'app' in ' '.join(cols).lower() or 'package' in ' '.join(cols).lower():
            rows = conn.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
            for r in rows:
                print(f"    {dict(r)}")
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 4) Check Onimator YAML configs
print("\n=== Onimator YAML/JSON configs ===")
for pattern in [os.path.join(BASE, 'uiAutomator', 'bot', 'accounts', '**', '*.yml'),
                os.path.join(BASE, 'uiAutomator', 'bot', 'accounts', '**', '*.json'),
                os.path.join(BASE, 'uiAutomator', 'bot', 'accounts', '*')]:
    files = glob.glob(pattern, recursive=True)
    if files:
        print(f"  Found: {files[:10]}")

# 5) Check GramAddict config directories
print("\n=== GramAddict config dirs ===")
config_dir = os.path.join(BASE, 'uiAutomator', 'bot', 'accounts')
if os.path.exists(config_dir):
    for item in os.listdir(config_dir)[:20]:
        full = os.path.join(config_dir, item)
        print(f"  {item} {'(dir)' if os.path.isdir(full) else ''}")
        if os.path.isdir(full):
            for f in os.listdir(full)[:5]:
                print(f"    {f}")
else:
    print("  accounts dir not found")

# 6) Check onimator_reader for how it reads data
print("\n=== Checking onimator_reader.py ===")
reader_path = os.path.join(BASE, 'uiAutomator', 'onimator_reader.py')
if os.path.exists(reader_path):
    with open(reader_path) as f:
        content = f.read()
    # Find references to package/app_id
    for i, line in enumerate(content.split('\n'), 1):
        if any(kw in line.lower() for kw in ['package', 'app_id', 'app-id', 'instagram']):
            print(f"  L{i}: {line.strip()}")
