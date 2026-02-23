import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
conn.row_factory = sqlite3.Row

for serial in ['184', '190', '192', '199']:
    rows = conn.execute(
        "SELECT action_type, COUNT(*) as cnt, SUM(CASE WHEN success THEN 1 ELSE 0 END) as ok "
        "FROM action_history WHERE device_serial LIKE ? AND timestamp > '2026-02-22 02:00' "
        "GROUP BY action_type ORDER BY cnt DESC", (f'%{serial}%',)
    ).fetchall()
    total = sum(r['cnt'] for r in rows) if rows else 0
    print(f'Device {serial}: {total} actions')
    for r in rows:
        print(f'  {r["action_type"]:15s} {r["cnt"]:4d} ({r["ok"]} ok)')

print('\n--- Comment/DM/Report on 184 ---')
rows2 = conn.execute(
    "SELECT action_type, username, target_username, success, error_message, timestamp "
    "FROM action_history WHERE device_serial LIKE '%184%' "
    "AND action_type IN ('comment','dm','report') AND timestamp > '2026-02-22 02:00' "
    "ORDER BY timestamp DESC LIMIT 20"
).fetchall()
for r in rows2:
    s = 'OK' if r['success'] else 'FAIL'
    e = r['error_message'] or ''
    print(f'  [{s}] {r["action_type"]:8s} @{r["username"]} -> @{r["target_username"] or "?"} | {r["timestamp"]} {e}')
if not rows2:
    print('  None found')

# Check bot log file
import os, glob
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
for serial in ['184']:
    logs = glob.glob(os.path.join(log_dir, f'*{serial}*'))
    if logs:
        latest = max(logs, key=os.path.getmtime)
        mtime = os.path.getmtime(latest)
        from datetime import datetime
        print(f'\nLog file: {os.path.basename(latest)} (modified {datetime.fromtimestamp(mtime)})')
        with open(latest, 'r', errors='ignore') as f:
            lines = f.readlines()
        # Show last 30 lines with comment/dm/report mentions
        relevant = [l for l in lines if any(k in l.lower() for k in ['comment', ' dm ', 'direct', 'report', 'error', 'fail', 'success'])]
        if relevant:
            print('Relevant log entries (last 15):')
            for l in relevant[-15:]:
                print(f'  {l.rstrip()}')
        else:
            print('Last 15 lines:')
            for l in lines[-15:]:
                print(f'  {l.rstrip()}')
    else:
        print(f'\nNo log file for device {serial}')

conn.close()
