import sqlite3

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# When did follows happen today?
rows = conn.execute("""
    SELECT device_serial, username, target_username, timestamp
    FROM action_history
    WHERE action_type = 'follow' AND success = 1
      AND timestamp >= '2026-02-21'
    ORDER BY timestamp DESC
    LIMIT 30
""").fetchall()

print("=== Last 30 successful follows today ===")
for r in rows:
    print(f"  {r['timestamp']}  {r['username']:20s} -> @{r['target_username']}")

# Count before vs after 13:17 (restart time)
before = conn.execute("""
    SELECT COUNT(*) FROM action_history
    WHERE action_type = 'follow' AND success = 1
      AND timestamp >= '2026-02-21' AND timestamp < '2026-02-21 13:17'
""").fetchone()[0]

after = conn.execute("""
    SELECT COUNT(*) FROM action_history
    WHERE action_type = 'follow' AND success = 1
      AND timestamp >= '2026-02-21 13:17'
""").fetchone()[0]

print(f"\nBefore restart (13:17): {before} follows")
print(f"After restart (13:17):  {after} follows")

conn.close()
