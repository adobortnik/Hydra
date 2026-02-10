"""
Extract real package mappings from Onimator's device folders AND profile_automation.db.
Then update phone_farm.db with the correct values.
"""
import sqlite3
import json
import os
from pathlib import Path

# Onimator device folders live 2 levels up from uiAutomator
UIAUTOMATOR_DIR = Path(r'C:\Users\TheLiveHouse\clawd\phone-farm\dashboard\uiAutomator')
BASE_DIR = UIAUTOMATOR_DIR.parent.parent  # 2 levels up
FARM_DB = r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db'
PROFILE_DB = r'C:\Users\TheLiveHouse\clawd\phone-farm\dashboard\uiAutomator\profile_automation.db'
LOGIN_DB = r'C:\Users\TheLiveHouse\clawd\phone-farm\dashboard\uiAutomator\login_automation.db'

print(f"Looking for Onimator device folders in: {BASE_DIR}")
print()

# ── Source 1: Onimator device folders ──
onimator_mappings = {}  # (device_serial, username) -> package

device_dirs = []
for folder in BASE_DIR.iterdir():
    if folder.is_dir() and '_' in folder.name:
        parts = folder.name.replace('_', '.').split('.')
        if len(parts) >= 4:  # IP-like pattern
            device_dirs.append(folder)

print(f"Found {len(device_dirs)} potential device folders")
for d in sorted(device_dirs):
    accounts_db = d / "accounts.db"
    if accounts_db.exists():
        try:
            conn = sqlite3.connect(str(accounts_db))
            conn.row_factory = sqlite3.Row
            accs = conn.execute("SELECT * FROM accounts").fetchall()
            conn.close()
            
            for acc in accs:
                username = acc['account']
                # Try to get package from settings.db
                settings_db = d / username / "settings.db"
                pkg = None
                if settings_db.exists():
                    try:
                        sc = sqlite3.connect(str(settings_db))
                        row = sc.execute("SELECT settings FROM accountsettings WHERE id = 1").fetchone()
                        sc.close()
                        if row and row[0]:
                            settings = json.loads(row[0])
                            pkg = settings.get('app_cloner')
                    except:
                        pass
                
                if pkg:
                    onimator_mappings[(d.name, username)] = pkg
        except:
            pass

print(f"Found {len(onimator_mappings)} package mappings from Onimator folders")

# ── Source 2: device_accounts in profile_automation.db ──
profile_mappings = {}  # (device_serial, username) -> package

try:
    conn = sqlite3.connect(PROFILE_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT device_serial, current_username, instagram_package FROM device_accounts").fetchall()
    for r in rows:
        profile_mappings[(r['device_serial'], r['current_username'])] = r['instagram_package']
    conn.close()
    print(f"Found {len(profile_mappings)} mappings from profile_automation.db device_accounts")
except Exception as e:
    print(f"Error reading profile_automation.db: {e}")

# ── Source 3: login_history (most recent successful logins) ──
login_mappings = {}  # (device_serial, username) -> package

try:
    conn = sqlite3.connect(LOGIN_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT device_serial, username, instagram_package 
        FROM login_history 
        WHERE success = 1
        ORDER BY logged_in_at DESC
    """).fetchall()
    for r in rows:
        key = (r['device_serial'], r['username'])
        if key not in login_mappings:  # Keep most recent
            login_mappings[key] = r['instagram_package']
    conn.close()
    print(f"Found {len(login_mappings)} mappings from login_history")
except Exception as e:
    print(f"Error reading login_automation.db: {e}")

# ── Merge: prefer onimator > profile > login ──
all_mappings = {}
for k, v in login_mappings.items():
    all_mappings[k] = v
for k, v in profile_mappings.items():
    all_mappings[k] = v
for k, v in onimator_mappings.items():
    all_mappings[k] = v

print(f"\nTotal unique mappings: {len(all_mappings)}")

# ── Now match against phone_farm.db ──
conn = sqlite3.connect(FARM_DB)
conn.row_factory = sqlite3.Row

accounts = conn.execute("""
    SELECT a.id, a.username, a.instagram_package, a.device_id, d.device_serial
    FROM accounts a
    JOIN devices d ON a.device_id = d.id
""").fetchall()

matched = 0
unmatched = []

print(f"\nMatching {len(accounts)} accounts in phone_farm.db...")
print()

for acc in accounts:
    serial = acc['device_serial']
    username = acc['username']
    
    # Try exact match
    pkg = all_mappings.get((serial, username))
    
    if pkg and pkg != acc['instagram_package']:
        matched += 1
        if matched <= 20:
            print(f"  MATCH: {username:35s} on {serial:20s} -> {pkg}")

if matched > 20:
    print(f"  ... and {matched - 20} more")

print(f"\nMatched: {matched}")
print(f"Unmatched: {len(accounts) - matched}")

# Show what we have from onimator per device serial  
print("\n=== Onimator folder sample ===")
for (serial, user), pkg in sorted(list(onimator_mappings.items()))[:20]:
    print(f"  {serial:20s} {user:35s} {pkg}")

conn.close()
