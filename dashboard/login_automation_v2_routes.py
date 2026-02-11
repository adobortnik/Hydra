"""
login_automation_v2_routes.py - Login Automation V2 Blueprint

Reads account credentials from phone_farm.db (single source of truth)
instead of per-device accounts.db files.

Reuses the existing ADB-based login scripts where possible.
"""

import sys
import os
import json
import threading
import traceback
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

from phone_farm_db import (
    get_all_devices, get_all_accounts, get_account_by_id,
    update_account_status, update_account, get_accounts_for_device,
    create_task, update_task, get_tasks_by_type_and_status
)
from adb_helper import serial_db_to_adb, check_device_reachable

# Try to import existing login utilities
UI_AUTOMATOR_PATH = Path(__file__).parent / 'uiAutomator'
sys.path.insert(0, str(UI_AUTOMATOR_PATH))

try:
    from automated_login_manager import AutomatedLoginManager
    HAS_LOGIN_MANAGER = True
except ImportError:
    HAS_LOGIN_MANAGER = False

try:
    from two_fa_live_client import TwoFALiveClient
    HAS_2FA_CLIENT = True
except ImportError:
    HAS_2FA_CLIENT = False

login_v2_bp = Blueprint('login_v2', __name__)

# In-memory task tracker for live progress
_login_progress = {}  # batch_id -> { status, message, ... }
_login_lock = threading.Lock()
_stop_requested = set()  # batch_ids that should stop


# ─────────────────────────────────────────────
# PAGE ROUTE
# ─────────────────────────────────────────────

@login_v2_bp.route('/login-automation-v2')
def login_automation_v2_page():
    return render_template('login_automation_v2.html')


# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────

