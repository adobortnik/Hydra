"""
Tag-Based Follow Deduplication
================================
Prevents multiple accounts sharing a tag from following the same target.

Tags live in account_settings.settings_json as:
  - "tags": "chantall"           (string — can be comma-separated for multi-tag)
  - "enable_tags": true
  - "enable_dont_follow_sametag_accounts": true

action_history stores follow records as:
  (device_serial, username, action_type='follow', target_username, success=1)

The join path is:  action_history.(device_serial, username) → accounts → account_settings → tags string.
"""

import json
import logging
import os
import sqlite3

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB (same pattern as actions/helpers.py)
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


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _parse_tags(settings_json_str):
    """Extract the tag set from a settings_json string.

    Returns a set of lowercase, stripped tag names (possibly empty).
    """
    try:
        s = json.loads(settings_json_str) if isinstance(settings_json_str, str) else settings_json_str
    except (json.JSONDecodeError, TypeError):
        return set()
    raw = s.get("tags", "")
    if not raw:
        return set()
    return {t.strip().lower() for t in str(raw).split(",") if t.strip()}


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
        log.error("get_account_tag_set(%d): %s", account_id, e)
        return set()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Core queries
# ---------------------------------------------------------------------------

def get_same_tag_accounts(account_id):
    """Return list of account dicts that share **any** tag with *account_id*.

    Each dict has keys: ``id``, ``username``, ``device_serial``, ``tags``.
    The calling account is **excluded** from the result.
    """
    my_tags = get_account_tag_set(account_id)
    if not my_tags:
        return []

    conn = _get_db()
    try:
        # Grab all accounts that have enable_tags set
        # (cheaper than loading every row — tags field is inside JSON so we
        # can't SQL-filter directly; we do a Python-side intersection.)
        rows = conn.execute("""
            SELECT a.id, a.username, a.device_serial, ast.settings_json
            FROM accounts a
            JOIN account_settings ast ON ast.account_id = a.id
            WHERE a.id != ?
        """, (account_id,)).fetchall()

        result = []
        for r in rows:
            their_tags = _parse_tags(r["settings_json"])
            if their_tags & my_tags:                       # intersection
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
    """Check if ANY account sharing a tag with *account_id* has already
    successfully followed *target_username*.

    Fast path: builds the set of (device_serial, username) pairs for same-tag
    accounts, then does a single EXISTS query against action_history.

    Returns True / False.
    """
    peers = get_same_tag_accounts(account_id)
    if not peers:
        return False

    conn = _get_db()
    try:
        # Build a WHERE clause with OR-ed pairs.
        # For 600 accounts this is still fine — SQLite handles it easily.
        clauses = []
        params = []
        for p in peers:
            clauses.append("(ah.device_serial = ? AND ah.username = ?)")
            params.extend([p["device_serial"], p["username"]])

        params.append(target_username)

        sql = f"""
            SELECT 1 FROM action_history ah
            WHERE ({" OR ".join(clauses)})
              AND ah.action_type = 'follow'
              AND ah.target_username = ?
              AND ah.success = 1
            LIMIT 1
        """
        row = conn.execute(sql, params).fetchone()
        return row is not None
    except Exception as e:
        log.error("has_same_tag_account_followed(%d, %s): %s",
                  account_id, target_username, e)
        return False
    finally:
        conn.close()


def get_same_tag_followed_set(account_id):
    """Return the full set of target_usernames already followed by any
    same-tag peer.  Useful for bulk pre-loading before a follow session
    (avoids per-user DB round-trips).

    Returns ``set[str]``.
    """
    peers = get_same_tag_accounts(account_id)
    if not peers:
        return set()

    conn = _get_db()
    try:
        clauses = []
        params = []
        for p in peers:
            clauses.append("(ah.device_serial = ? AND ah.username = ?)")
            params.extend([p["device_serial"], p["username"]])

        sql = f"""
            SELECT DISTINCT ah.target_username FROM action_history ah
            WHERE ({" OR ".join(clauses)})
              AND ah.action_type = 'follow'
              AND ah.success = 1
              AND ah.target_username IS NOT NULL
        """
        rows = conn.execute(sql, params).fetchall()
        return {r["target_username"] for r in rows}
    except Exception as e:
        log.error("get_same_tag_followed_set(%d): %s", account_id, e)
        return set()
    finally:
        conn.close()
