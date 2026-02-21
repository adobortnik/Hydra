"""
Tag-Based Follow Deduplication
================================
Prevents multiple accounts sharing a tag from following the same target.

Architecture (v2 — scalable):
  - Dedicated `tag_followed_targets` table with UNIQUE(tag, target_username)
  - INSERT OR IGNORE on every successful follow → instant cross-device dedup
  - Loading the set = simple SELECT on small indexed table (not scanning action_history)
  - No race conditions: DB is the single source of truth, checked in real-time

Tags live in account_settings.settings_json as:
  - "tags": "chantall"           (string — can be comma-separated for multi-tag)
  - "enable_tags": true
  - "enable_dont_follow_sametag_accounts": true
"""

import json
import logging
import os
import sqlite3

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _get_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "db", "phone_farm.db",
    )


def _get_db():
    path = _get_db_path()
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_table():
    """Create the tag_followed_targets table if it doesn't exist."""
    conn = _get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tag_followed_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL,
                target_username TEXT NOT NULL,
                followed_by TEXT NOT NULL,
                device_serial TEXT,
                followed_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                UNIQUE(tag, target_username)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tft_tag ON tag_followed_targets(tag)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tft_target ON tag_followed_targets(target_username)
        """)
        conn.commit()
    except Exception as e:
        log.error("ensure_table failed: %s", e)
    finally:
        conn.close()


# Auto-create on import
ensure_table()


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _parse_tags(settings_json_str):
    """Extract the tag set from a settings_json string."""
    try:
        s = json.loads(settings_json_str) if isinstance(settings_json_str, str) else settings_json_str
    except (json.JSONDecodeError, TypeError):
        return set()
    raw = s.get("tags", "")
    if not raw:
        return set()
    return {t.strip().lower() for t in str(raw).split(",") if t.strip()}


def _get_account_tags(account_id):
    """Return tag set for an account."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return set()
        return _parse_tags(row["settings_json"])
    except Exception as e:
        log.error("_get_account_tags(%d): %s", account_id, e)
        return set()
    finally:
        conn.close()


def is_tag_dedup_enabled(account_id, db_path=None):
    """Check if tag-based follow dedup is enabled for *account_id*.

    Requires **both** ``enable_tags`` and ``enable_dont_follow_sametag_accounts``
    to be truthy, and the ``tags`` field to be non-empty.
    """
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return False
        s = json.loads(row["settings_json"])
        return (
            bool(s.get("enable_tags"))
            and bool(s.get("enable_dont_follow_sametag_accounts"))
            and bool(s.get("tags", "").strip())
        )
    except Exception as e:
        log.error("is_tag_dedup_enabled(%d): %s", account_id, e)
        return False
    finally:
        conn.close()


def get_account_tag_set(account_id):
    """Return the set of tag strings for *account_id* (lowercase, stripped)."""
    return _get_account_tags(account_id)


# ---------------------------------------------------------------------------
# Core API (v2 — uses tag_followed_targets table)
# ---------------------------------------------------------------------------

def get_same_tag_followed_set(account_id):
    """Return the full set of target_usernames already followed by any
    account with the same tag(s).

    Fast: single indexed query on tag_followed_targets table.
    Returns ``set[str]``.
    """
    tags = _get_account_tags(account_id)
    if not tags:
        return set()

    conn = _get_db()
    try:
        placeholders = ",".join("?" for _ in tags)
        rows = conn.execute(f"""
            SELECT DISTINCT target_username
            FROM tag_followed_targets
            WHERE tag IN ({placeholders})
        """, list(tags)).fetchall()
        return {r["target_username"] for r in rows}
    except Exception as e:
        log.error("get_same_tag_followed_set(%d): %s", account_id, e)
        return set()
    finally:
        conn.close()


def record_tag_follow(account_id, target_username, device_serial=None, username=None):
    """Record a successful follow in the tag dedup table.

    Called immediately after a successful follow action.
    INSERT OR IGNORE ensures no duplicates (UNIQUE on tag+target).
    Works across all devices instantly — no cache staleness.
    """
    tags = _get_account_tags(account_id)
    if not tags:
        return

    followed_by = username or str(account_id)
    conn = _get_db()
    try:
        for tag in tags:
            conn.execute("""
                INSERT OR IGNORE INTO tag_followed_targets
                    (tag, target_username, followed_by, device_serial)
                VALUES (?, ?, ?, ?)
            """, (tag, target_username, followed_by, device_serial))
        conn.commit()
    except Exception as e:
        log.error("record_tag_follow(%d, %s): %s", account_id, target_username, e)
    finally:
        conn.close()


