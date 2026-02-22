"""
Migration: Create account_insights_v2 table
=============================================
New comprehensive schema for the insights scraper.
Keeps the old account_insights table intact (different schema).
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'phone_farm.db')

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS account_insights_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    device_serial TEXT,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_range TEXT,
    -- Overview
    views INTEGER,
    interactions INTEGER,
    new_followers INTEGER,
    content_shared INTEGER,
    -- Views detail
    accounts_reached INTEGER,
    accounts_reached_change_pct REAL,
    views_followers_pct REAL,
    views_non_followers_pct REAL,
    reels_views_pct REAL,
    posts_views_pct REAL,
    profile_visits INTEGER,
    profile_visits_change_pct REAL,
    external_link_taps INTEGER,
    comparison_period TEXT,
    -- Interactions detail
    interactions_followers_pct REAL,
    interactions_non_followers_pct REAL,
    likes_count INTEGER,
    reels_interactions_pct REAL,
    -- Followers detail
    total_followers INTEGER,
    demographics_available BOOLEAN DEFAULT 0,
    top_cities TEXT,
    top_countries TEXT,
    age_range TEXT,
    gender TEXT,
    most_active_times TEXT
);

CREATE INDEX IF NOT EXISTS idx_insights_v2_account ON account_insights_v2(account_id);
CREATE INDEX IF NOT EXISTS idx_insights_v2_date ON account_insights_v2(scraped_at);
"""

def run_migration():
    print(f"Running migration on: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    # Check if table already exists
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='account_insights_v2'"
    ).fetchone()
    
    if existing:
        print("Table account_insights_v2 already exists — skipping.")
    else:
        conn.executescript(MIGRATION_SQL)
        print("Created table: account_insights_v2")
        print("Created indexes: idx_insights_v2_account, idx_insights_v2_date")
    
    conn.close()
    print("Migration complete.")


if __name__ == '__main__':
    run_migration()
