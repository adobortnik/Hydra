import sqlite3

db_path = r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4\the-livehouse-dashboard\uiAutomator\profile_automation.db"
db = sqlite3.connect(db_path)

# Full schema
print("=== FULL SCHEMA ===")
for row in db.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
    print(row[0])
    print()

# Tags
print("=== TAGS ===")
for row in db.execute("SELECT * FROM tags"):
    print(row)

# Account tags
print("\n=== ACCOUNT_TAGS (sample) ===")
for row in db.execute("SELECT * FROM account_tags LIMIT 20"):
    print(row)

# Tag campaigns
print("\n=== TAG_CAMPAIGNS ===")
for row in db.execute("SELECT * FROM tag_campaigns"):
    print(row)

# Also check the account_inventory with tags
db2_path = r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4\the-livehouse-dashboard\data\account_inventory\account_inventory.db"
db2 = sqlite3.connect(db2_path)
print("\n=== ACCOUNT INVENTORY WITH TAGS (sample) ===")
for row in db2.execute("SELECT username, tags FROM account_inventory WHERE tags IS NOT NULL AND tags != '' LIMIT 20"):
    print(row)

db.close()
db2.close()
