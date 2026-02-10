import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
# Check account_tags
try:
    rows = conn.execute("SELECT count(*) FROM account_tags").fetchone()
    print("account_tags exists, rows:", rows[0])
except Exception as e:
    print("account_tags:", e)
# Check if follow_lists exists already
try:
    rows = conn.execute("SELECT count(*) FROM follow_lists").fetchone()
    print("follow_lists exists, rows:", rows[0])
except Exception as e:
    print("follow_lists:", e)
conn.close()
