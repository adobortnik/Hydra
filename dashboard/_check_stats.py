import sqlite3
DB = r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db'
conn = sqlite3.connect(DB)
c = conn.cursor()

stats_tables = ['action_history', 'bot_status', 'account_sessions', 'bot_logs', 'account_stats', 'task_history']
for t in stats_tables:
    try:
        c.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in c.fetchall()]
        c.execute(f"SELECT COUNT(*) FROM {t}")
        count = c.fetchone()[0]
        print(f"\n=== {t} ({count} rows) ===")
        print(f"  Cols: {cols}")
        if count > 0:
            c.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 2")
            for row in c.fetchall():
                print(f"  Sample: {dict(zip(cols, row))}")
    except Exception as e:
        print(f"\n=== {t}: {e} ===")

conn.close()