def is_already_followed_by_tag(account_id, target_username):
    """Real-time check if target was already followed by any same-tag account.

    Use this for per-user checks instead of loading the full set.
    Fast: indexed lookup on (tag, target_username).
    """
    tags = _get_account_tags(account_id)
    if not tags:
        return False

    conn = _get_db()
    try:
        placeholders = ",".join("?" for _ in tags)
        row = conn.execute(f"""
            SELECT 1 FROM tag_followed_targets
            WHERE tag IN ({placeholders}) AND target_username = ?
            LIMIT 1
        """, list(tags) + [target_username]).fetchone()
        return row is not None
    except Exception as e:
        log.error("is_already_followed_by_tag(%d, %s): %s",
                  account_id, target_username, e)
        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migration: backfill from action_history
# ---------------------------------------------------------------------------

def migrate_from_action_history():
    """One-time migration: populate tag_followed_targets from existing
    action_history records.

    Safe to run multiple times (INSERT OR IGNORE).
    """
    conn = _get_db()
    try:
        # Get all accounts with tags
        accounts = conn.execute("""
            SELECT a.id, a.username, a.device_serial, ast.settings_json
            FROM accounts a
            JOIN account_settings ast ON ast.account_id = a.id
        """).fetchall()

        # Build tag -> [(username, device_serial)] mapping
        tag_accounts = {}
        for acct in accounts:
            tags = _parse_tags(acct["settings_json"])
            for tag in tags:
                if tag not in tag_accounts:
                    tag_accounts[tag] = []
                tag_accounts[tag].append({
                    "username": acct["username"],
                    "device_serial": acct["device_serial"],
                })

        total = 0
        for tag, accts in tag_accounts.items():
            # Get all follows by accounts with this tag
            clauses = []
            params = []
            for a in accts:
                clauses.append("(ah.device_serial = ? AND ah.username = ?)")
                params.extend([a["device_serial"], a["username"]])

            if not clauses:
                continue

            rows = conn.execute(f"""
                SELECT DISTINCT ah.target_username, ah.username, ah.device_serial
                FROM action_history ah
                WHERE ({" OR ".join(clauses)})
                  AND ah.action_type = 'follow'
                  AND ah.success = 1
                  AND ah.target_username IS NOT NULL
            """, params).fetchall()

            for r in rows:
                conn.execute("""
                    INSERT OR IGNORE INTO tag_followed_targets
                        (tag, target_username, followed_by, device_serial)
                    VALUES (?, ?, ?, ?)
                """, (tag, r["target_username"], r["username"], r["device_serial"]))
                total += 1

        conn.commit()
        log.info("Migration complete: inserted %d records into tag_followed_targets", total)
        return total
    except Exception as e:
        log.error("migrate_from_action_history failed: %s", e)
        return 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backward compatibility (old API — kept for any callers)
# ---------------------------------------------------------------------------

def get_same_tag_accounts(account_id):
    """Return list of account dicts that share any tag with account_id."""
    my_tags = get_account_tag_set(account_id)
    if not my_tags:
        return []

    conn = _get_db()
    try:
        rows = conn.execute("""
            SELECT a.id, a.username, a.device_serial, ast.settings_json
            FROM accounts a
            JOIN account_settings ast ON ast.account_id = a.id
            WHERE a.id != ?
        """, (account_id,)).fetchall()

        result = []
        for r in rows:
            their_tags = _parse_tags(r["settings_json"])
            if their_tags & my_tags:
                result.append({
                    "id": r["id"],
                    "username": r["username"],
                    "device_serial": r["device_serial"],
                    "tags": ",".join(sorted(their_tags & my_tags)),
                })
        return result
    except Exception as e:
        log.error("get_same_tag_accounts(%d): %s", account_id, e)
        return []
    finally:
        conn.close()


def has_same_tag_account_followed(account_id, target_username):
    """Check if ANY same-tag account already followed target_username.
    Now uses the fast indexed table instead of scanning action_history.
    """
    return is_already_followed_by_tag(account_id, target_username)
