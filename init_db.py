"""
Hydra Database Initialization Script
=====================================
Creates all 42 tables in phone_farm.db from scratch.
Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS.

Usage:
    python init_db.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass

import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db')
DB_PATH = os.path.join(DB_DIR, 'phone_farm.db')

os.makedirs(DB_DIR, exist_ok=True)

# Delete empty/corrupt DB file
if os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) == 0:
    os.remove(DB_PATH)
    print(f"Removed empty DB file: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")

SCHEMA = """
-- ═══════════════════════════════════════════
-- HYDRA — Phone Farm Database Schema
-- 42 tables, auto-generated from production DB
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL UNIQUE,
    device_name     TEXT,
    ip_address      TEXT,
    adb_port        INTEGER DEFAULT 5555,
    status          TEXT    DEFAULT 'disconnected',
    last_seen       TEXT,
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER,
    device_serial   TEXT,
    username        TEXT    NOT NULL,
    password        TEXT,
    email           TEXT,
    instagram_package TEXT  DEFAULT 'com.instagram.android',
    two_fa_token    TEXT,
    status          TEXT    DEFAULT 'active',
    follow_enabled      TEXT DEFAULT 'False',
    unfollow_enabled    TEXT DEFAULT 'False',
    mute_enabled        TEXT DEFAULT 'False',
    like_enabled        TEXT DEFAULT 'False',
    comment_enabled     TEXT DEFAULT 'False',
    story_enabled       TEXT DEFAULT 'False',
    switchmode          TEXT DEFAULT 'False',
    start_time      TEXT    DEFAULT '0',
    end_time        TEXT    DEFAULT '0',
    follow_action   TEXT    DEFAULT '0',
    unfollow_action TEXT    DEFAULT '0',
    random_action   TEXT    DEFAULT '30,60',
    random_delay    TEXT    DEFAULT '30,60',
    follow_delay    TEXT    DEFAULT '30',
    unfollow_delay  TEXT    DEFAULT '30',
    like_delay      TEXT    DEFAULT '0',
    follow_limit_perday     TEXT DEFAULT '0',
    unfollow_limit_perday   TEXT DEFAULT '0',
    like_limit_perday       TEXT DEFAULT '0',
    unfollow_delay_day      TEXT DEFAULT '3',
    warmup          INTEGER DEFAULT 0,
    warmup_until    TEXT    DEFAULT NULL,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (device_id) REFERENCES devices(id),
    UNIQUE(device_serial, username)
);

CREATE TABLE IF NOT EXISTS account_settings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL UNIQUE,
    settings_json   TEXT    NOT NULL DEFAULT '{}',
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS account_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    source_type     TEXT    NOT NULL,
    value           TEXT    NOT NULL,
    created_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS account_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    date            TEXT    NOT NULL,
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

CREATE TABLE IF NOT EXISTS account_health_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id              INTEGER NOT NULL,
    device_serial           TEXT,
    username                TEXT,
    event_type              TEXT    NOT NULL,
    details                 TEXT,
    detected_at             TEXT    DEFAULT (datetime('now')),
    resolved_at             TEXT,
    resolved_by             TEXT,
    replacement_account_id  INTEGER,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS account_inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL,
    password        TEXT    NOT NULL,
    two_factor_auth TEXT,
    status          TEXT    DEFAULT 'available',
    device_assigned TEXT,
    date_added      TEXT,
    date_used       TEXT,
    notes           TEXT,
    appid           TEXT    DEFAULT 'com.instagram.android',
    email           TEXT,
    phone           TEXT,
    assigned_to_device_serial TEXT,
    assigned_to_account_id INTEGER,
    warmup_stage    TEXT,
    assigned_at     TEXT
);

CREATE TABLE IF NOT EXISTS account_text_configs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER NOT NULL,
    config_type     TEXT    NOT NULL,
    content         TEXT    NOT NULL DEFAULT '',
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE(account_id, config_type)
);

CREATE TABLE IF NOT EXISTS tags (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    UNIQUE
);

CREATE TABLE IF NOT EXISTS account_tags (
    account_id INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL,
    PRIMARY KEY (account_id, tag_id),
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (tag_id)     REFERENCES tags(id)
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

CREATE TABLE IF NOT EXISTS dead_sources (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_username    TEXT    NOT NULL,
    source_username     TEXT    NOT NULL,
    fail_count          INTEGER DEFAULT 1,
    first_failed_at     TEXT    NOT NULL,
    last_failed_at      TEXT    NOT NULL,
    status              TEXT    DEFAULT 'suspect',
    UNIQUE(account_username, source_username)
);

CREATE TABLE IF NOT EXISTS follow_lists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS follow_list_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id     INTEGER NOT NULL,
    username    TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    followed_by_account_id INTEGER,
    followed_at TEXT,
    skip_reason TEXT,
    FOREIGN KEY (list_id) REFERENCES follow_lists(id) ON DELETE CASCADE,
    UNIQUE(list_id, username)
);

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

