"""
Fix instagram_package: ensure SHORT format in accounts table (com.instagram.androiX)
and FULL format in app_cloner setting (com.instagram.androiX/com.instagram.mainactivity.MainActivity)

The instagram_package column is used as resource ID prefix in ig_controller,
so it MUST be the short package name only.

The app_cloner in settings_json has the full package/activity for launching.

Run from phone-farm folder:
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

    # 1. Fix instagram_package column — must be SHORT (no activity)
    accounts = conn.execute(
        "SELECT id, username, device_serial, instagram_package FROM accounts "
        "WHERE instagram_package IS NOT NULL AND instagram_package LIKE '%/%'"
    ).fetchall()

    print(f"Found {len(accounts)} accounts with full package name (need to shorten)\n")

    shortened = 0
    for acc in accounts:
        old_pkg = acc['instagram_package']
        new_pkg = old_pkg.split('/')[0]
        conn.execute(
            "UPDATE accounts SET instagram_package=? WHERE id=?",
            (new_pkg, acc['id'])
        )
        print(f"  [{acc['id']}] {acc['username']}: {old_pkg} -> {new_pkg}")
        shortened += 1

    # 2. Fix app_cloner in account_settings — must be FULL (package/activity)
    settings_rows = conn.execute(
        "SELECT account_id, settings_json FROM account_settings WHERE settings_json IS NOT NULL"
    ).fetchall()

    settings_fixed = 0
    for row in settings_rows:
        try:
            settings = json.loads(row['settings_json'])
            app_cloner = settings.get('app_cloner', '')
            if app_cloner and app_cloner.startswith('com.instagram') and '/' not in str(app_cloner):
                settings['app_cloner'] = f"{app_cloner}/{ACTIVITY}"
                conn.execute(
                    "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                    (json.dumps(settings), row['account_id'])
                )
                settings_fixed += 1
                print(f"  [settings:{row['account_id']}] app_cloner: {app_cloner} -> {settings['app_cloner']}")
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. Also ensure accounts WITHOUT app_cloner get it set
    all_accounts = conn.execute(
        "SELECT a.id, a.instagram_package FROM accounts a "
        "WHERE a.instagram_package IS NOT NULL AND a.instagram_package != ''"
    ).fetchall()

    added_cloner = 0
    for acc in all_accounts:
        pkg = acc['instagram_package'].split('/')[0]  # ensure short
        full_app_id = f"{pkg}/{ACTIVITY}"

        settings_row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id=?",
            (acc['id'],)
        ).fetchone()

        if settings_row:
            settings = json.loads(settings_row['settings_json'] or '{}')
            if not settings.get('app_cloner') or '/' not in str(settings.get('app_cloner', '')):
                settings['app_cloner'] = full_app_id
                conn.execute(
                    "UPDATE account_settings SET settings_json=? WHERE account_id=?",
                    (json.dumps(settings), acc['id'])
                )
                added_cloner += 1
        else:
            conn.execute(
                "INSERT INTO account_settings (account_id, settings_json) VALUES (?, ?)",
                (acc['id'], json.dumps({'app_cloner': full_app_id}))
            )
            added_cloner += 1

    conn.commit()
    conn.close()

    print(f"\nDone!")
    print(f"  Shortened instagram_package: {shortened}")
    print(f"  Fixed app_cloner in settings: {settings_fixed}")
    print(f"  Added missing app_cloner: {added_cloner}")

if __name__ == '__main__':
    main()
