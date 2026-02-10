"""Migration: Create follow_lists and follow_list_items tables."""
import sqlite3, sys

DB_PATH = r'C:\Users\TheLiveHouse\clawd\phone-farm\db\phone_farm.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS follow_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS follow_list_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id     INTEGER NOT NULL,
            username    TEXT    NOT NULL,
            added_at    TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (list_id) REFERENCES follow_lists(id) ON DELETE CASCADE,
            UNIQUE(list_id, username)
        )
    """)

    conn.commit()

    # Verify
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('follow_lists','follow_list_items')"
    ).fetchall()]
    assert 'follow_lists' in tables and 'follow_list_items' in tables, f"Missing tables! Got: {tables}"

    fl = conn.execute("SELECT COUNT(*) FROM follow_lists").fetchone()[0]
    fi = conn.execute("SELECT COUNT(*) FROM follow_list_items").fetchone()[0]
    print(f"OK: follow_lists ({fl} rows), follow_list_items ({fi} rows)")
    conn.close()

if __name__ == '__main__':
    migrate()
