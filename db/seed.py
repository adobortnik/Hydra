"""
Phone Farm — Data Import / Seed Script
=======================================
Imports existing data from Onimator's scattered DB files into
our consolidated phone_farm.db.

Source structure (Onimator):
  full_igbot_14.2.4/
  ├── devices.db                        → devices table
  ├── {device_serial}/
  │   ├── accounts.db                   → accounts table (+ toggles)
  │   └── {username}/
  │       ├── settings.db               → account_settings table
  │       ├── stats.db                  → account_stats table
  │       ├── sources.txt               → account_sources table
  │       ├── whitelist.txt             → account_sources table
  │       └── *.txt                     → account_text_configs table
  └── the-livehouse-dashboard/
      └── data/
          ├── media_library/media_library.db  → media, tags, folders tables
          ├── scheduled_posts/scheduled_posts.db → scheduled_posts table
          ├── account_inventory/account_inventory.db → account_inventory table
          └── ...

Also imports from dashboard-local DBs:
  - caption_templates.db
  - follower_orders.db
  - uiAutomator/login_automation.db
  - uiAutomator/profile_automation.db
  - uiAutomator/bot_data/*.db

Usage:
    python db/seed.py                       # Auto-detect Onimator path
    python db/seed.py --source C:\\path\\to\\full_igbot_14.2.4
    python db/seed.py --dry-run             # Print what would be imported
"""

import os
import sys
import json
import sqlite3
import argparse
import re
from pathlib import Path
from datetime import datetime

# Add parent so we can import models
sys.path.insert(0, str(Path(__file__).parent.parent))
from db.models import (
    get_connection, init_db, DB_PATH,
    insert_device, insert_account, upsert_account_settings, insert_stat,
    DEFAULT_ACCOUNT_SETTINGS, row_to_dict,
)


# ===================================================================
#  PATH DETECTION
# ===================================================================

