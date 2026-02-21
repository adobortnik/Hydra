import sqlite3
db = sqlite3.connect('db/phone_farm.db')

# Check account_sources structure
cols = db.execute('PRAGMA table_info(account_sources)').fetchall()
for c in cols: print(c)
print('---')
rows = db.execute('SELECT * FROM account_sources LIMIT 5').fetchall()
for r in rows: print(r)
print('---')

# Check tags
tags = db.execute("SELECT DISTINCT tag FROM accounts WHERE tag IS NOT NULL AND tag != ''").fetchall()
print('Tags:', tags)
print('---')

# Count data
cnt = db.execute('SELECT COUNT(*) FROM action_history').fetchone()
print('Total actions:', cnt[0])
follows = db.execute("SELECT COUNT(*) FROM action_history WHERE action_type='follow' AND success=1").fetchone()
print('Successful follows:', follows[0])
print('---')

# Follower snapshots
snaps = db.execute('SELECT COUNT(*) FROM follower_snapshots').fetchone()
print('Follower snapshots:', snaps[0])

# Check if source_username tracked in action_history
sample = db.execute("SELECT * FROM action_history WHERE action_type='follow' AND success=1 LIMIT 3").fetchall()
for s in sample: print(s)
