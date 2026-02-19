import sqlite3
db = sqlite3.connect('db/phone_farm.db')

# Re-enable all accounts on ROBIN 1 with original 2h rotation windows
# 12 accounts, 24 hours / 12 = 2h each
schedule = [
    ('rieff_real',              '0',  '2'),
    ('robin.rieff_prime',       '2',  '4'),
    ('private.steel',           '4',  '6'),
    ('sopphierray',             '6',  '8'),
    ('robin.private_lion',      '8',  '10'),
    ('robin_rieff_prime',       '10', '12'),
    ('robin_rieff_real',        '12', '14'),
    ('robin_rieff_alpha',       '14', '16'),
    ('robin.rieff_alpha',       '16', '18'),
    ('robin.rieff_realbeast',   '18', '20'),
    ('robin_rieff_private',     '20', '22'),
    ('robin_rieff_vault',       '22', '24'),
]

for username, start, end in schedule:
    db.execute(
        "UPDATE accounts SET status='active', start_time=?, end_time=? WHERE username=? AND device_serial='10.1.10.238_5555'",
        (start, end, username))

db.commit()

rows = db.execute("SELECT username, status, start_time, end_time FROM accounts WHERE device_serial='10.1.10.238_5555' ORDER BY CAST(start_time AS INTEGER)").fetchall()
for r in rows:
    print(f"{r[0]:<30} {r[1]:<10} {r[2]}h-{r[3]}h")