def find_onimator_root():
    """Try to find the Onimator root directory automatically."""
    candidates = [
        # Relative to phone-farm project
        Path(__file__).parent.parent / "dashboard",  # our copy
        # Original location
        Path(r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4"),
        Path(r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4\the-livehouse-dashboard"),
    ]
    for p in candidates:
        if p.exists() and (p / "data").exists():
            return p
    return None


def find_onimator_base():
    """Find the base dir containing devices.db and device folders."""
    candidates = [
        Path(r"C:\Users\TheLiveHouse\Downloads\full_igbot_14.2.4\full_igbot_14.2.4"),
    ]
    for p in candidates:
        if p.exists() and (p / "devices.db").exists():
            return p
    return None


def is_device_serial(name):
    """Check if folder name looks like a device serial (IP_port)."""
    return bool(re.match(r'^\d+\.\d+\.\d+\.\d+_\d+$', name))


# ===================================================================
#  IMPORT FUNCTIONS
# ===================================================================

def import_devices(conn, base_dir, dry_run=False):
    """Import from devices.db"""
    devices_db = base_dir / "devices.db"
    if not devices_db.exists():
        print(f"  [!] devices.db not found at {devices_db}")
        return 0

    src = sqlite3.connect(str(devices_db))
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM devices").fetchall()
    src.close()

    count = 0
    for row in rows:
        d = dict(row)
        serial = d.get("deviceid", "")
        name = d.get("devicename", "")
        status = d.get("status", "disconnected")
        if not serial:
            continue

        if dry_run:
            print(f"    [DRY] Device: {serial} ({name})")
        else:
            insert_device(conn, serial, name, status)
        count += 1

    print(f"  [OK] Devices: {count}")
    return count


def import_accounts_for_device(conn, base_dir, device_serial, dry_run=False):
    """Import accounts from {device}/accounts.db + per-account data."""
    accounts_db = base_dir / device_serial / "accounts.db"
    if not accounts_db.exists():
        return 0

    src = sqlite3.connect(str(accounts_db))
    src.row_factory = sqlite3.Row

    try:
        rows = src.execute("SELECT * FROM accounts").fetchall()
    except Exception as e:
        print(f"    [!] Error reading accounts.db for {device_serial}: {e}")
        src.close()
        return 0
    src.close()

    count = 0
    for row in rows:
        d = dict(row)
        username = d.get("account", "")
        if not username:
            continue

        if dry_run:
            print(f"    [DRY] Account: {device_serial}/{username}")
            count += 1
            continue

        # Insert account with all toggle fields
        acct_id = insert_account(
            conn, device_serial, username,
            password=d.get("password", ""),
            email=d.get("email", ""),
            follow=d.get("follow", "False"),
            unfollow=d.get("unfollow", "False"),
            mute=d.get("mute", "False"),
            like=d.get("like", "False"),
            comment=d.get("comment", "False"),
            story=d.get("story", "False"),
            switchmode=d.get("switchmode", "False"),
            starttime=d.get("starttime", "0"),
            endtime=d.get("endtime", "0"),
            followaction=d.get("followaction", "0"),
            unfollowaction=d.get("unfollowaction", "0"),
            randomaction=d.get("randomaction", "30,60"),
            randomdelay=d.get("randomdelay", "30,60"),
            followdelay=d.get("followdelay", "30"),
            unfollowdelay=d.get("unfollowdelay", "30"),
            likedelay=d.get("likedelay", "0"),
            followlimitperday=d.get("followlimitperday", "0"),
            unfollowlimitperday=d.get("unfollowlimitperday", "0"),
            likelimitperday=d.get("likelimitperday", "0"),
            unfollowdelayday=d.get("unfollowdelayday", "3"),
        )

        # Import settings.db
        _import_account_settings(conn, base_dir, device_serial, username, acct_id)
        # Import stats.db
        _import_account_stats(conn, base_dir, device_serial, username, acct_id)
        # Import text files (sources, whitelist, prompts)
        _import_account_text_files(conn, base_dir, device_serial, username, acct_id)

        count += 1

    return count


def _import_account_settings(conn, base_dir, device_serial, username, account_id):
    """Import settings.db JSON for one account."""
    settings_db = base_dir / device_serial / username / "settings.db"
    if not settings_db.exists():
        # Insert defaults
        upsert_account_settings(conn, account_id, DEFAULT_ACCOUNT_SETTINGS)
        return

    try:
        src = sqlite3.connect(str(settings_db))
        row = src.execute("SELECT settings FROM accountsettings WHERE id=1").fetchone()
        src.close()
        if row and row[0]:
            settings = json.loads(row[0])
            upsert_account_settings(conn, account_id, settings)
        else:
            upsert_account_settings(conn, account_id, DEFAULT_ACCOUNT_SETTINGS)
    except Exception as e:
        print(f"      [!] settings.db error for {username}: {e}")
        upsert_account_settings(conn, account_id, DEFAULT_ACCOUNT_SETTINGS)


def _import_account_stats(conn, base_dir, device_serial, username, account_id):
    """Import stats.db for one account."""
    stats_db = base_dir / device_serial / username / "stats.db"
    if not stats_db.exists():
        return

    try:
        src = sqlite3.connect(str(stats_db))
        src.row_factory = sqlite3.Row
        rows = src.execute("SELECT * FROM stats ORDER BY date").fetchall()
        src.close()

        for row in rows:
            d = dict(row)
            insert_stat(
                conn, account_id,
                date=d.get("date", ""),
                followers=d.get("followers", "0"),
                following=d.get("following", "0"),
                posts=d.get("posts", "0"),
            )
    except Exception as e:
        print(f"      [!] stats.db error for {username}: {e}")


def _import_account_text_files(conn, base_dir, device_serial, username, account_id):
    """Import text config files (sources.txt, whitelist.txt, prompts, etc.)."""
    account_dir = base_dir / device_serial / username
    if not account_dir.exists():
        return

    # Source files → account_sources table
    source_files = {
        "sources.txt": "sources",
        "whitelist.txt": "whitelist",
        "follow-specific-sources.txt": "follow_specific_sources",
        "follow-likers-sources.txt": "follow_likers_sources",
        "follow_using_word_search.txt": "follow_word_search",
        "unfollow-specific-accounts.txt": "unfollow_specific",
        "like_post_likers_using_keyword_search.txt": "like_keyword_search",
        "comment_using_keyword_search.txt": "comment_keyword_search",
        "view_specific_user.txt": "view_specific_user",
        "view_specific_user_highlight.txt": "view_specific_highlight",
        "directmessagespecificuser.txt": "dm_specific_user",
        "storyviewer-user-followers-sources.txt": "story_followers_sources",
        "storyviewer-user-likers-sources.txt": "story_likers_sources",
        "close-friends.txt": "close_friends",
        "watch_reels_sources.txt": "watch_reels_sources",
    }

    for filename, source_type in source_files.items():
        filepath = account_dir / filename
        if filepath.exists():
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").strip().split("\n")
                for line in lines:
                    val = line.strip()
                    if val:
                        conn.execute(
                            "INSERT OR IGNORE INTO account_sources (account_id, source_type, value) VALUES (?,?,?)",
                            (account_id, source_type, val),
                        )
            except Exception:
                pass

    # Text config files → account_text_configs table
    text_configs = {
        "gpt_prompt.txt": "gpt_prompt",
        "comment_gpt_prompt.txt": "comment_gpt_prompt",
        "message_new_followers_gpt_prompt.txt": "dm_new_followers_prompt",
        "message_specific_users_gpt_prompt.txt": "dm_specific_users_prompt",
        "caption_prompt.txt": "caption_prompt",
        "name_must_include.txt": "name_must_include",
        "name_must_not_include.txt": "name_must_not_include",
    }

    now = datetime.now().isoformat()
    for filename, config_type in text_configs.items():
        filepath = account_dir / filename
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    conn.execute(
                        """INSERT INTO account_text_configs (account_id, config_type, content, updated_at)
                           VALUES (?,?,?,?)
                           ON CONFLICT(account_id, config_type) DO UPDATE SET
                             content=excluded.content, updated_at=excluded.updated_at""",
                        (account_id, config_type, content, now),
                    )
            except Exception:
                pass

    conn.commit()


def import_media_library(conn, dashboard_dir, dry_run=False):
    """Import media_library.db → media, tags, media_tags, folders, media_folders."""
    ml_db = dashboard_dir / "data" / "media_library" / "media_library.db"
    if not ml_db.exists():
        print(f"  [!] media_library.db not found at {ml_db}")
        return 0

    src = sqlite3.connect(str(ml_db))
    src.row_factory = sqlite3.Row

    count = 0

    # Media items
    try:
        for row in src.execute("SELECT * FROM media").fetchall():
            d = dict(row)
            if dry_run:
                print(f"    [DRY] Media: {d.get('filename', '?')}")
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO media
                       (id, filename, original_path, processed_path, media_type, file_size,
                        width, height, duration, tags, description, upload_date, times_used, last_used)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (d["id"], d["filename"], d["original_path"], d.get("processed_path"),
                     d["media_type"], d.get("file_size"), d.get("width"), d.get("height"),
                     d.get("duration"), d.get("tags"), d.get("description"),
                     d.get("upload_date"), d.get("times_used", 0), d.get("last_used")),
                )
            count += 1
    except Exception as e:
        print(f"    [!] media import error: {e}")

    # Tags
    try:
        for row in src.execute("SELECT * FROM tags").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute("INSERT OR IGNORE INTO tags (id, name) VALUES (?,?)", (d["id"], d["name"]))
    except Exception:
        pass

    # Media-tag links
    try:
        for row in src.execute("SELECT * FROM media_tags").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO media_tags (media_id, tag_id) VALUES (?,?)",
                    (d["media_id"], d["tag_id"]),
                )
    except Exception:
        pass

    # Folders
    try:
        for row in src.execute("SELECT * FROM folders").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO folders (id, name, description, created_at, parent_id) VALUES (?,?,?,?,?)",
                    (d["id"], d["name"], d.get("description"), d.get("created_at"), d.get("parent_id")),
                )
    except Exception:
        pass

    # Media-folder links
    try:
        for row in src.execute("SELECT * FROM media_folders").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO media_folders (media_id, folder_id) VALUES (?,?)",
                    (d["media_id"], d["folder_id"]),
                )
    except Exception:
        pass

    # Content categories
    try:
        for row in src.execute("SELECT * FROM content_categories").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO content_categories (id, name, posting_frequency, hashtags, caption_template, created_at, last_used) VALUES (?,?,?,?,?,?,?)",
                    (d["id"], d["name"], d.get("posting_frequency"), d.get("hashtags"),
                     d.get("caption_template"), d.get("created_at"), d.get("last_used")),
                )
    except Exception:
        pass

    if not dry_run:
        conn.commit()
    src.close()
    print(f"  [OK] Media library: {count} items")
    return count


