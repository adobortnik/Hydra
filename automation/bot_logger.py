"""
Bot Logger — Structured logging for the Phone Farm automation engine.
=====================================================================

Provides:
- SQLite-backed log storage (bot_logs table)
- Custom logging handler that writes to DB
- Module-level API: log_bot_event(), get_recent_logs(), stream_logs()
- Thread-safe, WAL-mode compatible

Log entries include: timestamp, device, account, action, message, level, success/error.
"""

import logging
import threading
import sqlite3
import os
import time
import datetime
import json
from collections import deque

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "db", "phone_farm.db")
MAX_MEMORY_BUFFER = 500   # Keep last N logs in memory for fast polling
LOG_TABLE = "bot_logs"

# ---------------------------------------------------------------------------
# In-memory ring buffer for fast polling (no DB hit for recent logs)
# ---------------------------------------------------------------------------
_log_buffer = deque(maxlen=MAX_MEMORY_BUFFER)
_log_lock = threading.Lock()
_log_id_counter = 0

# ---------------------------------------------------------------------------
# DB Schema
# ---------------------------------------------------------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS bot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    level TEXT NOT NULL DEFAULT 'INFO',
    device_serial TEXT,
    username TEXT,
    action_type TEXT,
    message TEXT NOT NULL,
    success INTEGER,
    error_detail TEXT,
    module TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_bot_logs_timestamp ON bot_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_bot_logs_device ON bot_logs(device_serial);
CREATE INDEX IF NOT EXISTS idx_bot_logs_level ON bot_logs(level);
"""


def init_log_table():
    """Create the bot_logs table if it doesn't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(CREATE_TABLE_SQL + CREATE_INDEX_SQL)
        conn.commit()
        conn.close()
        log.info("bot_logs table initialized")
    except Exception as e:
        log.error("Failed to init bot_logs table: %s", e)


# Initialize on import
init_log_table()


# ---------------------------------------------------------------------------
# Core logging function
# ---------------------------------------------------------------------------
def log_bot_event(message, level="INFO", device_serial=None, username=None,
                  action_type=None, success=None, error_detail=None, module=None):
    """
    Log a structured bot event to both DB and memory buffer.

    Args:
        message: Human-readable log message
        level: INFO, WARNING, ERROR, DEBUG
        device_serial: Device this log relates to
        username: Instagram account username
        action_type: Action type (follow, unfollow, like, engage, reels, etc.)
        success: True/False/None
        error_detail: Error traceback or detail string
        module: Source module name (bot_engine, orchestrator, follow, etc.)
    """
    global _log_id_counter

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    entry = {
        "timestamp": timestamp,
        "level": level,
        "device_serial": device_serial,
        "username": username,
        "action_type": action_type,
        "message": message,
        "success": success,
        "error_detail": error_detail,
        "module": module,
    }

    # Add to memory buffer (fast path)
    with _log_lock:
        _log_id_counter += 1
        entry["id"] = _log_id_counter
        _log_buffer.append(entry)

    # Write to DB (async via thread to avoid blocking)
    def _write_db():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute(
                """INSERT INTO bot_logs
                   (timestamp, level, device_serial, username, action_type,
                    message, success, error_detail, module, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (timestamp, level, device_serial, username, action_type,
                 message, 1 if success is True else (0 if success is False else None),
                 error_detail, module, timestamp)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            # Don't recurse - just print
            print(f"[bot_logger] DB write error: {e}")

    threading.Thread(target=_write_db, daemon=True).start()


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------
def get_recent_logs(limit=100, since_id=None, device_serial=None,
                    level=None, username=None):
    """
    Get recent log entries.

    Args:
        limit: Max entries to return
        since_id: Return only entries with id > since_id (for polling)
        device_serial: Filter by device
        level: Filter by level (INFO, WARNING, ERROR)
        username: Filter by username

    Returns: list of log entry dicts
    """
    # Fast path: use memory buffer if no DB-specific filters needed
    if since_id is not None:
        with _log_lock:
            entries = [e for e in _log_buffer if e["id"] > since_id]
            if device_serial:
                entries = [e for e in entries if e.get("device_serial") == device_serial]
            if level:
                entries = [e for e in entries if e.get("level") == level]
            if username:
                entries = [e for e in entries if e.get("username") == username]
            return entries[:limit]

    # Memory buffer query (most recent first)
    with _log_lock:
        entries = list(reversed(_log_buffer))
        if device_serial:
            entries = [e for e in entries if e.get("device_serial") == device_serial]
        if level:
            entries = [e for e in entries if e.get("level") == level]
        if username:
            entries = [e for e in entries if e.get("username") == username]
        return entries[:limit]


def get_logs_from_db(limit=200, offset=0, device_serial=None,
                     level=None, username=None, since=None):
    """
    Get logs from DB (for historical queries).
    """
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM bot_logs WHERE 1=1"
        params = []

        if device_serial:
            query += " AND device_serial=?"
            params.append(device_serial)
        if level:
            query += " AND level=?"
            params.append(level)
        if username:
            query += " AND username=?"
            params.append(username)
        if since:
            query += " AND timestamp >= ?"
            params.append(since)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        conn.close()

        return [dict(r) for r in rows]
    except Exception as e:
        log.error("get_logs_from_db error: %s", e)
        return []


def get_log_stats():
    """Get log statistics for the dashboard."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row

        today = datetime.date.today().isoformat()

        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_logs WHERE timestamp >= ?", (today,)
        ).fetchone()["cnt"]

        errors = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_logs WHERE timestamp >= ? AND level='ERROR'",
            (today,)
        ).fetchone()["cnt"]

        warnings = conn.execute(
            "SELECT COUNT(*) as cnt FROM bot_logs WHERE timestamp >= ? AND level='WARNING'",
            (today,)
        ).fetchone()["cnt"]

        conn.close()

        return {
            "total_today": total,
            "errors_today": errors,
            "warnings_today": warnings,
        }
    except Exception:
        return {"total_today": 0, "errors_today": 0, "warnings_today": 0}