@login_v2_bp.route('/api/login-v2/pending', methods=['GET'])
def api_pending_accounts():
    """
    Get accounts with status pending_login or login_failed.
    Optional query param: ?device_serial=...
    """
    try:
        device_serial = request.args.get('device_serial')
        statuses = ['pending_login', 'login_failed']

        accounts = get_all_accounts(status_filter=statuses, device_serial=device_serial)

        # Group by device for the UI
        by_device = {}
        for acc in accounts:
            ds = acc.get('device_serial', 'unassigned')
            if ds not in by_device:
                by_device[ds] = []
            by_device[ds].append(acc)

        return jsonify({
            'status': 'success',
            'accounts': accounts,
            'by_device': by_device,
            'total': len(accounts),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/devices', methods=['GET'])
def api_login_devices():
    """Get all devices for the filter dropdown."""
    try:
        devices = get_all_devices()
        return jsonify({'status': 'success', 'devices': devices})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/create-tasks', methods=['POST'])
def api_create_login_tasks():
    """
    Create login tasks for selected account IDs.

    Body: { "account_ids": [1, 2, 3, ...] }
    """
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])

        if not account_ids:
            return jsonify({'status': 'error', 'message': 'No accounts selected'}), 400

        task_ids = []
        errors = []

        for aid in account_ids:
            acc = get_account_by_id(aid)
            if not acc:
                errors.append(f"Account ID {aid} not found")
                continue

            if not acc.get('device_serial'):
                errors.append(f"{acc['username']}: no device assigned")
                continue

            # Build params for the login task
            params = {
                'username': acc['username'],
                'password': acc.get('password', ''),
                'two_fa_token': acc.get('two_fa_token', ''),
                'instagram_package': acc.get('instagram_package', 'com.instagram.android'),
                'device_serial': acc['device_serial'],
            }

            task_id = create_task(
                account_id=acc['id'],
                device_serial=acc['device_serial'],
                task_type='login',
                params_json=json.dumps(params),
            )
            task_ids.append(task_id)

            # Set account status to logging_in
            update_account_status(acc['id'], 'logging_in')

        return jsonify({
            'status': 'success',
            'created': len(task_ids),
            'task_ids': task_ids,
            'errors': errors,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/execute', methods=['POST'])
def api_execute_login():
    """
    Execute login tasks. Runs in background threads.
    
    Body: { "task_ids": [1, 2, 3] } or { "all_pending": true }
    """
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        all_pending = data.get('all_pending', False)

        # Get tasks to execute
        if all_pending:
            tasks = get_tasks_by_type_and_status('login', ['pending'])
        else:
            tasks = get_tasks_by_type_and_status('login', ['pending'])
            if task_ids:
                tasks = [t for t in tasks if t['id'] in task_ids]

        if not tasks:
            return jsonify({'status': 'error', 'message': 'No pending login tasks found'}), 400

        # Group by device (max 1 concurrent login per device)
        by_device = {}
        for task in tasks:
            ds = task.get('device_serial', '')
            if ds not in by_device:
                by_device[ds] = []
            by_device[ds].append(task)

        # Launch one thread per device
        batch_id = f"batch_{int(datetime.utcnow().timestamp())}"

        with _login_lock:
            _login_progress[batch_id] = {
                'total': len(tasks),
                'completed': 0,
                'failed': 0,
                'in_progress': 0,
                'results': {},
                'started_at': datetime.utcnow().isoformat(),
            }

        for ds, device_tasks in by_device.items():
            t = threading.Thread(
                target=_run_device_logins,
                args=(batch_id, ds, device_tasks),
                daemon=True
            )
            t.start()

        return jsonify({
            'status': 'success',
            'batch_id': batch_id,
            'total_tasks': len(tasks),
            'devices': len(by_device),
            'message': f'Started {len(tasks)} login tasks across {len(by_device)} devices',
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/status', methods=['GET'])
def api_login_status():
    """Get live status of login tasks."""
    try:
        batch_id = request.args.get('batch_id')

        if batch_id:
            with _login_lock:
                progress = _login_progress.get(batch_id, {})
            return jsonify({'status': 'success', 'progress': progress})

        # Return all active tasks
        tasks = get_tasks_by_type_and_status('login', ['pending', 'running', 'completed', 'failed'])

        return jsonify({
            'status': 'success',
            'tasks': tasks,
            'active_batches': list(_login_progress.keys()),
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/reset-failed', methods=['POST'])
def api_reset_failed():
    """Reset login_failed accounts back to pending_login."""
    try:
        data = request.get_json()
        account_ids = data.get('account_ids', [])

        if not account_ids:
            return jsonify({'status': 'error', 'message': 'No accounts selected'}), 400

        count = 0
        for aid in account_ids:
            update_account_status(aid, 'pending_login')
            count += 1

        return jsonify({'status': 'success', 'reset': count})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@login_v2_bp.route('/api/login-v2/stop', methods=['POST'])
def api_stop_login():
    """Stop a running login batch. Remaining tasks revert to pending."""
    try:
        data = request.get_json() or {}
        batch_id = data.get('batch_id')

        if not batch_id:
            # Stop ALL active batches
            with _login_lock:
                for bid in list(_login_progress.keys()):
                    _stop_requested.add(bid)
                    _login_progress[bid]['stopped'] = True
                stopped = len(_stop_requested)
            return jsonify({'status': 'success', 'message': f'Stop requested for {stopped} batch(es)'})

        _stop_requested.add(batch_id)
        with _login_lock:
            if batch_id in _login_progress:
                _login_progress[batch_id]['stopped'] = True

        return jsonify({'status': 'success', 'message': f'Stop requested for {batch_id}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ─────────────────────────────────────────────
# BACKGROUND LOGIN WORKER
# ─────────────────────────────────────────────

def _run_device_logins(batch_id, device_serial, tasks):
    """
    Execute login tasks sequentially on a single device.
    Runs in a background thread.
    """
    for task in tasks:
        # Check if stop was requested before starting next account
        if batch_id in _stop_requested:
            # Mark remaining tasks back to pending
            remaining = [t for t in tasks if t['id'] >= task['id']]
            for rt in remaining:
                rt_id = rt['id']
                rt_params = json.loads(rt.get('params_json', '{}'))
                rt_username = rt_params.get('username', '?')
                update_task(rt_id, status='pending')
                rt_account_id = rt.get('account_id')
                if rt_account_id:
                    update_account_status(rt_account_id, 'pending_login')
                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['results'][str(rt_id)] = {
                            'status': 'skipped',
                            'username': rt_username,
                            'device': device_serial,
                            'message': 'Stopped by user',
                        }
            with _login_lock:
                if batch_id in _login_progress:
                    _login_progress[batch_id]['stopped'] = True
            return  # Exit the thread

        task_id = task['id']
        account_id = task.get('account_id')
        params = json.loads(task.get('params_json', '{}'))
        username = params.get('username', '?')

        # Update progress
        with _login_lock:
            if batch_id in _login_progress:
                _login_progress[batch_id]['in_progress'] += 1
                _login_progress[batch_id]['results'][str(task_id)] = {
                    'status': 'running',
                    'username': username,
                    'device': device_serial,
                }

        # Update task status
        update_task(task_id, status='running', started_at=datetime.utcnow().isoformat())

        try:
            # Try using the existing login manager
            success, message = _perform_login(
                device_serial=device_serial,
                username=params.get('username', ''),
                password=params.get('password', ''),
                two_fa_token=params.get('two_fa_token', ''),
                instagram_package=params.get('instagram_package', 'com.instagram.android'),
            )

            now = datetime.utcnow().isoformat()

            if success:
                update_task(task_id, status='completed', completed_at=now,
                            result_json=json.dumps({'message': message}))
                if account_id:
                    update_account_status(account_id, 'active')

                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['completed'] += 1
                        _login_progress[batch_id]['in_progress'] -= 1
                        _login_progress[batch_id]['results'][str(task_id)] = {
                            'status': 'completed', 'username': username,
                            'device': device_serial, 'message': message,
                        }
            else:
                update_task(task_id, status='failed', completed_at=now,
                            result_json=json.dumps({'error': message}))
                if account_id:
                    update_account_status(account_id, 'login_failed')

                with _login_lock:
                    if batch_id in _login_progress:
                        _login_progress[batch_id]['failed'] += 1
                        _login_progress[batch_id]['in_progress'] -= 1
                        _login_progress[batch_id]['results'][str(task_id)] = {
                            'status': 'failed', 'username': username,
                            'device': device_serial, 'error': message,
                        }

        except Exception as e:
            now = datetime.utcnow().isoformat()
            error_msg = f"{type(e).__name__}: {str(e)}"
            update_task(task_id, status='failed', completed_at=now,
                        result_json=json.dumps({'error': error_msg}))
            if account_id:
                update_account_status(account_id, 'login_failed')

            with _login_lock:
                if batch_id in _login_progress:
                    _login_progress[batch_id]['failed'] += 1
                    _login_progress[batch_id]['in_progress'] -= 1
                    _login_progress[batch_id]['results'][str(task_id)] = {
                        'status': 'failed', 'username': username,
                        'device': device_serial, 'error': error_msg,
                    }


def _perform_login(device_serial, username, password, two_fa_token, instagram_package):
    """
    Perform the actual Instagram login via ADB.
    Uses AutomatedLoginManager if available, otherwise returns a stub.
    """
    adb_serial = serial_db_to_adb(device_serial)

    # Check device reachability first
    if not check_device_reachable(device_serial):
        return False, f"Device {device_serial} not reachable via ADB"

    if HAS_LOGIN_MANAGER:
        try:
            manager = AutomatedLoginManager()

            # The existing manager expects certain params — adapt
            result = manager.login_account(
                device_serial=adb_serial,
                instagram_package=instagram_package,
                username=username,
                password=password,
                two_fa_token=two_fa_token if two_fa_token else None,
            )

            if isinstance(result, dict):
                success = result.get('success', False)
                message = result.get('message', str(result))
                return success, message
            elif isinstance(result, bool):
                return result, 'Login completed' if result else 'Login failed'
            else:
                return bool(result), str(result)

        except Exception as e:
            return False, f"Login manager error: {str(e)}"
    else:
        # Fallback: just verify device is reachable (stub for testing)
        return False, "AutomatedLoginManager not available. Install uiAutomator dependencies."
