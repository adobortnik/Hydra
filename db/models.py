"""
Phone Farm Database Models
==========================
Self-contained SQLite schema for the phone farm platform.
Replaces Onimator's scattered per-device/per-account DB files with a single
normalized database while staying compatible with the dashboard UI expectations.

Database: phone_farm.db (single file, thread-safe)

Tables:
  - devices              Master device registry
  - accounts             Instagram accounts (with device FK)
  - account_settings     Detailed bot settings (JSON, mirrors Onimator settings.db)
  - account_stats        Daily statistics snapshots
  - account_sources      Source accounts for follow/like targets
  - account_text_configs Text config files (whitelist, prompts, etc.)
  - tasks                Automation task queue
  - task_history         Completed task audit log
  - media                Media library items
  - media_tags           M2M: media ↔ tags
  - tags                 Tag registry
  - folders              Media folder hierarchy
  - media_folders        M2M: media ↔ folders
  - content_categories   Posting categories
  - scheduled_posts      Scheduled post queue
  - caption_templates    Caption template groups
  - captions             Individual captions within templates
  - account_inventory    Spare account pool (not yet assigned to devices)
  - follower_orders      JAP follower order tracking
  - login_tasks          Login automation queue
  - login_history        Login attempt audit
  - profile_updates      Profile automation tasks
  - bio_templates        Profile bio templates
  - profile_pictures     Profile picture library
  - bot_status           Per-device bot process status
  - account_sessions     Bot session tracking
  - action_history       Granular action log
"""

import os
import sqlite3
import json
import datetime

# ---------------------------------------------------------------------------
# Database location
# ---------------------------------------------------------------------------
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "phone_farm.db")


def get_connection(db_path=None):
    """Thread-safe connection with Row factory."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    """Convert sqlite3.Row → dict."""
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


# ===================================================================
#  SCHEMA DEFINITION
# ===================================================================

SCHEMA_SQL = """
-- ---------------------------------------------------------------
-- 1. DEVICES  (replaces Onimator devices.db → devices table)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL UNIQUE,   -- e.g. "10.1.10.183_5555"
    device_name     TEXT,                      -- friendly name
    ip_address      TEXT,                      -- parsed from serial
    adb_port        INTEGER DEFAULT 5555,
    status          TEXT    DEFAULT 'disconnected',  -- connected | disconnected | error
    last_seen       TEXT,                      -- ISO timestamp
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 2. ACCOUNTS  (replaces per-device accounts.db → accounts table)
--    Stores credentials + master ON/OFF toggles from accounts.db
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER,                   -- FK → devices.id (NULL = unassigned)
    device_serial   TEXT,                      -- denormalized for easy lookup
    username        TEXT    NOT NULL,
    password        TEXT,
    email           TEXT,
    instagram_package TEXT  DEFAULT 'com.instagram.android',
    two_fa_token    TEXT,                      -- TOTP secret
    status          TEXT    DEFAULT 'active',  -- active | disabled | banned | logged_out
    -- Master toggles (from Onimator accounts.db, stored as 'True'/'False' strings)
    follow_enabled      TEXT DEFAULT 'False',
    unfollow_enabled    TEXT DEFAULT 'False',
    mute_enabled        TEXT DEFAULT 'False',
    like_enabled        TEXT DEFAULT 'False',
    comment_enabled     TEXT DEFAULT 'False',
    story_enabled       TEXT DEFAULT 'False',
    switchmode          TEXT DEFAULT 'False',
    -- Scheduling
    start_time      TEXT    DEFAULT '0',       -- hour 0-23
    end_time        TEXT    DEFAULT '0',       -- hour 0-23
    -- Action ranges (comma-separated min,max)
    follow_action   TEXT    DEFAULT '0',
    unfollow_action TEXT    DEFAULT '0',
    random_action   TEXT    DEFAULT '30,60',
    random_delay    TEXT    DEFAULT '30,60',
    follow_delay    TEXT    DEFAULT '30',
    unfollow_delay  TEXT    DEFAULT '30',
    like_delay      TEXT    DEFAULT '0',
    -- Daily limits
    follow_limit_perday     TEXT DEFAULT '0',
    unfollow_limit_perday   TEXT DEFAULT '0',
    like_limit_perday       TEXT DEFAULT '0',
    unfollow_delay_day      TEXT DEFAULT '3',
    -- Metadata
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id),
    UNIQUE(device_serial, username)
);

