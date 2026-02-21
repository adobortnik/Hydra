import sqlite3

conn = sqlite3.connect('db/phone_farm.db')

# Temporarily extend windows for testing
for username in ['modeljagger', 'mrjaggerclub']:
    row = conn.execute("SELECT id, start_time, end_time FROM accounts WHERE username=?", (username,)).fetchone()
    old_start, old_end = row[1], row[2]
    conn.execute("UPDATE accounts SET start_time='2', end_time='23' WHERE username=?", (username,))
    print(f"  {username}: window {old_start}-{old_end} -> 2-23")

conn.commit()
conn.close()
print("Done! Will revert after testing.")
