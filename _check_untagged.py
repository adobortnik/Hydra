import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Untagged accounts
rows = conn.execute("SELECT username, device_serial, status FROM accounts WHERE tag IS NULL OR tag = '' ORDER BY device_serial").fetchall()
print(f"=== {len(rows)} UNTAGGED ACCOUNTS ===\n")

by_device = {}
for r in rows:
    d = r['device_serial']
    if d not in by_device:
        by_device[d] = []
    by_device[d].append(r['username'])

for device, usernames in sorted(by_device.items()):
    print(f"{device} ({len(usernames)} accounts):")
    for u in usernames:
        print(f"  {u}")
    print()

# Also show tag summary
print("=== TAG SUMMARY ===")
for row in conn.execute("SELECT tag, COUNT(*) as cnt FROM accounts WHERE tag IS NOT NULL AND tag != '' GROUP BY tag ORDER BY cnt DESC"):
    print(f"  {row['tag']}: {row['cnt']}")

total_tagged = conn.execute("SELECT COUNT(*) FROM accounts WHERE tag IS NOT NULL AND tag != ''").fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
print(f"\nTotal: {total_tagged}/{total} tagged")
conn.close()
