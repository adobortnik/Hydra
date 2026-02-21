import sqlite3

conn = sqlite3.connect('db/phone_farm.db')

# Check accounts table
print("=== accounts.followers ===")
rows = conn.execute("SELECT username, followers FROM accounts WHERE tag='jagger' ORDER BY username").fetchall()
for r in rows:
    print(f"  {r[0]:25s} followers={r[1]}")

# Check follower_snapshots
print("\n=== follower_snapshots (last 10) ===")
rows = conn.execute("""
    SELECT username, followers, following, posts_count, captured_at 
    FROM follower_snapshots 
    ORDER BY captured_at DESC LIMIT 10
""").fetchall()
for r in rows:
    print(f"  {r[0]:25s} F={r[1]} FG={r[2]} P={r[3]} @ {r[4]}")

conn.close()
