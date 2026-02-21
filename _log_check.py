import sqlite3, glob, os
from datetime import datetime

conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

# Today's action counts per device
print("=== Today's Actions (per device) ===")
rows = conn.execute("""
    SELECT device_serial, action_type, COUNT(*) as cnt
    FROM action_history
    WHERE timestamp >= '2026-02-21' AND success = 1
    GROUP BY device_serial, action_type
    ORDER BY device_serial, action_type
""").fetchall()

devices = {}
for r in rows:
    d = r['device_serial']
    if d not in devices:
        devices[d] = {}
    devices[d][r['action_type']] = r['cnt']

for d in sorted(devices):
    acts = devices[d]
    parts = [f"{k}={v}" for k,v in sorted(acts.items())]
    print(f"  {d:25s} {', '.join(parts)}")

# Follow success vs filtered since restart (13:17)
print("\n=== Follow Stats Since Restart (13:17+) ===")
logs_dir = 'logs'
for serial in ['10.1.10.184_5555', '10.1.10.190_5555', '10.1.10.192_5555', '10.1.10.199_5555']:
    logfile = os.path.join(logs_dir, f"{serial}_2026-02-21.log")
    if not os.path.exists(logfile):
        continue
    
    follows = 0
    filtered = 0
    tag_skipped = 0
    filter_reasons = {}
    
    with open(logfile, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line < '2026-02-21 13:17':
                continue
            if 'filtered:' in line:
                filtered += 1
                reason = line.split('filtered:')[1].strip().split('(')[0].strip()
                filter_reasons[reason] = filter_reasons.get(reason, 0) + 1
            elif 'same-tag account already followed' in line:
                tag_skipped += 1
            elif 'Successfully followed' in line or "action_type='follow'" in line:
                follows += 1
    
    print(f"  {serial}: follows={follows}, filtered={filtered}, tag_skipped={tag_skipped}")
    if filter_reasons:
        for reason, cnt in sorted(filter_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {cnt}")

# Latest follower snapshots
print("\n=== Latest Follower Snapshots ===")
rows = conn.execute("""
    SELECT username, followers, following, posts_count, captured_at
    FROM follower_snapshots
    WHERE captured_at >= '2026-02-21 13:00'
    ORDER BY captured_at DESC
""").fetchall()
for r in rows:
    print(f"  {r['username']:25s} F={r['followers']} FG={r['following']} P={r['posts_count']} @ {r['captured_at']}")

conn.close()
