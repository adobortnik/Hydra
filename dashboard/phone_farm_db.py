"""
phone_farm_db.py - Shared DB access layer for phone_farm.db

Single source of truth for all device/account operations.
All new blueprints should use this module instead of direct DB access.
"""

import sqlite3
import os
from datetime import datetime

# Path to the central database
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db', 'phone_farm.db')

CLONE_LETTERS = list('efghijklmnop')  # 12 clone slots per device


def get_conn():
    """Get a connection to phone_farm.db with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else None


def rows_to_dicts(rows):
    """Convert a list of sqlite3.Row to list of dicts."""
    return [dict(r) for r in rows] if rows else []


# ─────────────────────────────────────────────
# DEVICE operations
# ─────────────────────────────────────────────

def get_all_devices():
    """Get all devices with account counts."""
    conn = get_conn()
    try:
        devices = rows_to_dicts(conn.execute("""
            SELECT d.*,
                   COUNT(a.id) as account_count
            FROM devices d
            LEFT JOIN accounts a ON a.device_id = d.id
            GROUP BY d.id
            ORDER BY d.device_serial
        """).fetchall())
        return devices
    finally:
        conn.close()


def get_device_by_id(device_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_device_by_serial(serial):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM devices WHERE device_serial = ?", (serial,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def add_device(device_serial, device_name=None, ip_address=None, adb_port=5555, notes=None):
    """Add a new device. Returns the new device dict or raises on duplicate."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        if not ip_address:
            ip_address = device_serial.replace('_', ':').split(':')[0] if '_' in device_serial else device_serial
        if not device_name:
            device_name = ip_address

        conn.execute("""
            INSERT INTO devices (device_serial, device_name, ip_address, adb_port, status, last_seen, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'disconnected', ?, ?, ?, ?)
        """, (device_serial, device_name, ip_address, adb_port, now, notes, now, now))
        conn.commit()
        return get_device_by_serial(device_serial)
    finally:
        conn.close()


def update_device(device_id, **kwargs):
    """Update device fields. Pass only the fields you want to change."""
    allowed = {'device_name', 'ip_address', 'adb_port', 'status', 'last_seen', 'notes'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.utcnow().isoformat()

    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [device_id]

    conn = get_conn()
    try:
        conn.execute(f"UPDATE devices SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return True
    finally:
        conn.close()


def update_device_status(device_serial, status, last_seen=None):
    """Quick status update by serial."""
    conn = get_conn()
    try:
        now = last_seen or datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE devices SET status = ?, last_seen = ?, updated_at = ? WHERE device_serial = ?",
            (status, now, now, device_serial)
        )
        conn.commit()
    finally:
        conn.close()


def delete_device(device_id):
    """Delete a device only if it has no accounts assigned."""
    conn = get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM accounts WHERE device_id = ?", (device_id,)).fetchone()[0]
        if count > 0:
            return False, f"Cannot delete: {count} accounts still assigned to this device"
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
        return True, "Device deleted"
    finally:
        conn.close()


# ─────────────────────────────────────────────
# ACCOUNT operations
# ─────────────────────────────────────────────

def get_all_accounts(status_filter=None, device_serial=None):
    """Get accounts with optional filters."""
    conn = get_conn()
    try:
        query = """
            SELECT a.*, d.device_name
            FROM accounts a
            LEFT JOIN devices d ON d.id = a.device_id
            WHERE 1=1
        """
        params = []
        if status_filter:
            if isinstance(status_filter, list):
                placeholders = ','.join('?' * len(status_filter))
                query += f" AND a.status IN ({placeholders})"
                params.extend(status_filter)
            else:
                query += " AND a.status = ?"
                params.append(status_filter)
        if device_serial:
            query += " AND a.device_serial = ?"
            params.append(device_serial)
        query += " ORDER BY a.device_serial, a.username"
        return rows_to_dicts(conn.execute(query, params).fetchall())
    finally:
        conn.close()


def get_accounts_for_device(device_serial):
    """Get all accounts on a specific device."""
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            "SELECT * FROM accounts WHERE device_serial = ? ORDER BY username",
            (device_serial,)
        ).fetchall())
    finally:
        conn.close()


