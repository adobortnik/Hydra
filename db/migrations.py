"""
Hydra DB Migrations
====================
Central place for ALL table definitions and schema migrations.
Run ensure_schema() on every dashboard/bot startup to guarantee
all tables exist, even on fresh installs.

When adding a new table:
  1. Add CREATE TABLE IF NOT EXISTS to SCHEMA_TABLES
  2. If altering existing table, add ALTER to MIGRATIONS list
  3. That's it — runs automatically on startup
"""

import sqlite3
import os
import sys
import logging

log = logging.getLogger(__name__)


def _full_schema():
    """The COMPLETE table schema from init_db.py — the single source of truth for
    table definitions. Imported (works even when obfuscated in client builds) so
    ensure_schema creates EVERY table on update, not just the subset below. Returns
    the SCHEMA string, or None if init_db can't be imported (falls back to
    SCHEMA_TABLES)."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import init_db
        return getattr(init_db, 'SCHEMA', None)
    except Exception as e:
        log.warning("Could not load full schema from init_db: %s", e)
        return None

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'phone_farm.db'
)

# ─── All table definitions ───────────────────────────────────────────
# These run as CREATE TABLE IF NOT EXISTS — safe to run every time
SCHEMA_TABLES = """

-- Core tables
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial TEXT UNIQUE NOT NULL,
    device_name TEXT,
    model TEXT,
    android_version TEXT,
    ip_address TEXT,
    status TEXT DEFAULT 'online',
    last_seen TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id INTEGER,
    device_serial TEXT,
    username TEXT NOT NULL,
    password TEXT,
    email TEXT,
    instagram_package TEXT DEFAULT 'com.instagram.android',
    two_fa_token TEXT,
    status TEXT DEFAULT 'active',
    follow_enabled TEXT DEFAULT 'False',
    unfollow_enabled TEXT DEFAULT 'False',
    mute_enabled TEXT DEFAULT 'False',
    like_enabled TEXT DEFAULT 'False',
    comment_enabled TEXT DEFAULT 'False',
    story_enabled TEXT DEFAULT 'False',
    switchmode TEXT DEFAULT 'False',
    start_time TEXT DEFAULT '0',
    end_time TEXT DEFAULT '0',
    follow_action TEXT DEFAULT '0',
    unfollow_action TEXT DEFAULT '0',
    random_action TEXT DEFAULT '30,60',
    random_delay TEXT DEFAULT '30,60',
    follow_delay TEXT DEFAULT '30',
    unfollow_delay TEXT DEFAULT '30',
    like_delay TEXT DEFAULT '0',
    follow_limit_perday TEXT DEFAULT '0',
    unfollow_limit_perday TEXT DEFAULT '0',
    like_limit_perday TEXT DEFAULT '0',
    unfollow_delay_day TEXT DEFAULT '3',
    warmup INTEGER DEFAULT 0,
    warmup_until TEXT DEFAULT NULL,
    tag TEXT,
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    posts INTEGER DEFAULT 0,
    is_business_profile INTEGER DEFAULT 0,
    business_category TEXT,
    business_switched_at TEXT,
    is_private INTEGER DEFAULT 0,
    private_switched_at TEXT,
    display_name TEXT,
    display_name_set_at TEXT,
    profile_link TEXT,
    profile_link_title TEXT,
    profile_link_set_at TEXT,
    proxy TEXT,
    dm_enabled TEXT DEFAULT 'False',
    share_enabled TEXT DEFAULT 'False',
    reels_enabled TEXT DEFAULT 'False',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id),
    UNIQUE(device_serial, username)
);

CREATE TABLE IF NOT EXISTS account_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL UNIQUE,
    settings_json TEXT DEFAULT '{}',
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS account_text_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    config_type TEXT NOT NULL,
    content TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Follower tracking
CREATE TABLE IF NOT EXISTS follower_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    username TEXT,
    device_serial TEXT,
    followers INTEGER DEFAULT 0,
    following INTEGER DEFAULT 0,
    posts INTEGER DEFAULT 0,
    posts_count INTEGER DEFAULT 0,
    captured_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Action history
