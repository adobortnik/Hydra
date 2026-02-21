import sqlite3

conn = sqlite3.connect('db/phone_farm.db')

# Stats per tag
rows = conn.execute("SELECT tag, COUNT(*) as cnt FROM tag_followed_targets GROUP BY tag").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} targets")

total = conn.execute("SELECT COUNT(*) FROM tag_followed_targets").fetchone()[0]
unique = conn.execute("SELECT COUNT(DISTINCT target_username) FROM tag_followed_targets").fetchone()[0]
print(f"\nTotal rows: {total}")
print(f"Unique targets: {unique}")

# Sample
print("\nSample (last 5):")
rows = conn.execute("SELECT tag, target_username, followed_by, followed_at FROM tag_followed_targets ORDER BY id DESC LIMIT 5").fetchall()
for r in rows:
    print(f"  [{r[0]}] @{r[1]} by {r[2]} @ {r[3]}")

conn.close()