CREATE TABLE IF NOT EXISTS bot_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    level       TEXT NOT NULL DEFAULT 'INFO',
    device_serial TEXT,
    username    TEXT,
    action_type TEXT,
    message     TEXT NOT NULL,
    success     INTEGER,
    error_detail TEXT,
    module      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS job_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,
    job_type        TEXT NOT NULL,
    target          TEXT NOT NULL,
    target_count    INTEGER DEFAULT 0,
    completed_count INTEGER DEFAULT 0,
    limit_per_hour  INTEGER DEFAULT 50,
    limit_per_day   INTEGER DEFAULT 200,
    comment_text    TEXT,
    status          TEXT DEFAULT 'active',
    priority        INTEGER DEFAULT 0,
    report_reason   TEXT DEFAULT 'nudity',
    comment_list_id INTEGER,
    ai_mode         INTEGER DEFAULT 0,
    vision_ai       INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS job_assignments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL,
    account_id      INTEGER NOT NULL,
    device_serial   TEXT NOT NULL,
    username        TEXT NOT NULL,
    status          TEXT DEFAULT 'assigned',
    completed_count INTEGER DEFAULT 0,
    last_action_at  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    UNIQUE(job_id, account_id)
);

CREATE TABLE IF NOT EXISTS job_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER NOT NULL,
    account_id      INTEGER NOT NULL,
    action_type     TEXT NOT NULL,
    target          TEXT,
    status          TEXT DEFAULT 'success',
    error_message   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (job_id) REFERENCES job_orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comment_lists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    comments_json   TEXT NOT NULL DEFAULT '[]',
    ai_enabled      INTEGER DEFAULT 0,
    ai_style        TEXT,
    ai_sample_count INTEGER DEFAULT 10,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS content_schedule (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER,
    device_serial   TEXT,
    username        TEXT,
    content_type    TEXT NOT NULL,
    media_path      TEXT,
    caption         TEXT,
    hashtags        TEXT,
    location        TEXT,
    music_name      TEXT,
    music_search_query TEXT,
    mention_username TEXT,
    link_url        TEXT,
    scheduled_time  DATETIME NOT NULL,
    status          TEXT DEFAULT 'pending',
    posted_at       DATETIME,
    error_message   TEXT,
    batch_id        TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_batches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        TEXT UNIQUE NOT NULL,
    name            TEXT,
    content_type    TEXT,
    total_items     INTEGER DEFAULT 0,
    completed_items INTEGER DEFAULT 0,
    failed_items    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_categories (
    id              TEXT    PRIMARY KEY,
    name            TEXT    NOT NULL,
    posting_frequency TEXT,
    hashtags        TEXT,
    caption_template TEXT,
    created_at      TEXT,
    last_used       TEXT
);

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

CREATE TABLE IF NOT EXISTS scheduled_posts (
    id              TEXT    PRIMARY KEY,
    deviceid        TEXT    NOT NULL,
    account         TEXT    NOT NULL,
    post_type       TEXT    NOT NULL,
    caption         TEXT,
    media_path      TEXT,
    location        TEXT,
    scheduled_time  TEXT    NOT NULL,
    status          TEXT    DEFAULT 'scheduled',
    created_at      TEXT,
    updated_at      TEXT
);

CREATE TABLE IF NOT EXISTS media (
    id              TEXT    PRIMARY KEY,
    filename        TEXT    NOT NULL,
    original_path   TEXT    NOT NULL,
    processed_path  TEXT,
    media_type      TEXT    NOT NULL,
    file_size       INTEGER,
    width           INTEGER,
    height          INTEGER,
    duration        INTEGER,
    tags            TEXT,
    description     TEXT,
    upload_date     TEXT,
    times_used      INTEGER DEFAULT 0,
    last_used       TEXT
);

CREATE TABLE IF NOT EXISTS folders (
    id              TEXT    PRIMARY KEY,
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

CREATE TABLE IF NOT EXISTS media_tags (
    media_id        TEXT,
    tag_id          INTEGER,
    PRIMARY KEY (media_id, tag_id),
    FOREIGN KEY (media_id)  REFERENCES media(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)    REFERENCES tags(id)  ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS proxies (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    host                  TEXT    NOT NULL,
    port                  INTEGER NOT NULL,
    proxy_type            TEXT    DEFAULT 'HTTP',
    username              TEXT,
    password              TEXT,
    label                 TEXT,
    status                TEXT    DEFAULT 'available',
    assigned_device_serial TEXT,
    last_checked          TEXT,
    last_working          TEXT,
    check_latency_ms      INTEGER,
    country               TEXT,
    notes                 TEXT,
    created_at            TEXT    DEFAULT (datetime('now')),
    updated_at            TEXT    DEFAULT (datetime('now')),
    UNIQUE(host, port)
);

CREATE TABLE IF NOT EXISTS device_proxy_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    proxy_id        INTEGER,
    proxy_host      TEXT,
    proxy_port      INTEGER,
    action          TEXT    NOT NULL,
    details         TEXT,
    timestamp       TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (proxy_id) REFERENCES proxies(id)
);

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

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      INTEGER,
    device_serial   TEXT,
    task_type       TEXT    NOT NULL,
    status          TEXT    DEFAULT 'pending',
    priority        INTEGER DEFAULT 0,
    scheduled_time  TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    params_json     TEXT    DEFAULT '{}',
    result_json     TEXT,
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    created_at      TEXT    DEFAULT (datetime('now')),
    updated_at      TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS task_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER,
    account_id      INTEGER,
    device_serial   TEXT,
    task_type       TEXT    NOT NULL,
    status          TEXT    NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    duration_sec    REAL,
    params_json     TEXT,
    result_json     TEXT,
    error_message   TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
);

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
"""

print("Initializing Hydra database...")
print(f"DB path: {DB_PATH}")
conn.executescript(SCHEMA)
conn.commit()

# Verify
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
).fetchall()]
print(f"\nCreated {len(tables)} tables:")
for t in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t} ({count} rows)")

conn.close()
print(f"\nDatabase ready at: {DB_PATH}")