def get_account_by_id(account_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_used_clone_letters(device_serial):
    """Return set of clone letters already in use on a device."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT instagram_package FROM accounts WHERE device_serial = ?",
            (device_serial,)
        ).fetchall()
        used = set()
        for r in rows:
            pkg = r['instagram_package'] or ''
            # Package like com.instagram.androie → letter 'e'
            if pkg.startswith('com.instagram.androi') and len(pkg) == 21:
                used.add(pkg[-1])
        return used
    finally:
        conn.close()


def get_available_clone_letters(device_serial):
    """Return list of clone letters still available on a device."""
    used = get_used_clone_letters(device_serial)
    return [l for l in CLONE_LETTERS if l not in used]


def make_package_name(letter):
    """Build the full instagram_package from a clone letter (package/activity)."""
    return f"com.instagram.androi{letter}/com.instagram.mainactivity.MainActivity"


def make_app_id(letter):
    """Build the full appId string (package/activity) used in Onimator."""
    return f"com.instagram.androi{letter}/com.instagram.mainactivity.MainActivity"


def add_account(device_serial, username, password, two_fa_token=None,
                instagram_package=None, status='pending_login', **extra):
    """
    Add a single account to phone_farm.db.
    Auto-links to device_id if device_serial exists.
    Returns new account dict or raises.
    """
    conn = get_conn()
    try:
        # Look up device
        dev = conn.execute("SELECT id FROM devices WHERE device_serial = ?", (device_serial,)).fetchone()
        device_id = dev['id'] if dev else None

        now = datetime.utcnow().isoformat()
        pkg = instagram_package or 'com.instagram.android'

        # Collect extra columns
        start_time = extra.get('start_time', '0')
        end_time = extra.get('end_time', '0')
        follow_enabled = extra.get('follow_enabled', 'False')
        unfollow_enabled = extra.get('unfollow_enabled', 'False')
        like_enabled = extra.get('like_enabled', 'False')
        story_enabled = extra.get('story_enabled', 'False')
        comment_enabled = extra.get('comment_enabled', 'False')
        mute_enabled = extra.get('mute_enabled', 'False')
        warmup = extra.get('warmup', 0)
        warmup_until = extra.get('warmup_until', None)

        conn.execute("""
            INSERT INTO accounts
                (device_id, device_serial, username, password, two_fa_token,
                 instagram_package, status,
                 follow_enabled, unfollow_enabled, like_enabled,
                 story_enabled, comment_enabled, mute_enabled,
                 start_time, end_time, warmup, warmup_until,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (device_id, device_serial, username, password, two_fa_token,
              pkg, status,
              follow_enabled, unfollow_enabled, like_enabled,
              story_enabled, comment_enabled, mute_enabled,
              start_time, end_time, warmup, warmup_until, now, now))
        conn.commit()

        # Get the inserted account
        row = conn.execute(
            "SELECT * FROM accounts WHERE device_serial = ? AND username = ?",
            (device_serial, username)
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def update_account(account_id, **kwargs):
    """Update account fields by id."""
    allowed = {
        'device_id', 'device_serial', 'username', 'password', 'email',
        'instagram_package', 'two_fa_token', 'status',
        'follow_enabled', 'unfollow_enabled', 'mute_enabled',
        'like_enabled', 'comment_enabled', 'story_enabled', 'switchmode',
        'start_time', 'end_time',
        'follow_action', 'unfollow_action', 'random_action', 'random_delay',
        'follow_delay', 'unfollow_delay', 'like_delay',
        'follow_limit_perday', 'unfollow_limit_perday', 'like_limit_perday',
        'unfollow_delay_day',
        'warmup', 'warmup_until',
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.utcnow().isoformat()

    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [account_id]

    conn = get_conn()
    try:
        conn.execute(f"UPDATE accounts SET {set_clause} WHERE id = ?", values)
        conn.commit()
        return True
    finally:
        conn.close()


def update_account_status(account_id, status, notes=None):
    """Quick status update for an account."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE accounts SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, account_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def bulk_update_status(account_ids, status):
    """Update status for multiple accounts."""
    if not account_ids:
        return 0
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        placeholders = ','.join('?' * len(account_ids))
        conn.execute(
            f"UPDATE accounts SET status = ?, updated_at = ? WHERE id IN ({placeholders})",
            [status, now] + list(account_ids)
        )
        conn.commit()
        return len(account_ids)
    finally:
        conn.close()


# ─────────────────────────────────────────────
# ACCOUNT SETTINGS (JSON blob)
# ─────────────────────────────────────────────

def get_account_settings(account_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT settings_json FROM account_settings WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        if row:
            import json
            return json.loads(row['settings_json'])
        return {}
    finally:
        conn.close()


def upsert_account_settings(account_id, settings_dict):
    import json
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        json_str = json.dumps(settings_dict)
        conn.execute("""
            INSERT INTO account_settings (account_id, settings_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET settings_json = ?, updated_at = ?
        """, (account_id, json_str, now, json_str, now))
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────
# TASKS
# ─────────────────────────────────────────────

def create_task(account_id, device_serial, task_type, params_json='{}', priority=0):
    """Create a new task in the tasks table."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        cursor = conn.execute("""
            INSERT INTO tasks (account_id, device_serial, task_type, status, priority, params_json, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
        """, (account_id, device_serial, task_type, priority, params_json, now, now))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_pending_tasks(task_type=None):
    conn = get_conn()
    try:
        if task_type:
            return rows_to_dicts(conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND task_type = ? ORDER BY priority DESC, created_at",
                (task_type,)
            ).fetchall())
        return rows_to_dicts(conn.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at"
        ).fetchall())
    finally:
        conn.close()


def update_task(task_id, **kwargs):
    allowed = {'status', 'started_at', 'completed_at', 'result_json', 'error_message', 'retry_count'}
    # Also allow result_json via result_json
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields['updated_at'] = datetime.utcnow().isoformat()
    set_clause = ', '.join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]
    conn = get_conn()
    try:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def get_tasks_by_type_and_status(task_type, statuses):
    """Get tasks filtered by type and list of statuses."""
    conn = get_conn()
    try:
        placeholders = ','.join('?' * len(statuses))
        return rows_to_dicts(conn.execute(
            f"SELECT t.*, a.username, a.instagram_package, a.password, a.two_fa_token, d.device_name "
            f"FROM tasks t "
            f"LEFT JOIN accounts a ON a.id = t.account_id "
            f"LEFT JOIN devices d ON d.device_serial = t.device_serial "
            f"WHERE t.task_type = ? AND t.status IN ({placeholders}) "
            f"ORDER BY t.priority DESC, t.created_at",
            [task_type] + list(statuses)
        ).fetchall())
    finally:
        conn.close()


# ─────────────────────────────────────────────
# WARMUP helpers
# ─────────────────────────────────────────────

def set_warmup(account_id, warmup_until):
    """Enable warmup mode for an account until a given date (YYYY-MM-DD)."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE accounts SET warmup = 1, warmup_until = ?, updated_at = ? WHERE id = ?",
            (warmup_until, now, account_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def clear_warmup(account_id):
    """Disable warmup mode for an account."""
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE accounts SET warmup = 0, warmup_until = NULL, updated_at = ? WHERE id = ?",
            (now, account_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def bulk_set_warmup(account_ids, warmup_until):
    """Enable warmup for multiple accounts at once."""
    if not account_ids:
        return 0
    conn = get_conn()
    try:
        now = datetime.utcnow().isoformat()
        placeholders = ','.join('?' * len(account_ids))
        conn.execute(
            f"UPDATE accounts SET warmup = 1, warmup_until = ?, updated_at = ? WHERE id IN ({placeholders})",
            [warmup_until, now] + list(account_ids)
        )
        conn.commit()
        return len(account_ids)
    finally:
        conn.close()


def expire_warmups():
    """
    Auto-clear warmup for accounts whose warmup_until date has passed.
    Returns the number of accounts updated.
    """
    conn = get_conn()
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        now = datetime.utcnow().isoformat()
        cursor = conn.execute(
            "UPDATE accounts SET warmup = 0, warmup_until = NULL, updated_at = ? "
            "WHERE warmup = 1 AND warmup_until IS NOT NULL AND warmup_until <= ?",
            (now, today)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_warmup_accounts():
    """Get all accounts currently in warmup mode."""
    conn = get_conn()
    try:
        return rows_to_dicts(conn.execute(
            "SELECT a.*, d.device_name FROM accounts a "
            "LEFT JOIN devices d ON d.id = a.device_id "
            "WHERE a.warmup = 1 ORDER BY a.warmup_until"
        ).fetchall())
    finally:
        conn.close()
