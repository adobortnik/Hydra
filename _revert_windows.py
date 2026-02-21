import sqlite3
conn = sqlite3.connect('db/phone_farm.db')
conn.execute("UPDATE accounts SET start_time='14', end_time='16' WHERE username='modeljagger'")
conn.execute("UPDATE accounts SET start_time='12', end_time='14' WHERE username='mrjaggerclub'")
conn.commit()
conn.close()
print("Reverted: modeljagger=14-16, mrjaggerclub=12-14")
