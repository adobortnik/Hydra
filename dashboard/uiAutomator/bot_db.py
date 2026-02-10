#!/usr/bin/env python3
"""
Bot Database Layer
Manages bot status, account sessions, and action history for device bots
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime


# Bot data directory
BOT_DATA_DIR = Path(__file__).parent / "bot_data"
BOT_DATA_DIR.mkdir(exist_ok=True)


def get_bot_db_path(device_serial):
    """Get database path for device bot"""
    return BOT_DATA_DIR / f"{device_serial}_bot.db"


def init_bot_database(device_serial):
    """
    Initialize bot database for a device

    Args:
        device_serial: Device serial (e.g., "10.1.10.183_5555")
    """
    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Bot status table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY,
            device_serial TEXT UNIQUE,
            status TEXT DEFAULT 'stopped',
            started_at TIMESTAMP,
            last_check_at TIMESTAMP,
            pid INTEGER,
            accounts_run_today INTEGER DEFAULT 0,
            actions_today INTEGER DEFAULT 0
        )
    ''')

    # Account sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_serial TEXT NOT NULL,
            username TEXT NOT NULL,
            session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_end TIMESTAMP,
            status TEXT DEFAULT 'running',
            actions_executed TEXT,
            errors_count INTEGER DEFAULT 0,
            error_details TEXT
        )
    ''')

    # Action history table (detailed log)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            device_serial TEXT NOT NULL,
            username TEXT NOT NULL,
            action_type TEXT NOT NULL,
            target_username TEXT,
            target_post_id TEXT,
            success INTEGER DEFAULT 1,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            error_message TEXT,
            FOREIGN KEY (session_id) REFERENCES account_sessions(id)
        )
    ''')

    # Indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_device ON account_sessions(device_serial)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_username ON account_sessions(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_session ON action_history(session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_timestamp ON action_history(timestamp)')

    conn.commit()
    conn.close()

    print(f"Initialized bot database: {db_path}")


def update_bot_status(device_serial, status, pid=None):
    """
    Update bot status

    Args:
        device_serial: Device serial
        status: Bot status ('running', 'paused', 'stopped')
        pid: Process ID (optional)
    """
    init_bot_database(device_serial)  # Ensure database exists

    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check if bot status exists
    cursor.execute('SELECT id FROM bot_status WHERE device_serial = ?', (device_serial,))
    exists = cursor.fetchone()

    if exists:
        # Update existing
        if pid:
            cursor.execute('''
                UPDATE bot_status
                SET status = ?, last_check_at = CURRENT_TIMESTAMP, pid = ?
                WHERE device_serial = ?
            ''', (status, pid, device_serial))
        else:
            cursor.execute('''
                UPDATE bot_status
                SET status = ?, last_check_at = CURRENT_TIMESTAMP
                WHERE device_serial = ?
            ''', (status, device_serial))

        # Update started_at when transitioning to running
        if status == 'running':
            cursor.execute('''
                UPDATE bot_status
                SET started_at = CURRENT_TIMESTAMP
                WHERE device_serial = ?
            ''', (device_serial,))
    else:
        # Insert new
        cursor.execute('''
            INSERT INTO bot_status (device_serial, status, started_at, last_check_at, pid)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        ''', (device_serial, status, pid))

    conn.commit()
    conn.close()


def get_bot_status(device_serial):
    """
    Get current bot status

    Args:
        device_serial: Device serial

    Returns:
        dict: Bot status or default stopped status
    """
    db_path = get_bot_db_path(device_serial)

    if not db_path.exists():
        return {'status': 'stopped', 'device_serial': device_serial}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM bot_status WHERE device_serial = ?', (device_serial,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    else:
        return {'status': 'stopped', 'device_serial': device_serial}


def create_account_session(device_serial, username):
    """
    Create new account session

    Args:
        device_serial: Device serial
        username: Account username

    Returns:
        int: Session ID
    """
    init_bot_database(device_serial)

    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO account_sessions (device_serial, username)
        VALUES (?, ?)
    ''', (device_serial, username))

    session_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return session_id


def complete_account_session(device_serial, session_id, status='completed', error=None, actions=None):
    """
    Mark account session as complete

    Args:
        device_serial: Device serial
        session_id: Session ID
        status: Final status ('completed', 'error')
        error: Error details (if any)
        actions: Dict of actions performed (e.g., {'follow': 10, 'like': 25})
    """
    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Serialize actions dict to JSON
    actions_json = json.dumps(actions) if actions else None

    cursor.execute('''
        UPDATE account_sessions
        SET session_end = CURRENT_TIMESTAMP,
            status = ?,
            error_details = ?,
            actions_executed = ?
        WHERE id = ?
    ''', (status, error, actions_json, session_id))

    conn.commit()
    conn.close()


def log_action(session_id, device_serial, username, action_type, target, success, error=None):
    """
    Log individual action to history

    Args:
        session_id: Session ID
        device_serial: Device serial
        username: Account username
        action_type: Action type ('follow', 'like', 'comment', etc.)
        target: Target username or post ID
        success: True if successful, False if failed
        error: Error message (if failed)
    """
    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO action_history
        (session_id, device_serial, username, action_type, target_username, success, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, device_serial, username, action_type, target, 1 if success else 0, error))

    conn.commit()
    conn.close()


def get_last_session_time(device_serial, username):
    """
    Get timestamp of last session for account

    Args:
        device_serial: Device serial
        username: Account username

    Returns:
        datetime: Last session start time or None
    """
    db_path = get_bot_db_path(device_serial)

    if not db_path.exists():
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute('''
        SELECT session_start FROM account_sessions
        WHERE device_serial = ? AND username = ?
        ORDER BY session_start DESC
        LIMIT 1
    ''', (device_serial, username))

    row = cursor.fetchone()
    conn.close()

    if row:
        # Parse timestamp string to datetime
        return datetime.fromisoformat(row[0])
    else:
        return None


def query_account_sessions(device_serial, limit=50):
    """
    Query recent account sessions for device

    Args:
        device_serial: Device serial
        limit: Maximum sessions to return

    Returns:
        List[dict]: List of sessions
    """
    db_path = get_bot_db_path(device_serial)

    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM account_sessions
        WHERE device_serial = ?
        ORDER BY session_start DESC
        LIMIT ?
    ''', (device_serial, limit))

    sessions = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return sessions


def calculate_device_metrics(device_serial):
    """
    Calculate today's metrics for device

    Args:
        device_serial: Device serial

    Returns:
        dict: Metrics (sessions, actions, success rate)
    """
    db_path = get_bot_db_path(device_serial)

    if not db_path.exists():
        return {
            'sessions_today': 0,
            'actions_today': 0,
            'successful_actions': 0,
            'failed_actions': 0,
            'success_rate': 0
        }

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Count sessions today
    cursor.execute('''
        SELECT COUNT(*) FROM account_sessions
        WHERE device_serial = ? AND DATE(session_start) = DATE('now')
    ''', (device_serial,))
    sessions_today = cursor.fetchone()[0]

    # Count actions today
    cursor.execute('''
        SELECT COUNT(*), SUM(success) FROM action_history
        WHERE device_serial = ? AND DATE(timestamp) = DATE('now')
    ''', (device_serial,))

    row = cursor.fetchone()
    actions_today = row[0] if row[0] else 0
    successful_actions = row[1] if row[1] else 0
    failed_actions = actions_today - successful_actions

    conn.close()

    success_rate = (successful_actions / actions_today * 100) if actions_today > 0 else 0

    return {
        'sessions_today': sessions_today,
        'actions_today': actions_today,
        'successful_actions': successful_actions,
        'failed_actions': failed_actions,
        'success_rate': round(success_rate, 2)
    }


def increment_actions_today(device_serial, count=1):
    """
    Increment actions_today counter

    Args:
        device_serial: Device serial
        count: Number of actions to add
    """
    db_path = get_bot_db_path(device_serial)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE bot_status
        SET actions_today = actions_today + ?
        WHERE device_serial = ?
    ''', (count, device_serial))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Test database creation
    print("Testing bot database creation...")

    test_device = "10.1.10.183_5555"

    # Initialize
    init_bot_database(test_device)

    # Update status
    update_bot_status(test_device, 'running', pid=12345)

    # Get status
    status = get_bot_status(test_device)
    print(f"Bot status: {status}")

    # Create session
    session_id = create_account_session(test_device, "test_account")
    print(f"Created session: {session_id}")

    # Log action
    log_action(session_id, test_device, "test_account", "follow", "target_user", True)

    # Complete session
    complete_account_session(test_device, session_id, 'completed', actions={'follow': 1})

    # Get metrics
    metrics = calculate_device_metrics(test_device)
    print(f"Metrics: {metrics}")

    print("\nBot database test complete!")