CREATE TABLE IF NOT EXISTS action_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    device_serial TEXT,
    username TEXT,
    action_type TEXT,
    target_username TEXT,
    success INTEGER DEFAULT 1,
    error_message TEXT,
    extra_data TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Job orders system
CREATE TABLE IF NOT EXISTS job_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT,
    job_type TEXT NOT NULL,
    target TEXT,
    target_count INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    limit_per_hour INTEGER DEFAULT 50,
    limit_per_day INTEGER DEFAULT 200,
    comment_text TEXT,
    status TEXT DEFAULT 'active',
    priority INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT,
    report_reason TEXT,
    comment_list_id INTEGER,
    ai_mode TEXT,
    vision_ai INTEGER DEFAULT 0,
    finished_at TEXT,
    action_delay_seconds INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    device_serial TEXT,
    username TEXT,
    status TEXT DEFAULT 'assigned',
    completed_count INTEGER DEFAULT 0,
    last_action_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    action_type TEXT,
    target TEXT,
    status TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE
);

-- Content scheduling
CREATE TABLE IF NOT EXISTS content_schedule (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    device_serial TEXT,
    content_type TEXT DEFAULT 'post',
    media_path TEXT,
    caption TEXT,
    scheduled_time TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    posted_at TEXT
);

-- Tags system
CREATE TABLE IF NOT EXISTS account_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account_id, tag),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Follow lists
CREATE TABLE IF NOT EXISTS follow_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS follow_list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    followed_by TEXT,
    followed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (list_id) REFERENCES follow_lists(id) ON DELETE CASCADE
);

-- Comment lists
CREATE TABLE IF NOT EXISTS comment_lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comment_list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id INTEGER NOT NULL,
    comment_text TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (list_id) REFERENCES comment_lists(id) ON DELETE CASCADE
);

-- Follow sources
CREATE TABLE IF NOT EXISTS follow_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    source_username TEXT NOT NULL,
    source_type TEXT DEFAULT 'followers',
    is_dead INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    last_used TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- Follower orders (mass follow campaigns)
CREATE TABLE IF NOT EXISTS follower_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_username TEXT NOT NULL,
    target_count INTEGER DEFAULT 100,
    completed_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);

-- Global settings
CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Session tracking
CREATE TABLE IF NOT EXISTS bot_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial TEXT,
    username TEXT,
    session_id TEXT UNIQUE,
    started_at TEXT DEFAULT (datetime('now')),
    ended_at TEXT,
    actions_done INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0
);

