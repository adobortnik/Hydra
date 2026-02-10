#!/usr/bin/env python3
"""
Proxy Tables Migration
=======================
Adds proxy management tables to phone_farm.db.

Tables:
  - proxies               Proxy server pool
  - device_proxy_history  Audit log of proxy assignments

Safe to run multiple times (CREATE TABLE IF NOT EXISTS).
"""

import os
import sys
import sqlite3

# Reuse the central DB path
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "phone_farm.db")

PROXY_SCHEMA_SQL = """
-- ---------------------------------------------------------------
-- PROXIES  (proxy server pool)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proxies (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    host                  TEXT    NOT NULL,
    port                  INTEGER NOT NULL,
    proxy_type            TEXT    DEFAULT 'HTTP',          -- HTTP, SOCKS5, SOCKS4, HTTPS
    username              TEXT,
    password              TEXT,
    label                 TEXT,                            -- friendly name: "US Proxy 1"
    status                TEXT    DEFAULT 'available',     -- available, in_use, dead, checking
    assigned_device_serial TEXT,                           -- which device is currently using it
    last_checked          TEXT,                            -- ISO timestamp of last health check
    last_working          TEXT,                            -- ISO timestamp of last successful check
    check_latency_ms      INTEGER,                        -- latency in ms from last check
    country               TEXT,                            -- geo label: US, DE, etc.
    notes                 TEXT,
    created_at            TEXT    DEFAULT (datetime('now')),
    updated_at            TEXT    DEFAULT (datetime('now')),
    UNIQUE(host, port)
);

-- ---------------------------------------------------------------
-- DEVICE PROXY HISTORY  (audit log)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_proxy_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_serial   TEXT    NOT NULL,
    proxy_id        INTEGER,
    proxy_host      TEXT,
    proxy_port      INTEGER,
    action          TEXT    NOT NULL,   -- assigned, removed, failed, toggled_on, toggled_off
    details         TEXT,              -- extra context / error message
    timestamp       TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (proxy_id) REFERENCES proxies(id)
);

-- ---------------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_proxies_status         ON proxies(status);
CREATE INDEX IF NOT EXISTS idx_proxies_assigned       ON proxies(assigned_device_serial);
CREATE INDEX IF NOT EXISTS idx_proxy_history_device   ON device_proxy_history(device_serial, timestamp);
CREATE INDEX IF NOT EXISTS idx_proxy_history_proxy    ON device_proxy_history(proxy_id);
"""


def init_proxy_tables(db_path=None):
    """Create proxy tables if they don't exist. Safe to call repeatedly."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(PROXY_SCHEMA_SQL)
    conn.commit()
    conn.close()
    print(f"[OK] Proxy tables initialized in {path}")
    return path


if __name__ == "__main__":
    print(f"Initializing proxy tables in {DB_PATH}...")
    init_proxy_tables()
    
    # Verify
    conn = sqlite3.connect(DB_PATH)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%prox%'"
    ).fetchall()]
    print(f"[OK] Proxy tables: {', '.join(tables)}")
    
    # Count existing rows
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"     {table}: {count} rows")
    conn.close()
