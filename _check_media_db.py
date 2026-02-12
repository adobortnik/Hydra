import sqlite3, os
db = os.path.join('media_library', 'media_library.db')
print('Exists:', os.path.exists(db))
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('Tables:', tables)
if 'folders' in tables:
    rows = conn.execute("SELECT * FROM folders LIMIT 5").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM folders LIMIT 1").description] if rows else []
    print('Folder columns:', cols)
    for r in rows:
        print(dict(zip(cols, r)))
else:
    print('NO folders table!')
    # Check schema
    for t in tables:
        cols = [d[0] for d in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f'  {t}: {cols}')
conn.close()
