"""
login_automation_routes.py

Flask Blueprint for Instagram Login Automation API
Provides REST endpoints for the dashboard to control login automation

Integrates with dashboard's existing account loading system (get_devices, get_accounts)

Author: Claude Code
Created: 2025-11-21
"""

import sys
import os
from pathlib import Path
from flask import Blueprint, jsonify, request, current_app
import sqlite3
import json

# Add uiAutomator to path for imports (now inside dashboard folder)
UI_AUTOMATOR_PATH = Path(__file__).parent / 'uiAutomator'
sys.path.append(str(UI_AUTOMATOR_PATH))

from login_automation_db import (
    create_login_task,
    get_all_login_tasks,
    get_pending_login_tasks,
    get_task_by_id,
    update_task_status,
    delete_task,
    get_login_history,
    add_2fa_token,
    get_2fa_token,
    get_statistics,
    clear_completed_tasks,
    init_database
)
from two_fa_live_client import TwoFALiveClient
from automated_login_manager import AutomatedLoginManager


# Create Blueprint
login_bp = Blueprint('login', __name__, url_prefix='/api/login')

# Base directory
BASE_DIR = Path(__file__).parent.parent

# Initialize login automation database on blueprint registration
try:
    init_database()
except:
    pass  # Database may already exist


# ============================================================================
# HELPER FUNCTIONS - Use dashboard's existing account system
# ============================================================================

