import sqlite3, os
conn = sqlite3.connect(os.path.join('media_library', 'media_library.db'))
conn.execute("DELETE FROM folders WHERE name='test-delete-me'")
conn.commit()
conn.close()
print('cleaned')