"""

# ─── Schema migrations (ALTER TABLE, etc.) ───────────────────────────
# Each migration has a unique name — only runs once
MIGRATIONS = [
    # job_orders
    {'name': 'add_finished_at_to_job_orders',
     'sql': "ALTER TABLE job_orders ADD COLUMN finished_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='job_orders' AND sql LIKE '%finished_at%'"},
    {'name': 'add_action_delay_seconds_to_job_orders',
     'sql': "ALTER TABLE job_orders ADD COLUMN action_delay_seconds INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='job_orders' AND sql LIKE '%action_delay_seconds%'"},
    {'name': 'add_unique_comments_to_job_orders',
     'sql': "ALTER TABLE job_orders ADD COLUMN unique_comments INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='job_orders' AND sql LIKE '%unique_comments%'"},
    {'name': 'add_comment_used_to_job_history',
     'sql': "ALTER TABLE job_history ADD COLUMN comment_used TEXT DEFAULT NULL",
     'check': "SELECT sql FROM sqlite_master WHERE name='job_history' AND sql LIKE '%comment_used%'"},

    # accounts — columns that may be missing on older DBs
    {'name': 'add_followers_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN followers INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%followers%'"},
    {'name': 'add_following_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN following INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%following%'"},
    {'name': 'add_posts_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN posts INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '% posts %'"},
    {'name': 'add_is_business_profile_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN is_business_profile INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%is_business_profile%'"},
    {'name': 'add_business_category_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN business_category TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%business_category%'"},
    {'name': 'add_follow_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN follow_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%follow_enabled%'"},
    {'name': 'add_unfollow_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN unfollow_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%unfollow_enabled%'"},
    {'name': 'add_like_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN like_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%like_enabled%'"},
    {'name': 'add_comment_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN comment_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%comment_enabled%'"},
    {'name': 'add_story_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN story_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%story_enabled%'"},
    {'name': 'add_dm_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN dm_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%dm_enabled%'"},
    {'name': 'add_share_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN share_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%share_enabled%'"},
    {'name': 'add_reels_enabled_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN reels_enabled INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%reels_enabled%'"},
    {'name': 'add_start_time_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN start_time TEXT DEFAULT '0'",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%start_time%'"},
    {'name': 'add_end_time_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN end_time TEXT DEFAULT '0'",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%end_time%'"},
    {'name': 'add_proxy_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN proxy TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%proxy%'"},
    {'name': 'add_updated_at_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN updated_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%updated_at%'"},
    {'name': 'add_tag_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN tag TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%tag %'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN device_id INTEGER",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%device_id%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN two_fa_token TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%two_fa_token%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN display_name TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%display_name %'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN display_name_set_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%display_name_set_at%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN profile_link TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%profile_link %'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN profile_link_title TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%profile_link_title%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN profile_link_set_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%profile_link_set_at%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN business_switched_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%business_switched_at%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN is_private INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%is_private%'"},
    {'sql': "ALTER TABLE accounts ADD COLUMN private_switched_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%private_switched_at%'"},

    # Mother account flag (added 2026-05-01) — used by mothers dashboard
    {'name': 'add_is_mother_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN is_mother INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%is_mother%'"},
    {'name': 'idx_accounts_is_mother',
     'sql': "CREATE INDEX IF NOT EXISTS idx_accounts_is_mother ON accounts(is_mother) WHERE is_mother=1",
     'check': "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_accounts_is_mother'"},

    # Account Status snapshot (Settings → Account Status sekcia v IG)
    # JSON: {removed_content, recommendable, monetization, features_usable, captured_at}
    {'name': 'add_account_status_json_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN account_status_json TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%account_status_json%'"},
    {'name': 'add_account_status_checked_at_to_accounts',
     'sql': "ALTER TABLE accounts ADD COLUMN account_status_checked_at TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='accounts' AND sql LIKE '%account_status_checked_at%'"},

    # follower_snapshots — columns added after initial table creation
    {'name': 'add_device_serial_to_follower_snapshots',
     'sql': "ALTER TABLE follower_snapshots ADD COLUMN device_serial TEXT",
     'check': "SELECT sql FROM sqlite_master WHERE name='follower_snapshots' AND sql LIKE '%device_serial%'"},
    {'name': 'add_posts_count_to_follower_snapshots',
     'sql': "ALTER TABLE follower_snapshots ADD COLUMN posts_count INTEGER DEFAULT 0",
     'check': "SELECT sql FROM sqlite_master WHERE name='follower_snapshots' AND sql LIKE '%posts_count%'"},
]


def ensure_schema(db_path=None):
    """
    Ensure all tables exist and migrations are applied.
    Safe to call on every startup — uses IF NOT EXISTS and checks.
    """
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)

    # Create all tables — prefer the COMPLETE schema from init_db.py (single source
    # of truth, ~41 tables); fall back to the legacy subset below if unavailable.
    full = _full_schema()
    if full:
        conn.executescript(full)
        conn.commit()
    conn.executescript(SCHEMA_TABLES)

    # Run migrations
    for m in MIGRATIONS:
        # Use migration name if provided, else derive from SQL for logs
        m_name = m.get('name') or (m.get('sql', '')[:60] + '...')
        try:
            # Check if migration already applied
            if m.get('check'):
                result = conn.execute(m['check']).fetchone()
                if result:
                    continue  # Already applied

            conn.execute(m['sql'])
            conn.commit()
            log.info("Migration applied: %s", m_name)
        except Exception as e:
            # Likely already applied (duplicate column, etc.)
            if 'duplicate' not in str(e).lower() and 'already exists' not in str(e).lower():
                log.warning("Migration '%s' skipped: %s", m_name, e)

    conn.commit()
    conn.close()
    log.info("Schema check complete — all tables verified")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    ensure_schema()
    print("Schema verified OK")
