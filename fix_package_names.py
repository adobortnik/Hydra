"""
Fix instagram_package to full format: com.instagram.androiX/com.instagram.mainactivity.MainActivity

Run from phone-farm folder:
    python fix_package_names.py

Or with venv:
    venv\Scripts\python.exe fix_package_names.py
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'phone_farm.db')
ACTIVITY = 'com.instagram.mainactivity.MainActivity'

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Fix instagram_package column in accounts table
    accounts = conn.execute(
        "SELECT id, username, device_serial, instagram_package FROM accounts "
        "WHERE instagram_package IS NOT NULL AND instagram_package != '' "
        "AND instagram_package NOT LIKE '%/%'"
    ).fetchall()

    print(f"Found {len(accounts)} accounts with short package name\n")

    updated = 0
    for acc in accounts:
        old_pkg = acc['instagram_package']
        new_pkg = f"{old_pkg}/{ACTIVITY}"
        conn.execute(
            "UPDATE accounts SET instagram_package=? WHERE id=?",
            (new_pkg, acc['id'])
        )
        print(f"  [{acc['id']}] {acc['username']} @ {acc['device_serial']}: {old_pkg} -> {new_pkg}")
        updated += 1

    # 2. Fix app_cloner in account_settings
    settings_rows = conn.execute(
        "SELECT account_id, settings_json FROM account_settings WHERE settings_json IS NOT NULL"
    ).fetchall()

    settings_fixed = 0
    for row in settings_rows:
        try:
            settings = json.loads(row['settings_json'])
            app_cloner = settings.get('app_cloner', '')
            if app_cloner and '/' not in str(app_cloner) and app_cloner.startswith('com.instagram'):
                settings['app_cloner'] = f"{app_cloner}/{ACTIVITY}"
                conn.execute(
                    "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                    (json.dumps(settings), row['account_id'])
                )
                settings_fixed += 1
        except (json.JSONDecodeError, TypeError):
            pass

    conn.commit()
    conn.close()

    print(f"\nDone! Updated {updated} accounts, {settings_fixed} settings entries.")

if __name__ == '__main__':
    main()