-- ---------------------------------------------------------------
-- 3. ACCOUNT SETTINGS  (replaces {device}/{account}/settings.db)
--    Single JSON blob per account — mirrors Onimator exactly
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_settings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL UNIQUE,
    settings_json   TEXT    NOT NULL DEFAULT '{}', -- Full Onimator-compatible JSON
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- 4. ACCOUNT STATS  (replaces {device}/{account}/stats.db)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    date            TEXT    NOT NULL,           -- YYYY-MM-DD
    followers       TEXT    DEFAULT '0',
    following       TEXT    DEFAULT '0',
    posts           TEXT    DEFAULT '0',
    follows_done    INTEGER DEFAULT 0,
    unfollows_done  INTEGER DEFAULT 0,
    likes_done      INTEGER DEFAULT 0,
    comments_done   INTEGER DEFAULT 0,
    stories_viewed  INTEGER DEFAULT 0,
    dms_sent        INTEGER DEFAULT 0,
    created_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE(account_id, date)
);

-- ---------------------------------------------------------------
-- 5. ACCOUNT SOURCES  (replaces {device}/{account}/sources.txt etc.)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    source_type     TEXT    NOT NULL,           -- 'sources' | 'whitelist' | 'follow_specific' | etc.
    value           TEXT    NOT NULL,           -- username or keyword
    created_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- 6. ACCOUNT TEXT CONFIGS  (replaces *.txt files per account)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_text_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    config_type     TEXT    NOT NULL,           -- 'gpt_prompt' | 'comment_gpt_prompt' | etc.
    content         TEXT    NOT NULL DEFAULT '',
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE(account_id, config_type)
);

-- ---------------------------------------------------------------
-- 7. TASKS  (automation task queue)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER,
    device_serial   TEXT,
    task_type       TEXT    NOT NULL,           -- 'follow' | 'unfollow' | 'like' | 'comment' | 'post' | 'login' | 'profile_update'
    status          TEXT    DEFAULT 'pending',  -- pending | running | completed | failed | cancelled
    priority        INTEGER DEFAULT 0,
    scheduled_time  TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    params_json     TEXT    DEFAULT '{}',       -- task-specific parameters
    result_json     TEXT,                       -- task result / error
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- ---------------------------------------------------------------
-- 8. TASK HISTORY  (completed tasks log — never deleted)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER,
    account_id      INTEGER,
    device_serial   TEXT,
    task_type       TEXT    NOT NULL,
    status          TEXT    NOT NULL,           -- completed | failed
    started_at      TEXT,
    completed_at    TEXT,
    duration_sec    REAL,
    params_json     TEXT,
    result_json     TEXT,
    error_message   TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 9. MEDIA LIBRARY  (compatible with existing dashboard)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media (
    id              TEXT    PRIMARY KEY,        -- UUID hash
    filename        TEXT    NOT NULL,
    original_path   TEXT    NOT NULL,
    processed_path  TEXT,
    media_type      TEXT    NOT NULL,           -- 'image' | 'video'
    file_size       INTEGER,
    width           INTEGER,
    height          INTEGER,
    duration        INTEGER,
    tags            TEXT,                       -- legacy comma-separated
    description     TEXT,
    upload_date     TEXT,
    times_used      INTEGER DEFAULT 0,
    last_used       TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    UNIQUE
);

