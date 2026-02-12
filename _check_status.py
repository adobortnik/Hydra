import sqlite3

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Account status distribution
print("=== Account Status Distribution ===")
for r in conn.execute("SELECT status, COUNT(*) as cnt FROM accounts GROUP BY status ORDER BY cnt DESC").fetchall():
    print(f"  {r['status']}: {r['cnt']}")

# Inventory status distribution
print("\n=== Inventory Status Distribution ===")
for r in conn.execute("SELECT status, COUNT(*) as cnt FROM account_inventory GROUP BY status ORDER BY cnt DESC").fetchall():
    print(f"  {r['status']}: {r['cnt']}")

# Unhealthy accounts sample
print("\n=== Sample Unhealthy Accounts ===")
BAD = ('banned', 'suspended', 'challenge', 'login_failed', 'verification_required', 'logged_out', 'action_blocked', '2fa_required')
placeholders = ','.join('?' * len(BAD))
for r in conn.execute(f"SELECT id, username, device_serial, status, updated_at FROM accounts WHERE status IN ({placeholders}) LIMIT 10", BAD).fetchall():
    print(f"  #{r['id']} @{r['username']} on {r['device_serial']} - {r['status']} (updated: {r['updated_at']})")

conn.close()
