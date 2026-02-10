import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
c = conn.cursor()

# Check if follow_lists tables exist
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'follow%'")
tables = [r[0] for r in c.fetchall()]
print(f"Follow tables: {tables}")

if 'follow_lists' in tables:
    c.execute("PRAGMA table_info(follow_lists)")
    print("\nfollow_lists schema:")
    for r in c.fetchall(): print(f"  {r[1]} ({r[2]})")
    
if 'follow_list_items' in tables:
    c.execute("PRAGMA table_info(follow_list_items)")
    print("\nfollow_list_items schema:")
    for r in c.fetchall(): print(f"  {r[1]} ({r[2]})")

# Check if blueprint registered in simple_app
import os
with open('dashboard/simple_app.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    if 'follow_list' in content:
        lines = [l.strip() for l in content.split('\n') if 'follow_list' in l.lower()]
        print(f"\nsimple_app.py follow_list refs:")
        for l in lines: print(f"  {l}")
    else:
        print("\n⚠️ follow_list NOT registered in simple_app.py")

conn.close()