CREATE TABLE IF NOT EXISTS media_tags (
    media_id        TEXT,
    tag_id          INTEGER,
    PRIMARY KEY (media_id, tag_id),
    FOREIGN KEY (media_id)  REFERENCES media(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)    REFERENCES tags(id)  ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- 10. MEDIA FOLDERS
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS folders (
    id              TEXT    PRIMARY KEY,        -- UUID
    name            TEXT    NOT NULL,
    description     TEXT,
    created_at      TEXT,
    parent_id       TEXT,
    FOREIGN KEY (parent_id) REFERENCES folders(id)
);

CREATE TABLE IF NOT EXISTS media_folders (
    media_id        TEXT,
    folder_id       TEXT,
    PRIMARY KEY (media_id, folder_id),
    FOREIGN KEY (media_id)  REFERENCES media(id)   ON DELETE CASCADE,
    FOREIGN KEY (folder_id) REFERENCES folders(id)  ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- 11. CONTENT CATEGORIES
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_categories (
    id              TEXT    PRIMARY KEY,
    name            TEXT    NOT NULL,
    posting_frequency TEXT,
    hashtags        TEXT,
    caption_template TEXT,
    created_at      TEXT,
    last_used       TEXT
);

-- ---------------------------------------------------------------
-- 12. SCHEDULED POSTS  (compatible with existing dashboard)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduled_posts (
    id              TEXT    PRIMARY KEY,        -- UUID
    deviceid        TEXT    NOT NULL,
    account         TEXT    NOT NULL,
    post_type       TEXT    NOT NULL,           -- 'post' | 'reels' | 'story'
    caption         TEXT,
    media_path      TEXT,
    location        TEXT,
    scheduled_time  TEXT    NOT NULL,
    status          TEXT    DEFAULT 'scheduled', -- scheduled | posted | failed
    created_at      TEXT,
    updated_at      TEXT
);

-- ---------------------------------------------------------------
-- 13. CAPTION TEMPLATES  (compatible with existing dashboard)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS caption_templates (
    id              TEXT    PRIMARY KEY,
    name            TEXT    NOT NULL,
    description     TEXT,
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS captions (
    id              TEXT    PRIMARY KEY,
    template_id     TEXT    NOT NULL,
    caption         TEXT    NOT NULL,
    created_at      TEXT,
    FOREIGN KEY (template_id) REFERENCES caption_templates(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------
-- 14. ACCOUNT INVENTORY  (spare accounts pool)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    password        TEXT    NOT NULL,
    email           TEXT,
    phone           TEXT,
    two_factor_auth TEXT,
    status          TEXT    DEFAULT 'available',  -- available | assigned | burned
    device_assigned TEXT,
    assigned_to_device_serial TEXT,
    assigned_to_account_id INTEGER,
    warmup_stage    TEXT,                         -- day1 | day3 | day5 | week2 | full | NULL
    date_added      TEXT,
    date_used       TEXT,
    assigned_at     TEXT,
    notes           TEXT,
    appid           TEXT    DEFAULT 'com.instagram.android'
);

-- ---------------------------------------------------------------
-- 14b. ACCOUNT HEALTH EVENTS  (health monitoring & flagging)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_health_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id              INTEGER NOT NULL,
    device_serial           TEXT,
    username                TEXT,
    event_type              TEXT    NOT NULL,  -- logged_out | suspended | verification_required | 2fa_required | action_blocked
    details                 TEXT,             -- extra info / XML snippet
    detected_at             TEXT    DEFAULT (datetime('now')),
    resolved_at             TEXT,             -- NULL until resolved
    resolved_by             TEXT,             -- manual | auto_replace
    replacement_account_id  INTEGER,          -- if auto-replaced, the new account
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- ---------------------------------------------------------------
-- 15. FOLLOWER ORDERS  (JAP API tracking)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS follower_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    quantity        INTEGER NOT NULL,
    service_id      INTEGER NOT NULL,
    order_id        TEXT    NOT NULL,
    status          TEXT    DEFAULT 'Pending',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- ---------------------------------------------------------------
-- 16. LOGIN AUTOMATION
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS login_tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    instagram_package TEXT  NOT NULL,
    username        TEXT    NOT NULL,
    password        TEXT    NOT NULL,
    two_fa_token    TEXT,
    status          TEXT    DEFAULT 'pending',
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    completed_at    TEXT,
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    priority        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS login_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    instagram_package TEXT  NOT NULL,
    username        TEXT    NOT NULL,
    login_type      TEXT    NOT NULL,
    success         INTEGER DEFAULT 1,
    logged_in_at    TEXT    DEFAULT (datetime('now')),
    error_details   TEXT,
    two_fa_used     INTEGER DEFAULT 0,
    challenge_encountered INTEGER DEFAULT 0
);

-- ---------------------------------------------------------------
-- 17. PROFILE AUTOMATION
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS profile_updates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    instagram_package TEXT  NOT NULL,
    username        TEXT,
    new_username    TEXT,
    new_bio         TEXT,
    profile_picture_id INTEGER,
    status          TEXT    DEFAULT 'pending',
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    completed_at    TEXT,
    error_message   TEXT,
    ai_api_key      TEXT,
    ai_provider     TEXT    DEFAULT 'openai',
    mother_account  TEXT
);

CREATE TABLE IF NOT EXISTS bio_templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    bio_text        TEXT    NOT NULL,
    category        TEXT,
    created_at      TEXT    DEFAULT (datetime('now')),
    times_used      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_pictures (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL,
    original_path   TEXT    NOT NULL,
    category        TEXT,
    gender          TEXT,
    uploaded_at     TEXT    DEFAULT (datetime('now')),
    times_used      INTEGER DEFAULT 0,
    description     TEXT
);

-- ---------------------------------------------------------------
-- 18. BOT MANAGEMENT  (replaces per-device bot_data/*.db)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bot_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    UNIQUE NOT NULL,
    status          TEXT    DEFAULT 'stopped',
    started_at      TEXT,
    last_check_at   TEXT,
    pid             INTEGER,
    accounts_run_today INTEGER DEFAULT 0,
    actions_today   INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS account_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    username        TEXT    NOT NULL,
    session_start   TEXT    DEFAULT (datetime('now')),
    session_end     TEXT,
    status          TEXT    DEFAULT 'running',
    actions_executed TEXT,
    errors_count    INTEGER DEFAULT 0,
    error_details   TEXT
);

CREATE TABLE IF NOT EXISTS action_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER,
    device_serial   TEXT    NOT NULL,
    username        TEXT    NOT NULL,
    action_type     TEXT    NOT NULL,
    target_username TEXT,
    target_post_id  TEXT,
    success         INTEGER DEFAULT 1,
    timestamp       TEXT    DEFAULT (datetime('now')),
    error_message   TEXT,
    FOREIGN KEY (session_id) REFERENCES account_sessions(id)
);

-- ---------------------------------------------------------------
-- 19. DEAD SOURCES  (tracks source accounts that can't be found)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dead_sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_username    TEXT    NOT NULL,   -- the bot account that was searching
    source_username     TEXT    NOT NULL,   -- the source that wasn't found
    fail_count          INTEGER DEFAULT 1,
    first_failed_at     TEXT    NOT NULL,   -- ISO timestamp
    last_failed_at      TEXT    NOT NULL,   -- ISO timestamp
    status              TEXT    DEFAULT 'suspect',  -- suspect → dead after 3 fails
    UNIQUE(account_username, source_username)
);

-- ---------------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_accounts_device       ON accounts(device_serial);
CREATE INDEX IF NOT EXISTS idx_accounts_username     ON accounts(username);
CREATE INDEX IF NOT EXISTS idx_account_stats_acct    ON account_stats(account_id, date);
CREATE INDEX IF NOT EXISTS idx_tasks_status          ON tasks(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_tasks_account         ON tasks(account_id);
CREATE INDEX IF NOT EXISTS idx_task_history_type     ON task_history(task_type, completed_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_posts_time  ON scheduled_posts(scheduled_time, status);
CREATE INDEX IF NOT EXISTS idx_login_tasks_status    ON login_tasks(status);
CREATE INDEX IF NOT EXISTS idx_account_inventory_status ON account_inventory(status);
CREATE INDEX IF NOT EXISTS idx_action_history_device ON action_history(device_serial, timestamp);
CREATE INDEX IF NOT EXISTS idx_health_events_account ON account_health_events(account_id, resolved_at);
CREATE INDEX IF NOT EXISTS idx_health_events_type    ON account_health_events(event_type, detected_at);
CREATE INDEX IF NOT EXISTS idx_inventory_status       ON account_inventory(status);
CREATE INDEX IF NOT EXISTS idx_dead_sources_account   ON dead_sources(account_username);
CREATE INDEX IF NOT EXISTS idx_dead_sources_source    ON dead_sources(source_username, status);
"""


# ===================================================================
#  DEFAULT SETTINGS (Onimator-compatible JSON)
# ===================================================================

DEFAULT_ACCOUNT_SETTINGS = {
    # Like settings
    "enable_likepost": False,
    "likepost_method": {
        "enable_likepost_sources_followers": True,
        "enable_likepost_via_keywords": False,
        "enable_likepost_specific_accounts": False,
    },
    "min_likepost_action": "10",
    "max_likepost_action": "20",
    "like_limit_perday": "50",
    "enable_auto_increment_like_limit_perday": False,
    "auto_increment_like_limit_perday_increase": "5",
    "auto_increment_like_limit_perday_increase_limit": "100",
    "like_enable_filters": False,
    "enable_dont_like_if_user_followed": False,
    "enable_dont_like_sametag_accounts": False,
    "like_story_after_liking_post": False,
    "min_post_to_like": "1",
    "max_post_to_like": "3",
    # Comment settings
    "enable_comment": False,
    "comment_method": {"comment_using_keyword_search": False},
    "comment_text": "[AI]",
    "min_comment": "5",
    "max_comment": "10",
    "comment_min_delay": "5",
    "comment_max_delay": "15",
    "comment_limit_perday": "25",
    "enable_dont_comment_sametag_accounts": False,
    # Story settings
    "enable_story_viewer": False,
    "view_method": {
        "view_followers": True,
        "view_likers": False,
        "view_specific_user": False,
        "view_specific_user_highlight": False,
    },
    "story_viewer_min": "10",
    "story_viewer_max": "20",
    "story_viewer_daily_limit": "800",
    "story_view_peraccount_view": "3",
    "like_story_after_viewing": False,
    "story_like_daily_limit": "200",
    "min_story_like_peraccount_view": "1",
    "max_story_like_peraccount_view": "3",
    "dont_view_same_account_twice": True,
    "view_highlight_if_no_story_viceversa": False,
    # DM settings
    "enable_directmessage": False,
    "directmessage_method": {
        "directmessage_new_followers": False,
        "directmessage_specificuser": False,
        "directmessage_reply": False,
        "enable_dm_crm": False,
    },
    "directmessage_min": "3",
    "directmessage_max": "5",
    "directmessage_min_delay": "10",
    "directmessage_max_delay": "30",
    "directmessage_daily_limit": "20",
    "message_check_delay": "60",
    "enable_send_message_every_new_line": False,
    "enable_openai_dm": False,
    "enable_cupidai_dm": False,
    "enable_openai_assistant": False,
    "openai_assistant_id": "",
    # Follow settings
    "follow_method": {
        "follow_followers": True,
        "follow_likers": False,
        "follow_specific_sources": False,
        "follow_using_word_search": False,
    },
    "default_action_limit_perday": "30",
    "enable_auto_increment_follow_limit_perday": False,
    "follow_timer_min_hour": "0",
    "follow_timer_max_hour": "24",
    "follow_is_weekdays": False,
    # Unfollow settings
    "unfollow_method": {
        "unfollow_using_profile": True,
        "unfollow_using_following_list": False,
        "unfollow_specific_accounts": False,
    },
    "unfollow_limit_perday": "30",
    "enable_auto_increment_unfollow_limit_perday": False,
    "unfollow_delay_day": "3",
    # Filter settings
    "enable_filters": False,
    "filters": {
        "min_followers": "0",
        "max_followers": "999999",
        "min_following": "0",
        "max_following": "999999",
        "min_posts": "0",
        "max_posts": "999999",
        "must_have_profile_pic": False,
        "must_be_business": False,
        "must_be_verified": False,
        "must_be_public": True,
        "skip_if_bio_contains": "",
        "must_bio_contain": "",
    },
    # Reels settings
    "enable_watch_reels": False,
    "min_reels_to_watch": "10",
    "max_reels_to_watch": "20",
    "watch_reels_duration_min": "5",
    "watch_reels_duration_max": "15",
    "watch_reels_daily_limit": "100",
    "enable_save_reels_while_watching": False,
    "save_reels_percent": "10",
    "enable_like_reels_while_watching": False,
    "like_reels_percent": "20",
    "enable_comment_reels_while_watching": False,
    "comment_reels_percent": "5",
    # Share to story
    "enable_shared_post": False,
    "post_type_to_share": "post",
    "shared_post_limit_perday": "5",
    "enable_add_mention_shared_post": False,
    "enable_add_hashtag_shared_post": False,
    "enable_add_sticker_shared_post": False,
    "enable_add_music_shared_post": False,
    "enable_repost_shared_post": False,
    "repost_limit_perday": "3",
    # Human behaviour emulation
    "enable_human_behaviour_emulation": False,
    "enable_viewhomefeedstory": False,
    "viewhomefeedstory_min": "3",
    "viewhomefeedstory_max": "10",
    "viewhomefeedstory_daily_limit": "50",
    "enable_scrollhomefeed": False,
    "scrollhomefeed_min": "5",
    "scrollhomefeed_max": "15",
    "scrollhomefeed_duration_min": "30",
    "scrollhomefeed_duration_max": "120",
    "enable_scrollexplorepage": False,
    "scrollexplorepage_min": "5",
    "scrollexplorepage_max": "15",
    "scrollexplorepage_duration_min": "30",
    "scrollexplorepage_duration_max": "120",
    # App cloner
    "app_cloner": "None",
}


# ===================================================================
#  INIT  — call once at startup
# ===================================================================

def init_db(db_path=None):
    """Create all tables if they don't exist. Safe to call repeatedly."""
    conn = get_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return db_path or DB_PATH


# ===================================================================
#  CONVENIENCE HELPERS
# ===================================================================

def insert_device(conn, device_serial, device_name="", status="disconnected"):
    """Insert or update a device."""
    now = datetime.datetime.now().isoformat()
    ip = device_serial.replace("_", ".").rsplit(".", 1)[0] if "_" in device_serial else ""
    conn.execute(
        """INSERT INTO devices (device_serial, device_name, ip_address, status, last_seen, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(device_serial) DO UPDATE SET
             device_name=excluded.device_name,
             status=excluded.status,
             last_seen=excluded.last_seen,
             updated_at=excluded.updated_at""",
        (device_serial, device_name, ip, status, now, now, now),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM devices WHERE device_serial=?", (device_serial,)
    ).fetchone()["id"]


def insert_account(conn, device_serial, username, password="", **kwargs):
    """Insert or update an account."""
    now = datetime.datetime.now().isoformat()
    # Resolve device_id
    row = conn.execute(
        "SELECT id FROM devices WHERE device_serial=?", (device_serial,)
    ).fetchone()
    device_id = row["id"] if row else None

    conn.execute(
        """INSERT INTO accounts
             (device_id, device_serial, username, password,
              email, instagram_package, two_fa_token, status,
              follow_enabled, unfollow_enabled, mute_enabled,
              like_enabled, comment_enabled, story_enabled, switchmode,
              start_time, end_time,
              follow_action, unfollow_action, random_action, random_delay,
              follow_delay, unfollow_delay, like_delay,
              follow_limit_perday, unfollow_limit_perday, like_limit_perday,
              unfollow_delay_day,
              created_at, updated_at)
           VALUES (?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?, ?,?, ?,?,?,?, ?,?,?, ?,?,?, ?, ?,?)
           ON CONFLICT(device_serial, username) DO UPDATE SET
             password=excluded.password,
             email=COALESCE(excluded.email, accounts.email),
             instagram_package=COALESCE(excluded.instagram_package, accounts.instagram_package),
             two_fa_token=COALESCE(excluded.two_fa_token, accounts.two_fa_token),
             follow_enabled=COALESCE(excluded.follow_enabled, accounts.follow_enabled),
             unfollow_enabled=COALESCE(excluded.unfollow_enabled, accounts.unfollow_enabled),
             mute_enabled=COALESCE(excluded.mute_enabled, accounts.mute_enabled),
             like_enabled=COALESCE(excluded.like_enabled, accounts.like_enabled),
             comment_enabled=COALESCE(excluded.comment_enabled, accounts.comment_enabled),
             story_enabled=COALESCE(excluded.story_enabled, accounts.story_enabled),
             switchmode=COALESCE(excluded.switchmode, accounts.switchmode),
             start_time=COALESCE(excluded.start_time, accounts.start_time),
             end_time=COALESCE(excluded.end_time, accounts.end_time),
             updated_at=excluded.updated_at""",
        (
            device_id, device_serial, username, password,
            kwargs.get("email", ""),
            kwargs.get("instagram_package", "com.instagram.android"),
            kwargs.get("two_fa_token", ""),
            kwargs.get("status", "active"),
            kwargs.get("follow_enabled", kwargs.get("follow", "False")),
            kwargs.get("unfollow_enabled", kwargs.get("unfollow", "False")),
            kwargs.get("mute_enabled", kwargs.get("mute", "False")),
            kwargs.get("like_enabled", kwargs.get("like", "False")),
            kwargs.get("comment_enabled", kwargs.get("comment", "False")),
            kwargs.get("story_enabled", kwargs.get("story", "False")),
            kwargs.get("switchmode", "False"),
            kwargs.get("start_time", kwargs.get("starttime", "0")),
            kwargs.get("end_time", kwargs.get("endtime", "0")),
            kwargs.get("follow_action", kwargs.get("followaction", "0")),
            kwargs.get("unfollow_action", kwargs.get("unfollowaction", "0")),
            kwargs.get("random_action", kwargs.get("randomaction", "30,60")),
            kwargs.get("random_delay", kwargs.get("randomdelay", "30,60")),
            kwargs.get("follow_delay", kwargs.get("followdelay", "30")),
            kwargs.get("unfollow_delay", kwargs.get("unfollowdelay", "30")),
            kwargs.get("like_delay", kwargs.get("likedelay", "0")),
            kwargs.get("follow_limit_perday", kwargs.get("followlimitperday", "0")),
            kwargs.get("unfollow_limit_perday", kwargs.get("unfollowlimitperday", "0")),
            kwargs.get("like_limit_perday", kwargs.get("likelimitperday", "0")),
            kwargs.get("unfollow_delay_day", kwargs.get("unfollowdelayday", "3")),
            now, now,
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM accounts WHERE device_serial=? AND username=?",
        (device_serial, username),
    ).fetchone()["id"]


def upsert_account_settings(conn, account_id, settings_dict):
    """Insert or update the JSON settings blob for an account."""
    now = datetime.datetime.now().isoformat()
    json_str = json.dumps(settings_dict)
    conn.execute(
        """INSERT INTO account_settings (account_id, settings_json, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(account_id) DO UPDATE SET
             settings_json=excluded.settings_json,
             updated_at=excluded.updated_at""",
        (account_id, json_str, now),
    )
    conn.commit()


def insert_stat(conn, account_id, date, followers="0", following="0", posts="0"):
    """Insert a daily stats snapshot."""
    conn.execute(
        """INSERT INTO account_stats (account_id, date, followers, following, posts)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(account_id, date) DO UPDATE SET
             followers=excluded.followers,
             following=excluded.following,
             posts=excluded.posts""",
        (account_id, date, followers, following, posts),
    )
    conn.commit()


# ===================================================================
#  QUICK SELF-TEST
# ===================================================================
if __name__ == "__main__":
    print(f"Initializing database at {DB_PATH}...")
    init_db()
    print("[OK] All tables created successfully.")

    # Quick sanity check
    conn = get_connection()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    print(f"[OK] Tables ({len(tables)}): {', '.join(tables)}")
    conn.close()
