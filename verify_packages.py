import sqlite3
conn = sqlite3.connect(r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db')
conn.row_factory = sqlite3.Row

# Count by package
pkgs = conn.execute("SELECT instagram_package, COUNT(*) as cnt FROM accounts GROUP BY instagram_package ORDER BY instagram_package").fetchall()
print("Package distribution:")
for p in pkgs:
    print(f"  {p['instagram_package']:30s} = {p['cnt']} accounts")

# Verify none left as base package
base = conn.execute("SELECT COUNT(*) as c FROM accounts WHERE instagram_package = 'com.instagram.android'").fetchone()
print(f"\nAccounts still on base package: {base['c']}")
conn.close()
