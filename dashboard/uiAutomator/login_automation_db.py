"""
login_automation_db.py

Database layer for Instagram Login Automation System
Follows the same patterns as profile_automation_db.py

Database Tables:
- login_tasks: Task queue for login operations
- login_history: Audit trail of all login attempts
- two_factor_services: Storage for 2fa.live tokens

Author: Claude Code
Created: 2025-11-21
"""

import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime

# Database path
# uiAutomator is now inside the-livehouse-dashboard
BASE_DIR = Path(__file__).parent.parent.parent
DATABASE_PATH = Path(__file__).parent / 'login_automation.db'


def get_db_connection():
    """Get database connection with row_factory for dict-like access"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """
    Initialize the login automation database with all required tables

    Creates:
    - login_tasks: Task queue for pending login operations
    - login_history: Audit trail of all login attempts
    - two_factor_services: Storage for 2fa.live tokens
    """
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Task queue table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS login_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT NOT NULL,
        instagram_package TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        two_fa_token TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        priority INTEGER DEFAULT 0
    )
    ''')

    # History table (audit trail)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS login_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_serial TEXT NOT NULL,
        instagram_package TEXT NOT NULL,
        username TEXT NOT NULL,
        login_type TEXT NOT NULL,
        success INTEGER DEFAULT 1,
        logged_in_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        error_details TEXT,
        two_fa_used INTEGER DEFAULT 0,
        challenge_encountered INTEGER DEFAULT 0
    )
    ''')

    # 2FA services table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS two_factor_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT DEFAULT '2fa.live',
        token TEXT NOT NULL UNIQUE,
        phone_number TEXT,
        username TEXT,
        device_serial TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP,
        usage_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        notes TEXT
    )
    ''')

    # Create indexes for performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_tasks_status ON login_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_tasks_device ON login_tasks(device_serial)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_tasks_username ON login_tasks(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_history_device ON login_history(device_serial)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_history_username ON login_history(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_history_timestamp ON login_history(logged_in_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_2fa_token ON two_factor_services(token)')

    conn.commit()
    conn.close()

    print(f"✓ Database initialized: {DATABASE_PATH}")


def create_login_task(device_serial, instagram_package, username, password, two_fa_token=None, priority=0):
    """
    Create a new login task

    Args:
        device_serial: Device identifier (e.g., "10.1.10.183_5555")
        instagram_package: Package name (e.g., "com.instagram.androim")
        username: Instagram username
        password: Instagram password
        two_fa_token: Optional 2fa.live token (e.g., "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
        priority: Task priority (higher = earlier execution)

    Returns:
        int: Task ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if task already exists and is pending/processing
    cursor.execute('''
        SELECT id, status FROM login_tasks
        WHERE device_serial = ? AND username = ? AND status IN ('pending', 'processing')
    ''', (device_serial, username))

    existing = cursor.fetchone()
    if existing:
        conn.close()
        print(f"⚠ Task already exists for {username} on {device_serial} (status: {existing['status']})")
        return existing['id']

    # Create new task
    cursor.execute('''
        INSERT INTO login_tasks
        (device_serial, instagram_package, username, password, two_fa_token, priority)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (device_serial, instagram_package, username, password, two_fa_token, priority))

    task_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"✓ Created login task #{task_id}: {username} on {device_serial}")
    return task_id


def get_pending_login_tasks(device_serial=None, limit=None):
    """
    Get pending login tasks, optionally filtered by device

    Args:
        device_serial: Optional device filter
        limit: Optional limit on number of tasks

    Returns:
        list: List of task dicts sorted by priority (high to low), then created_at
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if device_serial:
        query = '''
            SELECT * FROM login_tasks
            WHERE status = 'pending' AND device_serial = ?
            ORDER BY priority DESC, created_at ASC
        '''
        params = (device_serial,)
    else:
        query = '''
            SELECT * FROM login_tasks
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
        '''
        params = ()

    if limit:
        query += f' LIMIT {limit}'

    cursor.execute(query, params)
    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return tasks


def get_all_login_tasks(status=None):
    """
    Get all login tasks, optionally filtered by status

    Args:
        status: Optional status filter ('pending', 'processing', 'completed', 'failed', 'needs_manual')

    Returns:
        list: List of task dicts
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if status:
        cursor.execute('SELECT * FROM login_tasks WHERE status = ? ORDER BY created_at DESC', (status,))
    else:
        cursor.execute('SELECT * FROM login_tasks ORDER BY created_at DESC')

    tasks = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return tasks


def update_task_status(task_id, status, error_message=None):
    """
    Update task status

    Args:
        task_id: Task ID
        status: New status ('processing', 'completed', 'failed', 'needs_manual')
        error_message: Optional error message for failed tasks
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    timestamp = datetime.now().isoformat()

    if status == 'completed':
        cursor.execute('''
            UPDATE login_tasks
            SET status = ?, updated_at = ?, completed_at = ?, error_message = ?
            WHERE id = ?
        ''', (status, timestamp, timestamp, error_message, task_id))
    else:
        cursor.execute('''
            UPDATE login_tasks
            SET status = ?, updated_at = ?, error_message = ?
            WHERE id = ?
        ''', (status, timestamp, error_message, task_id))

    conn.commit()
    conn.close()

    print(f"✓ Updated task #{task_id} status: {status}")


def increment_retry_count(task_id):
    """
    Increment retry count for a task

    Args:
        task_id: Task ID

    Returns:
        int: New retry count
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT retry_count, max_retries FROM login_tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()

    if row:
        new_count = row['retry_count'] + 1
        cursor.execute('''
            UPDATE login_tasks
            SET retry_count = ?, updated_at = ?
            WHERE id = ?
        ''', (new_count, datetime.now().isoformat(), task_id))
        conn.commit()
        conn.close()
        return new_count

    conn.close()
    return 0


def log_login_attempt(device_serial, instagram_package, username, login_type, success,
                     error_details=None, two_fa_used=False, challenge_encountered=False):
    """
    Log a login attempt to history

    Args:
        device_serial: Device identifier
        instagram_package: Package name
        username: Instagram username
        login_type: Type of login ('normal', '2fa', 'challenge', 'already_logged_in')
        success: Boolean success flag
        error_details: Optional error details
        two_fa_used: Whether 2FA was used
        challenge_encountered: Whether a challenge was encountered

    Returns:
        int: History entry ID
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO login_history
        (device_serial, instagram_package, username, login_type, success,
         error_details, two_fa_used, challenge_encountered)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (device_serial, instagram_package, username, login_type,
          1 if success else 0, error_details,
          1 if two_fa_used else 0, 1 if challenge_encountered else 0))

    history_id = cursor.lastrowid
    conn.commit()
    conn.close()

    status = "✓" if success else "✗"
    print(f"{status} Logged login attempt: {username} on {device_serial} ({login_type})")

    return history_id


def get_login_history(device_serial=None, username=None, limit=50):
    """
    Get login history

    Args:
        device_serial: Optional device filter
        username: Optional username filter
        limit: Maximum number of entries to return

    Returns:
        list: List of history dicts
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = 'SELECT * FROM login_history WHERE 1=1'
    params = []

    if device_serial:
        query += ' AND device_serial = ?'
        params.append(device_serial)

    if username:
        query += ' AND username = ?'
        params.append(username)

    query += ' ORDER BY logged_in_at DESC LIMIT ?'
    params.append(limit)

    cursor.execute(query, params)
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return history


def add_2fa_token(token, phone_number=None, username=None, device_serial=None, notes=None):
    """
    Add a 2fa.live token

    Args:
        token: 2fa.live token (e.g., "CHN44RHFYSYPFCKLL2C5CFHNTY54PYOD")
        phone_number: Optional phone number associated with token
        username: Optional username this token is for
        device_serial: Optional device this token is associated with
        notes: Optional notes

    Returns:
        int: Token ID, or None if already exists
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if token already exists
    cursor.execute('SELECT id FROM two_factor_services WHERE token = ?', (token,))
    existing = cursor.fetchone()

    if existing:
        conn.close()
        print(f"⚠ 2FA token already exists: {token}")
        return existing['id']

    # Add new token
    cursor.execute('''
        INSERT INTO two_factor_services
        (token, phone_number, username, device_serial, notes)
        VALUES (?, ?, ?, ?, ?)
    ''', (token, phone_number, username, device_serial, notes))

    token_id = cursor.lastrowid
    conn.commit()
    conn.close()

    print(f"✓ Added 2FA token #{token_id}: {token}")
    return token_id


def get_2fa_token(username=None, device_serial=None):
    """
    Get 2FA token for a user/device

    Args:
        username: Optional username filter
        device_serial: Optional device filter

    Returns:
        dict: Token info, or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if username:
        cursor.execute('''
            SELECT * FROM two_factor_services
            WHERE username = ? AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        ''', (username,))
    elif device_serial:
        cursor.execute('''
            SELECT * FROM two_factor_services
            WHERE device_serial = ? AND status = 'active'
            ORDER BY created_at DESC LIMIT 1
        ''', (device_serial,))
    else:
        # Get any active token
        cursor.execute('''
            SELECT * FROM two_factor_services
            WHERE status = 'active'
            ORDER BY usage_count ASC, created_at DESC LIMIT 1
        ''')

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def update_2fa_token_usage(token):
    """
    Update last_used and usage_count for a token

    Args:
        token: 2fa.live token string
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE two_factor_services
        SET last_used = ?, usage_count = usage_count + 1
        WHERE token = ?
    ''', (datetime.now().isoformat(), token))

    conn.commit()
    conn.close()


def get_task_by_id(task_id):
    """
    Get a specific task by ID

    Args:
        task_id: Task ID

    Returns:
        dict: Task info, or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM login_tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def delete_task(task_id):
    """
    Delete a task

    Args:
        task_id: Task ID

    Returns:
        bool: True if deleted, False if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM login_tasks WHERE id = ?', (task_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()

    if deleted:
        print(f"✓ Deleted task #{task_id}")
    else:
        print(f"⚠ Task #{task_id} not found")

    return deleted


def clear_completed_tasks(days_old=7):
    """
    Clear completed tasks older than specified days

    Args:
        days_old: Delete completed tasks older than this many days

    Returns:
        int: Number of tasks deleted
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cutoff_time = datetime.now().timestamp() - (days_old * 86400)

    cursor.execute('''
        DELETE FROM login_tasks
        WHERE status = 'completed'
        AND completed_at < datetime(?, 'unixepoch')
    ''', (cutoff_time,))

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"✓ Cleared {deleted} completed tasks older than {days_old} days")
    return deleted


def get_statistics():
    """
    Get login automation statistics

    Returns:
        dict: Statistics including task counts, success rates, etc.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Task statistics
    cursor.execute('SELECT status, COUNT(*) as count FROM login_tasks GROUP BY status')
    task_stats = {row['status']: row['count'] for row in cursor.fetchall()}

    # History statistics
    cursor.execute('SELECT COUNT(*) as total, SUM(success) as successful FROM login_history')
    history_row = cursor.fetchone()

    total_attempts = history_row['total'] or 0
    successful_attempts = history_row['successful'] or 0
    success_rate = (successful_attempts / total_attempts * 100) if total_attempts > 0 else 0

    # 2FA statistics
    cursor.execute('SELECT COUNT(*) as total FROM two_factor_services WHERE status = "active"')
    active_tokens = cursor.fetchone()['total']

    # Recent activity
    cursor.execute('''
        SELECT COUNT(*) as recent_logins
        FROM login_history
        WHERE logged_in_at > datetime('now', '-24 hours')
    ''')
    recent_logins = cursor.fetchone()['recent_logins']

    conn.close()

    return {
        'tasks': task_stats,
        'total_attempts': total_attempts,
        'successful_attempts': successful_attempts,
        'success_rate': round(success_rate, 2),
        'active_2fa_tokens': active_tokens,
        'recent_logins_24h': recent_logins
    }


# Initialize database on module import
if __name__ == '__main__':
    print("="*70)
    print("INITIALIZING LOGIN AUTOMATION DATABASE")
    print("="*70)

    init_database()

    # Print statistics
    print("\n" + "="*70)
    print("DATABASE STATISTICS")
    print("="*70)

    stats = get_statistics()
    print(f"Task Statistics: {stats['tasks']}")
    print(f"Total Login Attempts: {stats['total_attempts']}")
    print(f"Successful Logins: {stats['successful_attempts']}")
    print(f"Success Rate: {stats['success_rate']}%")
    print(f"Active 2FA Tokens: {stats['active_2fa_tokens']}")
    print(f"Recent Logins (24h): {stats['recent_logins_24h']}")

    print("\n✓ Database ready!")
