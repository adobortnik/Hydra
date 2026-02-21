import sqlite3

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Check account_stats (what device manager uses)
print("=== account_stats (today) ===")
rows = conn.execute("""
    SELECT username, followers, following, date 
    FROM account_stats 
    WHERE date = '2026-02-21' 
    ORDER BY username
""").fetchall()
for r in rows:
    print(f"  {r['username']:25s} F={r['followers']} FG={r['following']}")
print(f"Total: {len(rows)}\n")

# Check follower_snapshots (what check_profile writes)
print("=== follower_snapshots (today) ===")
rows = conn.execute("""
    SELECT username, followers, following, posts_count, captured_at
    FROM follower_snapshots 
    WHERE captured_at >= '2026-02-21'
    ORDER BY username, captured_at DESC
""").fetchall()
for r in rows:
    print(f"  {r['username']:25s} F={r['followers']} FG={r['following']} P={r['posts_count']} @ {r['captured_at']}")
print(f"Total: {len(rows)}\n")

# Check accounts.followers
print("=== accounts.followers (non-zero) ===")
rows = conn.execute("""
    SELECT username, followers 
    FROM accounts 
    WHERE tag = 'jagger' AND followers > 0
    ORDER BY username
""").fetchall()
for r in rows:
    print(f"  {r['username']:25s} F={r['followers']}")
print(f"Total: {len(rows)}")

conn.close()
