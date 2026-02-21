import sqlite3

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Check account_stats (what device manager uses for followers column)
print("=== account_stats (today) ===")
rows = conn.execute("""
    SELECT a.username, s.followers, s.following, s.date 
    FROM account_stats s
    JOIN accounts a ON a.id = s.account_id
    WHERE s.date = '2026-02-21' AND a.tag = 'jagger'
    ORDER BY a.username
""").fetchall()
for r in rows:
    print(f"  {r['username']:25s} F={r['followers']} FG={r['following']}")
print(f"Total: {len(rows)}\n")

# Check follower_snapshots (what check_profile writes)
print("=== follower_snapshots (today, latest per user) ===")
rows = conn.execute("""
    SELECT username, followers, following, posts_count, captured_at
    FROM follower_snapshots 
    WHERE captured_at >= '2026-02-21'
    ORDER BY username, captured_at DESC
""").fetchall()
seen = set()
for r in rows:
    if r['username'] not in seen:
        print(f"  {r['username']:25s} F={r['followers']} FG={r['following']} P={r['posts_count']} @ {r['captured_at']}")
        seen.add(r['username'])
print(f"Total unique: {len(seen)}\n")

# Who populates account_stats?
print("=== account_stats schema check ===")
print("Any rows at all?", conn.execute("SELECT COUNT(*) FROM account_stats").fetchone()[0])
print("Dates:", [r[0] for r in conn.execute("SELECT DISTINCT date FROM account_stats ORDER BY date DESC LIMIT 5").fetchall()])

conn.close()
