"""
Apply tags from old Onimator settings.db to Hydra accounts.
Matches by username (account can be on different device now).
"""
import sqlite3, json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ONIMATOR_BASE = r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4"
HYDRA_DB = r"C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db"

# ── Step 1: Extract username->tag from old Onimator ──
print("=" * 70)
print("STEP 1: Extract tags from Onimator")
print("=" * 70)

old_tags = {}  # username -> tag
for device_dir in os.listdir(ONIMATOR_BASE):
    device_path = os.path.join(ONIMATOR_BASE, device_dir)
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
                if tags:
                    old_tags[account_dir.lower()] = tags
        except:
            pass

print(f"Found {len(old_tags)} accounts with tags in Onimator")
tag_counts = {}
for t in old_tags.values():
    tag_counts[t] = tag_counts.get(t, 0) + 1
print(f"Tag distribution: {json.dumps(tag_counts, indent=2)}")

# ── Step 2: Check current Hydra state ──
print(f"\n{'=' * 70}")
print("STEP 2: Current Hydra accounts")
print("=" * 70)

conn = sqlite3.connect(HYDRA_DB)
conn.row_factory = sqlite3.Row

# Get all accounts
accounts = conn.execute("SELECT id, username, device_serial, tag FROM accounts").fetchall()
print(f"Total Hydra accounts: {len(accounts)}")

already_tagged = sum(1 for a in accounts if a['tag'])
no_tag = sum(1 for a in accounts if not a['tag'])
print(f"Already tagged: {already_tagged}")
print(f"Missing tag: {no_tag}")

# ── Step 3: Match and apply ──
print(f"\n{'=' * 70}")
print("STEP 3: Matching & Applying Tags")
print("=" * 70)

# Also ensure tags exist in tags table
existing_tags = {r[0]: r[1] for r in conn.execute("SELECT name, id FROM tags").fetchall()}
print(f"Existing Hydra tags: {list(existing_tags.keys())}")

matched = 0
unmatched = 0
already_correct = 0
updated = 0
new_tags_created = []

DRY_RUN = False  # APPLYING FOR REAL

for acc in accounts:
    username = acc['username'].lower()
    current_tag = acc['tag'] or ''
    
    if username in old_tags:
        old_tag = old_tags[username]
        matched += 1
        
        if current_tag == old_tag:
            already_correct += 1
        else:
            updated += 1
            if updated <= 30:  # Print first 30
                print(f"  {acc['username']} ({acc['device_serial']}): '{current_tag}' -> '{old_tag}'")
            
            if not DRY_RUN:
                # Update accounts.tag
                conn.execute("UPDATE accounts SET tag = ? WHERE id = ?", (old_tag, acc['id']))
                
                # Ensure tag exists in tags table
                if old_tag not in existing_tags:
                    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (old_tag,))
                    existing_tags[old_tag] = None
                    new_tags_created.append(old_tag)
                
                # Add to account_tags junction table
                tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (old_tag,)).fetchone()
                if tag_id:
                    conn.execute("INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)", 
                               (acc['id'], tag_id[0]))
    else:
        unmatched += 1

if updated > 30:
    print(f"  ... and {updated - 30} more")

print(f"\n--- SUMMARY ---")
print(f"Matched by username: {matched}/{len(accounts)}")
print(f"Already correct tag: {already_correct}")
print(f"Would update: {updated}")
print(f"No match in Onimator: {unmatched}")
print(f"New tags to create: {new_tags_created}")

if DRY_RUN:
    print(f"\n>>> DRY RUN - no changes made. Set DRY_RUN = False to apply.")
else:
    conn.commit()
    print(f"\n>>> APPLIED! {updated} accounts updated.")

conn.close()