def get_dashboard_devices():
    """Get devices from dashboard's devices.db"""
    try:
        from simple_app import get_devices
        return get_devices()
    except:
        # Fallback: read directly
        devices_db = BASE_DIR / 'devices.db'
        if not devices_db.exists():
            return []

        conn = sqlite3.connect(devices_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM devices')
        devices = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return devices


def get_dashboard_accounts(deviceid):
    """Get accounts for a device from dashboard's {device}/accounts.db"""
    try:
        from simple_app import get_accounts
        return get_accounts(deviceid)
    except:
        # Fallback: read directly
        accounts_db = BASE_DIR / deviceid / 'accounts.db'
        if not accounts_db.exists():
            return []

        conn = sqlite3.connect(accounts_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts')
        accounts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return accounts


def get_instagram_package_for_account(deviceid, username, account_data=None):
    """Get Instagram package from account's appid field or settings.db"""
    # First try to get from account_data (from CSV import)
    if account_data and 'appid' in account_data and account_data['appid']:
        return account_data['appid']

    # Fallback: try reading from settings.db
    settings_db = BASE_DIR / deviceid / username / 'settings.db'

    if settings_db.exists():
        try:
            conn = sqlite3.connect(settings_db)
            cursor = conn.cursor()
            cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
            row = cursor.fetchone()
            conn.close()

            if row and row[0]:
                settings = json.loads(row[0])
                app_cloner = settings.get('app_cloner', '')
                if '/' in app_cloner:
                    return app_cloner.split('/')[0]

        except Exception as e:
            print(f"Error reading settings for {username}: {e}")

    return 'com.instagram.android'


def get_2fa_token_for_account(deviceid, username, account_data=None):
    """Get 2FA token from account's 2fa_setup_code field or settings.db"""
    # First try to get from account_data (from CSV import)
    if account_data:
        token = account_data.get('2fa_setup_code', '') or account_data.get('tfa_code', '')
        if token:
            return token

    # Fallback: try reading from settings.db (code_2fa field)
    settings_db = BASE_DIR / deviceid / username / 'settings.db'

    if settings_db.exists():
        try:
            conn = sqlite3.connect(settings_db)
            cursor = conn.cursor()
            cursor.execute('SELECT settings FROM accountsettings WHERE id = 1')
            row = cursor.fetchone()
            conn.close()

            if row and row[0]:
                settings = json.loads(row[0])
                code_2fa = settings.get('code_2fa', '')
                if code_2fa:
                    return code_2fa

        except Exception as e:
            print(f"Error reading 2FA from settings for {username}: {e}")

    return ''


# ============================================================================
# DASHBOARD INTEGRATION ENDPOINTS (New - for UI)
# ============================================================================

@login_bp.route('/devices', methods=['GET'])
def list_devices():
    """
    Get all devices (from dashboard's devices.db)

    Returns:
        {
            "status": "success",
            "devices": [
                {
                    "deviceid": "10.1.10.183_5555",
                    "devicename": "Device 1",
                    "status": "active"
                },
                ...
            ]
        }
    """
    try:
        devices = get_dashboard_devices()
        return jsonify({
            'status': 'success',
            'devices': devices
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/devices/<device_serial>/accounts', methods=['GET'])
def list_device_accounts(device_serial):
    """
    Get all accounts for a device (from dashboard's {device}/accounts.db)

    Returns:
        {
            "status": "success",
            "device_serial": "10.1.10.183_5555",
            "accounts": [
                {
                    "account": "testuser",
                    "password": "testpass123",
                    "instagram_package": "com.instagram.androim",
                    "two_fa_token": "CHN44RHFY...",
                    ...
                },
                ...
            ]
        }
    """
    try:
        accounts = get_dashboard_accounts(device_serial)

        # Enrich with Instagram package info and 2FA token
        for account in accounts:
            username = account['account']
            # Get instagram package from appid field or settings.db
            account['instagram_package'] = get_instagram_package_for_account(
                device_serial, username, account
            )
            # Get 2FA token from 2fa_setup_code field or settings.db (code_2fa)
            account['two_fa_token'] = get_2fa_token_for_account(
                device_serial, username, account
            )

        return jsonify({
            'status': 'success',
            'device_serial': device_serial,
            'accounts': accounts
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/accounts/selected', methods=['POST'])
def create_tasks_for_selected_accounts():
    """
    Create login tasks for selected accounts (like profile automation)

    POST body:
    {
        "accounts": [
            {
                "device_serial": "10.1.10.183_5555",
                "username": "user1"
            },
            ...
        ],
        "two_fa_token": "CHN44RHFY...",  // optional, apply to all
        "priority": 0  // optional
    }

    Returns:
        {
            "status": "success",
            "created": 5,
            "task_ids": [...]
        }
    """
    try:
        data = request.get_json()

        if 'accounts' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "accounts" field'
            }), 400

        two_fa_token = data.get('two_fa_token')
        priority = data.get('priority', 0)

        task_ids = []
        errors = []
        warnings = []

        for acc in data['accounts']:
            device_serial = acc.get('device_serial')
            username = acc.get('username')

            if not device_serial or not username:
                errors.append(f"Missing device_serial or username for account")
                continue

            # Get password from dashboard's accounts.db
            accounts = get_dashboard_accounts(device_serial)
            account_data = next((a for a in accounts if a['account'] == username), None)

            if not account_data:
                errors.append(f"Account {username} not found on {device_serial}")
                continue

            password = account_data.get('password')
            if not password:
                errors.append(f"No password for {username} on {device_serial}")
                continue

            # Get Instagram package from appid field or settings.db
            instagram_package = get_instagram_package_for_account(device_serial, username, account_data)

            # Get 2FA token - use manual override if provided, otherwise use from account data or settings.db
            account_2fa = get_2fa_token_for_account(device_serial, username, account_data)
            final_2fa_token = two_fa_token if two_fa_token else account_2fa

            # Check if task already exists
            from login_automation_db import get_db_connection
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, status FROM login_tasks
                WHERE device_serial = ? AND username = ? AND status IN ('pending', 'processing')
            ''', (device_serial, username))
            existing = cursor.fetchone()
            conn.close()

            if existing:
                warnings.append(f"Task for {username} already exists (status: {existing['status']}). Delete it first to recreate.")
                task_ids.append(existing['id'])
                continue

            # Create task
            task_id = create_login_task(
                device_serial=device_serial,
                instagram_package=instagram_package,
                username=username,
                password=password,
                two_fa_token=final_2fa_token,
                priority=priority
            )

            task_ids.append(task_id)

        return jsonify({
            'status': 'success',
            'created': len(task_ids) - len(warnings),  # Only count newly created, not reused
            'task_ids': task_ids,
            'errors': errors if errors else None,
            'warnings': warnings if warnings else None
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# TASK MANAGEMENT ENDPOINTS
# ============================================================================

@login_bp.route('/tasks', methods=['POST'])
def create_task():
    """
    Create a login task

    POST body:
    {
        "device_serial": "10.1.10.183_5555",
        "instagram_package": "com.instagram.androim",
        "username": "testuser",
        "password": "testpass123",
        "two_fa_token": "CHN44RHFY...",  // optional
        "priority": 0  // optional, default 0
    }

    Returns:
        {
            "status": "success",
            "task_id": 123
        }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ['device_serial', 'instagram_package', 'username', 'password']
        missing = [f for f in required if f not in data]

        if missing:
            return jsonify({
                'status': 'error',
                'message': f'Missing required fields: {", ".join(missing)}'
            }), 400

        # Create task
        task_id = create_login_task(
            device_serial=data['device_serial'],
            instagram_package=data['instagram_package'],
            username=data['username'],
            password=data['password'],
            two_fa_token=data.get('two_fa_token'),
            priority=data.get('priority', 0)
        )

        return jsonify({
            'status': 'success',
            'task_id': task_id
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/bulk', methods=['POST'])
def create_bulk_tasks():
    """
    Create login tasks for multiple accounts

    POST body:
    {
        "accounts": [
            {
                "device_serial": "10.1.10.183_5555",
                "username": "user1",
                "password": "pass1",
                "instagram_package": "com.instagram.androim",
                "two_fa_token": "TOKEN1"
            },
            ...
        ]
    }

    Returns:
        {
            "status": "success",
            "created": 5,
            "task_ids": [123, 124, 125, ...]
        }
    """
    try:
        data = request.get_json()

        if 'accounts' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "accounts" field'
            }), 400

        task_ids = []

        for account in data['accounts']:
            # Validate account has required fields
            required = ['device_serial', 'username', 'password', 'instagram_package']
            if not all(f in account for f in required):
                continue

            task_id = create_login_task(
                device_serial=account['device_serial'],
                instagram_package=account['instagram_package'],
                username=account['username'],
                password=account['password'],
                two_fa_token=account.get('two_fa_token'),
                priority=account.get('priority', 0)
            )

            task_ids.append(task_id)

        return jsonify({
            'status': 'success',
            'created': len(task_ids),
            'task_ids': task_ids
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/device/<device_serial>', methods=['POST'])
def create_tasks_for_device(device_serial):
    """
    Create login tasks for all accounts on a device

    Uses dashboard's get_accounts() to read from {device_serial}/accounts.db

    POST body (optional):
    {
        "two_fa_token": "TOKEN",  // Apply to all accounts
        "priority": 0
    }

    Returns:
        {
            "status": "success",
            "created": 3,
            "task_ids": [...]
        }
    """
    try:
        data = request.get_json() or {}

        two_fa_token = data.get('two_fa_token')
        priority = data.get('priority', 0)

        # Get accounts using dashboard's function
        accounts = get_dashboard_accounts(device_serial)

        if not accounts:
            return jsonify({
                'status': 'success',
                'created': 0,
                'message': 'No accounts found'
            })

        task_ids = []
        errors = []

        for account in accounts:
            username = account['account']
            password = account.get('password')

            if not password:
                errors.append(f"No password for {username}")
                continue

            # Get Instagram package
            instagram_package = get_instagram_package_for_account(device_serial, username)

            # Create task
            task_id = create_login_task(
                device_serial=device_serial,
                instagram_package=instagram_package,
                username=username,
                password=password,
                two_fa_token=two_fa_token,
                priority=priority
            )

            task_ids.append(task_id)

        return jsonify({
            'status': 'success',
            'created': len(task_ids),
            'task_ids': task_ids,
            'errors': errors if errors else None
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """
    Get login tasks with optional filtering

    Query params:
        ?status=pending|completed|failed|needs_manual
        ?device=10.1.10.183_5555

    Returns:
        {
            "status": "success",
            "tasks": [...]
        }
    """
    try:
        status_filter = request.args.get('status')
        device_filter = request.args.get('device')

        if device_filter:
            tasks = get_pending_login_tasks(device_serial=device_filter)
        else:
            tasks = get_all_login_tasks(status=status_filter)

        return jsonify({
            'status': 'success',
            'tasks': tasks
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/<int:task_id>', methods=['GET'])
def get_task(task_id):
    """
    Get a specific task

    Returns:
        {
            "status": "success",
            "task": {...}
        }
    """
    try:
        task = get_task_by_id(task_id)

        if not task:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_id} not found'
            }), 404

        return jsonify({
            'status': 'success',
            'task': task
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/<int:task_id>', methods=['DELETE'])
def delete_task_endpoint(task_id):
    """
    Delete a task

    Returns:
        {
            "status": "success"
        }
    """
    try:
        if delete_task(task_id):
            return jsonify({'status': 'success'})
        else:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_id} not found'
            }), 404

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/<int:task_id>/restart', methods=['POST'])
def restart_task_endpoint(task_id):
    """
    Restart a task by resetting its status to 'pending'

    This allows stuck 'processing' or 'failed' tasks to be re-executed.

    Returns:
        {
            "status": "success"
        }
    """
    try:
        # Get the task to verify it exists
        task = get_task_by_id(task_id)

        if not task:
            return jsonify({
                'status': 'error',
                'message': f'Task {task_id} not found'
            }), 404

        # Reset status to pending and clear any error message
        update_task_status(task_id, 'pending', error_message=None)

        return jsonify({
            'status': 'success',
            'message': f'Task {task_id} restarted and set to pending'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/<int:task_id>/execute', methods=['POST'])
def execute_task(task_id):
    """
    Execute a specific task

    Returns:
        {
            "status": "success",
            "result": {...}
        }
    """
    try:
        manager = AutomatedLoginManager()
        success = manager.process_task_by_id(task_id)

        if success:
            return jsonify({
                'status': 'success',
                'result': 'Login completed successfully'
            })
        else:
            task = get_task_by_id(task_id)
            return jsonify({
                'status': 'error',
                'message': task.get('error_message', 'Login failed')
            }), 500

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/storage-permission', methods=['POST'])
def create_storage_permission_tasks():
    """
    Create storage permission tasks for selected accounts

    POST body:
    {
        "accounts": [
            {
                "device_serial": "10.1.10.183_5555",
                "username": "user1"
            },
            ...
        ]
    }

    Returns:
        {
            "status": "success",
            "created": 5,
            "task_ids": [...]
        }
    """
    try:
        data = request.get_json()

        if 'accounts' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "accounts" field'
            }), 400

        task_ids = []
        errors = []
        warnings = []

        for acc in data['accounts']:
            device_serial = acc.get('device_serial')
            username = acc.get('username')

            if not device_serial or not username:
                errors.append(f"Missing device_serial or username for account")
                continue

            # Get account data to get Instagram package
            accounts = get_dashboard_accounts(device_serial)
            account_data = next((a for a in accounts if a['account'] == username), None)

            if not account_data:
                errors.append(f"Account {username} not found on {device_serial}")
                continue

            # Get Instagram package
            instagram_package = get_instagram_package_for_account(device_serial, username, account_data)

            # Create a login task with a special flag for storage permission
            # We'll reuse the login task system but mark it as storage_permission type
            task_id = create_login_task(
                device_serial=device_serial,
                instagram_package=instagram_package,
                username=username,
                password="STORAGE_PERMISSION",  # Special marker
                two_fa_token=None,
                priority=10  # Higher priority
            )

            task_ids.append(task_id)

        return jsonify({
            'status': 'success',
            'created': len(task_ids) - len(warnings),
            'task_ids': task_ids,
            'errors': errors if errors else None,
            'warnings': warnings if warnings else None
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/process', methods=['POST'])
def process_all_tasks():
    """
    Process all pending tasks (batch processor)

    POST body (optional):
    {
        "device_serial": "10.1.10.183_5555",  // Optional filter
        "max_tasks": 10  // Optional limit
    }

    Returns:
        {
            "status": "success",
            "stats": {...}
        }
    """
    try:
        data = request.get_json() or {}

        manager = AutomatedLoginManager()
        stats = manager.run_batch_processor(
            device_serial=data.get('device_serial'),
            max_tasks=data.get('max_tasks')
        )

        return jsonify({
            'status': 'success',
            'stats': stats
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/tasks/process-parallel', methods=['POST'])
def process_tasks_parallel():
    """
    Process all pending tasks using parallel processor (FASTER)

    Different devices will process simultaneously in parallel threads.
    Same device tasks will still run sequentially.

    POST body (optional):
    {
        "device_serial": "10.1.10.183_5555",  // Optional filter
        "max_tasks": 10,  // Optional limit
        "max_devices": 3  // Optional: limit parallel devices
    }

    Returns:
        {
            "status": "success",
            "stats": {
                "successful": 13,
                "failed": 1,
                "needs_manual": 1,
                "total": 15
            },
            "duration": 78
        }
    """
    try:
        import sys
        from pathlib import Path
        import time

        # Import parallel processor
        sys.path.insert(0, str(Path(__file__).parent.parent / 'uiAutomator'))
        from parallel_login_processor import ParallelLoginProcessor

        data = request.get_json() or {}

        # Get pending tasks
        pending_tasks = get_pending_login_tasks(
            device_serial=data.get('device_serial'),
            limit=data.get('max_tasks')
        )

        if not pending_tasks:
            return jsonify({
                'status': 'success',
                'message': 'No pending tasks',
                'stats': {
                    'successful': 0,
                    'failed': 0,
                    'needs_manual': 0,
                    'total': 0
                },
                'duration': 0
            })

        # Create processor and run in parallel mode
        processor = ParallelLoginProcessor()

        start_time = time.time()
        processor.run_parallel(
            pending_tasks,
            max_parallel_devices=data.get('max_devices')
        )
        end_time = time.time()

        duration = int(end_time - start_time)

        return jsonify({
            'status': 'success',
            'stats': processor.results,
            'duration': duration,
            'message': f'Processed {processor.results["total"]} tasks in {duration} seconds'
        })

    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }), 500


@login_bp.route('/tasks/clear', methods=['POST'])
def clear_tasks():
    """
    Clear completed tasks

    POST body:
    {
        "days_old": 7  // Optional, default 7
    }

    Returns:
        {
            "status": "success",
            "deleted": 10
        }
    """
    try:
        data = request.get_json() or {}
        days_old = data.get('days_old', 7)

        deleted = clear_completed_tasks(days_old)

        return jsonify({
            'status': 'success',
            'deleted': deleted
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# QUICK LOGIN ENDPOINT
# ============================================================================

@login_bp.route('/quick_login', methods=['POST'])
def quick_login():
    """
    One-shot login without creating a task

    POST body:
    {
        "device_serial": "10.1.10.183_5555",
        "instagram_package": "com.instagram.androim",
        "username": "testuser",
        "password": "testpass123",
        "two_fa_token": "CHN44RHFY..."  // optional
    }

    Returns:
        {
            "status": "success",
            "result": {...}
        }
    """
    try:
        data = request.get_json()

        # Validate
        required = ['device_serial', 'instagram_package', 'username', 'password']
        missing = [f for f in required if f not in data]

        if missing:
            return jsonify({
                'status': 'error',
                'message': f'Missing required fields: {", ".join(missing)}'
            }), 400

        # Perform login
        from login_automation import LoginAutomation

        login = LoginAutomation(data['device_serial'])

        if not login.connect_device():
            return jsonify({
                'status': 'error',
                'message': 'Failed to connect to device'
            }), 500

        result = login.login_account(
            username=data['username'],
            password=data['password'],
            instagram_package=data['instagram_package'],
            two_fa_token=data.get('two_fa_token')
        )

        if result['success']:
            return jsonify({
                'status': 'success',
                'result': result
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result.get('error', 'Login failed'),
                'result': result
            }), 500

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# HISTORY AND STATISTICS
# ============================================================================

@login_bp.route('/history', methods=['GET'])
def get_history():
    """
    Get login history

    Query params:
        ?device=10.1.10.183_5555
        ?username=testuser
        ?limit=50

    Returns:
        {
            "status": "success",
            "history": [...]
        }
    """
    try:
        device_serial = request.args.get('device')
        username = request.args.get('username')
        limit = int(request.args.get('limit', 50))

        history = get_login_history(
            device_serial=device_serial,
            username=username,
            limit=limit
        )

        return jsonify({
            'status': 'success',
            'history': history
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/statistics', methods=['GET'])
def get_stats():
    """
    Get login automation statistics

    Returns:
        {
            "status": "success",
            "statistics": {...}
        }
    """
    try:
        stats = get_statistics()

        return jsonify({
            'status': 'success',
            'statistics': stats
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# 2FA MANAGEMENT
# ============================================================================

@login_bp.route('/2fa/tokens', methods=['POST'])
def add_token():
    """
    Add a 2FA token

    POST body:
    {
        "token": "CHN44RHFY...",
        "username": "testuser",  // optional
        "device_serial": "10.1.10.183_5555",  // optional
        "phone_number": "+1234567890",  // optional
        "notes": "Notes"  // optional
    }

    Returns:
        {
            "status": "success",
            "token_id": 123
        }
    """
    try:
        data = request.get_json()

        if 'token' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "token" field'
            }), 400

        token_id = add_2fa_token(
            token=data['token'],
            phone_number=data.get('phone_number'),
            username=data.get('username'),
            device_serial=data.get('device_serial'),
            notes=data.get('notes')
        )

        return jsonify({
            'status': 'success',
            'token_id': token_id
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/2fa/tokens/<token>', methods=['GET'])
def get_token(token):
    """
    Get a 2FA token

    Returns:
        {
            "status": "success",
            "token": {...}
        }
    """
    try:
        from login_automation_db import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM two_factor_services WHERE token = ?", (token,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({
                'status': 'error',
                'message': 'Token not found'
            }), 404

        return jsonify({
            'status': 'success',
            'token': dict(row)
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@login_bp.route('/2fa/test', methods=['POST'])
def test_2fa():
    """
    Test a 2FA token

    POST body:
    {
        "token": "CHN44RHFY..."
    }

    Returns:
        {
            "status": "success",
            "test_result": {...},
            "code": "123456"  // if available
        }
    """
    try:
        data = request.get_json()

        if 'token' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "token" field'
            }), 400

        client = TwoFALiveClient(data['token'])
        result = client.test_connection()

        return jsonify({
            'status': 'success' if result['success'] else 'error',
            'test_result': result,
            'code': result.get('code')
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@login_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint

    Returns:
        {
            "status": "ok",
            "version": "1.0.0"
        }
    """
    return jsonify({
        'status': 'ok',
        'version': '1.0.0'
    })