def import_scheduled_posts(conn, dashboard_dir, dry_run=False):
    """Import scheduled_posts.db."""
    sp_db = dashboard_dir / "data" / "scheduled_posts" / "scheduled_posts.db"
    if not sp_db.exists():
        print(f"  [!] scheduled_posts.db not found")
        return 0

    src = sqlite3.connect(str(sp_db))
    src.row_factory = sqlite3.Row
    count = 0

    try:
        for row in src.execute("SELECT * FROM scheduled_posts").fetchall():
            d = dict(row)
            if dry_run:
                print(f"    [DRY] Post: {d.get('account', '?')} @ {d.get('scheduled_time', '?')}")
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO scheduled_posts
                       (id, deviceid, account, post_type, caption, media_path, location, scheduled_time, status, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (d["id"], d["deviceid"], d["account"], d["post_type"],
                     d.get("caption"), d.get("media_path"), d.get("location"),
                     d["scheduled_time"], d.get("status", "scheduled"),
                     d.get("created_at"), d.get("updated_at")),
                )
            count += 1
    except Exception as e:
        print(f"    [!] scheduled_posts import error: {e}")

    if not dry_run:
        conn.commit()
    src.close()
    print(f"  [OK] Scheduled posts: {count}")
    return count


def import_account_inventory(conn, dashboard_dir, dry_run=False):
    """Import account_inventory.db."""
    inv_db = dashboard_dir / "data" / "account_inventory" / "account_inventory.db"
    if not inv_db.exists():
        print(f"  [!] account_inventory.db not found")
        return 0

    src = sqlite3.connect(str(inv_db))
    src.row_factory = sqlite3.Row
    count = 0

    try:
        for row in src.execute("SELECT * FROM account_inventory").fetchall():
            d = dict(row)
            if dry_run:
                print(f"    [DRY] Inventory: {d.get('username', '?')} ({d.get('status', '?')})")
            else:
                conn.execute(
                    """INSERT OR IGNORE INTO account_inventory
                       (username, password, two_factor_auth, status, device_assigned, date_added, date_used, notes, appid)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (d["username"], d["password"], d.get("two_factor_auth"),
                     d.get("status", "available"), d.get("device_assigned"),
                     d.get("date_added"), d.get("date_used"), d.get("notes"),
                     d.get("appid", "com.instagram.android")),
                )
            count += 1
    except Exception as e:
        print(f"    [!] account_inventory import error: {e}")

    if not dry_run:
        conn.commit()
    src.close()
    print(f"  [OK] Account inventory: {count}")
    return count


def import_caption_templates(conn, base_dir, dry_run=False):
    """Import caption_templates.db (lives at Onimator root level)."""
    ct_db = base_dir / "caption_templates.db"
    if not ct_db.exists():
        # Also check dashboard data dir
        ct_db = base_dir / "the-livehouse-dashboard" / "caption_templates.db"
    if not ct_db.exists():
        return 0

    src = sqlite3.connect(str(ct_db))
    src.row_factory = sqlite3.Row
    count = 0

    try:
        for row in src.execute("SELECT * FROM caption_templates").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO caption_templates (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
                    (d["id"], d["name"], d.get("description"), d.get("created_at"), d.get("updated_at")),
                )
            count += 1

        for row in src.execute("SELECT * FROM captions").fetchall():
            d = dict(row)
            if not dry_run:
                conn.execute(
                    "INSERT OR IGNORE INTO captions (id, template_id, caption, created_at) VALUES (?,?,?,?)",
                    (d["id"], d["template_id"], d["caption"], d.get("created_at")),
                )
    except Exception as e:
        print(f"    [!] caption_templates import error: {e}")

    if not dry_run:
        conn.commit()
    src.close()
    print(f"  [OK] Caption templates: {count}")
    return count


# ===================================================================
#  MAIN
# ===================================================================

def run_import(source_dir=None, dry_run=False):
    """Run the full import pipeline."""
    print("=" * 60)
    print("Phone Farm — Data Import")
    print("=" * 60)

    # Find source directories
    base_dir = Path(source_dir) if source_dir else find_onimator_base()
    dashboard_dir = None

    if base_dir and base_dir.exists():
        print(f"\nOnimator base: {base_dir}")
        # Dashboard is a subfolder of base
        dash_candidate = base_dir / "the-livehouse-dashboard"
        if dash_candidate.exists():
            dashboard_dir = dash_candidate
    else:
        print("\n[!] Onimator base directory not found")
        base_dir = None

    # Fallback: use our own dashboard copy for media/inventory/posts
    our_dashboard = Path(__file__).parent.parent / "dashboard"
    if not dashboard_dir and our_dashboard.exists():
        dashboard_dir = our_dashboard
        print(f"Using local dashboard copy: {dashboard_dir}")

    if dashboard_dir:
        print(f"Dashboard dir: {dashboard_dir}")

    if not base_dir and not dashboard_dir:
        print("\n[X] No data sources found. Provide --source or check paths.")
        return

    # Initialize target DB
    if not dry_run:
        print(f"\nTarget DB: {DB_PATH}")
        init_db()
        conn = get_connection()
    else:
        print("\n[DRY RUN — no data will be written]")
        conn = None

    # 1. Import devices
    if base_dir:
        print("\n--- Devices ---")
        import_devices(conn, base_dir, dry_run)

    # 2. Import accounts per device
    if base_dir:
        print("\n--- Accounts ---")
        total_accounts = 0
        for entry in sorted(base_dir.iterdir()):
            if entry.is_dir() and is_device_serial(entry.name):
                n = import_accounts_for_device(conn, base_dir, entry.name, dry_run)
                if n:
                    print(f"  [OK] {entry.name}: {n} accounts")
                total_accounts += n
        print(f"  Total accounts imported: {total_accounts}")

    # 3. Import media library
    if dashboard_dir:
        print("\n--- Media Library ---")
        import_media_library(conn, dashboard_dir, dry_run)

    # 4. Import scheduled posts
    if dashboard_dir:
        print("\n--- Scheduled Posts ---")
        import_scheduled_posts(conn, dashboard_dir, dry_run)

    # 5. Import account inventory
    if dashboard_dir:
        print("\n--- Account Inventory ---")
        import_account_inventory(conn, dashboard_dir, dry_run)

    # 6. Import caption templates
    if base_dir:
        print("\n--- Caption Templates ---")
        import_caption_templates(conn, base_dir, dry_run)

    # Done
    if conn:
        conn.close()

    print("\n" + "=" * 60)
    print("Import complete!" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Onimator data into Phone Farm DB")
    parser.add_argument("--source", help="Path to Onimator root (full_igbot_14.2.4/)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without writing")
    args = parser.parse_args()

    run_import(source_dir=args.source, dry_run=args.dry_run)
