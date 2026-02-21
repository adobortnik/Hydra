import sqlite3, json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4"

# 1. Check account_inventory (has 'tags' column)
inv_db = os.path.join(BASE, "the-livehouse-dashboard", "data", "account_inventory", "account_inventory.db")
print("=== ACCOUNT INVENTORY WITH TAGS ===")
conn = sqlite3.connect(inv_db)
rows = conn.execute("SELECT username, tags, device_assigned, status FROM account_inventory WHERE tags IS NOT NULL AND tags != ''").fetchall()
print(f"Found {len(rows)} accounts with tags")
tag_counts = {}
for r in rows:
    username, tags, device, status = r
    print(f"  {username}: tag='{tags}' device={device} status={status}")
    if tags:
        tag_counts[tags] = tag_counts.get(tags, 0) + 1
print(f"\nTag distribution: {tag_counts}")
conn.close()

# 2. Check profile_automation.db account_tags (was empty before)
pa_db = os.path.join(BASE, "the-livehouse-dashboard", "uiAutomator", "profile_automation.db")
print("\n=== PROFILE AUTOMATION account_tags ===")
conn = sqlite3.connect(pa_db)
rows = conn.execute("SELECT * FROM account_tags").fetchall()
print(f"Found {len(rows)} entries")
for r in rows[:20]:
    print(f"  {r}")
conn.close()

# 3. Check per-device settings.db for tags field
print("\n=== SETTINGS.DB TAG SCAN (per account) ===")
tag_map = {}  # device -> {username -> tag}
for device_dir in os.listdir(BASE):
    device_path = os.path.join(BASE, device_dir)
    if not os.path.isdir(device_path) or device_dir.startswith('.') or device_dir in ('the-livehouse-dashboard', 'uiAutomator', 'scrapers', 'template', 'venv'):
        continue
    
    for account_dir in os.listdir(device_path):
        settings_db = os.path.join(device_path, account_dir, "settings.db")
        if not os.path.exists(settings_db):
            continue
        try:
            conn = sqlite3.connect(settings_db)
            row = conn.execute("SELECT settings FROM accountsettings WHERE id = 1").fetchone()
            conn.close()
            if row and row[0]:
                settings = json.loads(row[0])
                tags = settings.get('tags', '')
                enable_tags = settings.get('enable_tags', False)
                if tags:
                    if device_dir not in tag_map:
                        tag_map[device_dir] = {}
                    tag_map[device_dir][account_dir] = tags
        except Exception as e:
            pass

# Print results grouped by device
print(f"\nFound tags in {len(tag_map)} devices:")
device_tag_summary = {}  # device -> tag (most common)
for device, accounts in sorted(tag_map.items()):
    # Find most common tag for this device
    tags_on_device = {}
    for username, tag in accounts.items():
        tags_on_device[tag] = tags_on_device.get(tag, 0) + 1
    
    most_common = max(tags_on_device, key=tags_on_device.get)
    device_tag_summary[device] = most_common
    
    print(f"\n  {device} -> TAG: '{most_common}' ({len(accounts)} accounts)")
    for username, tag in sorted(accounts.items()):
        print(f"    {username}: '{tag}'")

print(f"\n\n=== DEVICE -> TAG MAPPING (for Hydra import) ===")
for device, tag in sorted(device_tag_summary.items()):
    print(f"  {device} = {tag}")
