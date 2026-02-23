"""Sync completed profile automation username changes into phone_farm.db"""
import sqlite3
from pathlib import Path

pa_db = Path('dashboard/uiAutomator/profile_automation.db')
farm_db = Path('db/phone_farm.db')

# Get completed tasks with username changes
pa_conn = sqlite3.connect(str(pa_db))
pa_conn.row_factory = sqlite3.Row
tasks = pa_conn.execute("""
    SELECT id, device_serial, username as old_username, new_username, instagram_package, status
    FROM profile_updates
    WHERE new_username IS NOT NULL AND status = 'completed'
""").fetchall()
pa_conn.close()

print(f"Found {len(tasks)} completed username change tasks\n")

if not tasks:
    print("Nothing to sync!")
    exit()

# Show what we'd update
farm_conn = sqlite3.connect(str(farm_db), timeout=30)
farm_conn.execute("PRAGMA journal_mode=WAL")
farm_conn.execute("PRAGMA busy_timeout=30000")
farm_conn.row_factory = sqlite3.Row

updated = 0
for t in tasks:
    old_u = t['old_username']
    new_u = t['new_username']
    dev = t['device_serial']
    pkg = t['instagram_package']
    
    # Try both colon and underscore serial formats
    dev_colon = dev.replace('_', ':')
    dev_under = dev.replace(':', '_')
    
    # Check if old username still exists in phone_farm.db
    row = farm_conn.execute(
        "SELECT id, username, device_serial FROM accounts WHERE username = ? AND (device_serial = ? OR device_serial = ?)",
        (old_u, dev_colon, dev_under)
    ).fetchone()
    
    if row:
        farm_conn.execute("UPDATE accounts SET username = ? WHERE id = ?", (new_u, row['id']))
        print(f"  ✅ {old_u:25s} → {new_u:25s} (device {dev_colon})")
        updated += 1
    else:
        # Maybe already updated or username doesn't match
        already = farm_conn.execute(
            "SELECT id FROM accounts WHERE username = ? AND (device_serial = ? OR device_serial = ?)",
            (new_u, dev_colon, dev_under)
        ).fetchone()
        if already:
            print(f"  ⏭️  {old_u:25s} → {new_u:25s} (already synced)")
        else:
            print(f"  ❓ {old_u:25s} → {new_u:25s} (old username not found in DB)")

farm_conn.commit()
farm_conn.close()
print(f"\nUpdated {updated} accounts in phone_farm.db")