# ---------------------------------------------------------------------------
# Custom logging handler — intercepts Python logging calls
# ---------------------------------------------------------------------------
class BotLogHandler(logging.Handler):
    """
    A logging.Handler that captures automation module logs and stores them
    via log_bot_event(). Attach to the 'automation' logger namespace.
    """

    def __init__(self):
        super().__init__()
        self.setLevel(logging.INFO)

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname

            # Try to extract device_serial from the log message
            # Convention: "[device_serial] message" or "[device_serial] username: message"
            device_serial = None
            username = None
            clean_msg = msg

            if msg.startswith("[") and "]" in msg:
                bracket_end = msg.index("]")
                device_serial = msg[1:bracket_end]
                clean_msg = msg[bracket_end + 1:].strip()

                # Try to extract username (pattern: "username: rest of message")
                if ": " in clean_msg:
                    potential_user = clean_msg.split(":")[0].strip()
                    # Username is typically short, no spaces
                    if potential_user and len(potential_user) < 40 and " " not in potential_user:
                        username = potential_user

            # Determine module from logger name
            module = record.name
            if "." in module:
                module = module.rsplit(".", 1)[-1]

            log_bot_event(
                message=clean_msg,
                level=level,
                device_serial=device_serial,
                username=username,
                module=module,
            )
        except Exception:
            pass  # Never let logging fail silently crash


def setup_bot_logging():
    """
    Install the BotLogHandler on the 'automation' parent logger ONLY.
    Child loggers (automation.bot_engine, etc.) propagate up by default,
    so one handler on the parent catches everything. No duplicates.
    """
    handler = BotLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Only attach to the parent 'automation' logger
    parent = logging.getLogger("automation")
    # Remove any existing BotLogHandlers first
    parent.handlers = [h for h in parent.handlers if not isinstance(h, BotLogHandler)]
    parent.addHandler(handler)

    log.info("Bot structured logging initialized")
